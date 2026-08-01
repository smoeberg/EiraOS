package app.eira.sync

import android.content.Context
import android.util.Base64
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import app.eira.security.WrappedSecretStore
import app.eira.storage.RoomStateStore
import app.eira.storage.StateEntity
import java.nio.charset.StandardCharsets
import java.security.GeneralSecurityException
import java.security.SecureRandom
import java.util.concurrent.TimeUnit
import javax.crypto.Cipher
import javax.crypto.Mac
import javax.crypto.spec.IvParameterSpec
import javax.crypto.spec.SecretKeySpec
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONArray
import org.json.JSONObject

data class SyncConfiguration(
    val serverUrl: String,
    val deviceId: String,
    val publicKey: String,
)

object SyncConfigurationStore {
    private const val PREFERENCES = "eira-sync-config-v1"

    fun save(context: Context, configuration: SyncConfiguration) {
        context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
            .edit()
            .putString("server_url", configuration.serverUrl)
            .putString("device_id", configuration.deviceId)
            .putString("public_key", configuration.publicKey)
            .apply()
    }

    fun load(context: Context): SyncConfiguration? {
        val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
        val serverUrl = preferences.getString("server_url", null) ?: return null
        val deviceId = preferences.getString("device_id", null) ?: return null
        val publicKey = preferences.getString("public_key", null) ?: return null
        return SyncConfiguration(serverUrl, deviceId, publicKey)
    }
}

data class FleetSecretMaterial(
    val masterKey: ByteArray,
    val fleetSalt: ByteArray,
    val authToken: String,
)

object SyncSecrets {
    private fun store(context: Context) = WrappedSecretStore(
        context,
        keyAlias = "eira-fleet-sync-wrap-v1",
        preferencesName = "eira-fleet-sync-secrets",
    )

    fun provision(
        context: Context,
        masterKey: ByteArray,
        fleetSalt: ByteArray,
        authToken: String,
    ) {
        require(masterKey.size == 32) { "Fleet master key must be 32 bytes" }
        require(fleetSalt.size == 16) { "Fleet salt must be 16 bytes" }
        require(authToken.isNotBlank()) { "Fleet authentication token is required" }
        store(context).put("master_key", masterKey)
        store(context).put("fleet_salt", fleetSalt)
        store(context).put("auth_token", authToken.toByteArray(StandardCharsets.UTF_8))
    }

    fun load(context: Context): FleetSecretMaterial? {
        val secrets = store(context)
        val masterKey = secrets.get("master_key") ?: return null
        val fleetSalt = secrets.get("fleet_salt") ?: return null
        val authToken = secrets.get("auth_token")
            ?.toString(StandardCharsets.UTF_8)
            ?: return null
        return FleetSecretMaterial(masterKey, fleetSalt, authToken)
    }
}

class FleetCrypto(masterKey: ByteArray, fleetSalt: ByteArray) {
    private val key = hkdfSha256(
        inputKey = masterKey,
        salt = fleetSalt,
        info = "eiraos-fleet-sync-v1\u0000state-payload".toByteArray(),
        length = 32,
    )

    private fun metadata(state: StateEntity) = JSONObject()
        .put("id", state.id)
        .put("version", state.version)
        .put("hash", state.hash)
        .put("previous_state_id", state.previous_state_id ?: JSONObject.NULL)

    private fun associatedData(metadata: JSONObject): ByteArray {
        val previous = if (metadata.isNull("previous_state_id")) {
            "null"
        } else {
            JSONObject.quote(metadata.getString("previous_state_id"))
        }
        val canonical = buildString {
            append("{\"algorithm\":\"ChaCha20-Poly1305+HKDF-SHA256\",")
            append("\"envelope_version\":1,\"metadata\":{")
            append("\"hash\":${JSONObject.quote(metadata.getString("hash"))},")
            append("\"id\":${JSONObject.quote(metadata.getString("id"))},")
            append("\"previous_state_id\":$previous,")
            append("\"version\":${metadata.getInt("version")}}}")
        }
        return canonical.toByteArray(StandardCharsets.UTF_8)
    }

    fun encrypt(state: StateEntity): JSONObject {
        val metadata = metadata(state)
        val plaintext = JSONObject()
            .put("payload", JSONObject(state.payload))
            .put("timestamp_ns", state.timestamp_ns)
            .put("type", state.type)
            .toString()
            .toByteArray(StandardCharsets.UTF_8)
        val nonce = ByteArray(12).also { SecureRandom().nextBytes(it) }
        val cipher = Cipher.getInstance("ChaCha20-Poly1305")
        cipher.init(
            Cipher.ENCRYPT_MODE,
            SecretKeySpec(key, "ChaCha20"),
            IvParameterSpec(nonce),
        )
        cipher.updateAAD(associatedData(metadata))
        val ciphertext = cipher.doFinal(plaintext)
        return JSONObject()
            .put("algorithm", "ChaCha20-Poly1305+HKDF-SHA256")
            .put("envelope_version", 1)
            .put("metadata", metadata)
            .put("nonce", Base64.encodeToString(nonce, Base64.NO_WRAP))
            .put("ciphertext", Base64.encodeToString(ciphertext, Base64.NO_WRAP))
    }

    fun decrypt(envelope: JSONObject): StateEntity {
        require(envelope.getString("algorithm") == "ChaCha20-Poly1305+HKDF-SHA256")
        require(envelope.getInt("envelope_version") == 1)
        val metadata = envelope.getJSONObject("metadata")
        val cipher = Cipher.getInstance("ChaCha20-Poly1305")
        cipher.init(
            Cipher.DECRYPT_MODE,
            SecretKeySpec(key, "ChaCha20"),
            IvParameterSpec(Base64.decode(envelope.getString("nonce"), Base64.NO_WRAP)),
        )
        cipher.updateAAD(associatedData(metadata))
        val plaintext = try {
            cipher.doFinal(
                Base64.decode(envelope.getString("ciphertext"), Base64.NO_WRAP),
            )
        } catch (error: GeneralSecurityException) {
            throw SecurityException("Fleet state authentication failed", error)
        }
        val protected = JSONObject(String(plaintext, StandardCharsets.UTF_8))
        return StateEntity(
            id = metadata.getString("id"),
            version = metadata.getInt("version"),
            timestamp_ns = protected.getLong("timestamp_ns"),
            type = protected.getString("type"),
            payload = protected.getJSONObject("payload").toString(),
            previous_state_id = if (metadata.isNull("previous_state_id")) {
                null
            } else {
                metadata.getString("previous_state_id")
            },
            hash = metadata.getString("hash"),
        )
    }

    companion object {
        private fun hkdfSha256(
            inputKey: ByteArray,
            salt: ByteArray,
            info: ByteArray,
            length: Int,
        ): ByteArray {
            val extract = Mac.getInstance("HmacSHA256")
            extract.init(SecretKeySpec(salt, "HmacSHA256"))
            val pseudoRandomKey = extract.doFinal(inputKey)
            val output = ByteArray(length)
            var previous = byteArrayOf()
            var offset = 0
            var counter = 1
            while (offset < length) {
                val expand = Mac.getInstance("HmacSHA256")
                expand.init(SecretKeySpec(pseudoRandomKey, "HmacSHA256"))
                expand.update(previous)
                expand.update(info)
                expand.update(counter.toByte())
                previous = expand.doFinal()
                val count = minOf(previous.size, length - offset)
                previous.copyInto(output, offset, 0, count)
                offset += count
                counter += 1
            }
            pseudoRandomKey.fill(0)
            return output
        }
    }
}

class FleetSyncClient(
    private val configuration: SyncConfiguration,
    private val authToken: String,
    private val store: RoomStateStore,
    private val crypto: FleetCrypto,
    private val client: OkHttpClient = OkHttpClient(),
) {
    suspend fun syncOnce(): Boolean {
        val completion = CompletableDeferred<Boolean>()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val listener = SessionListener(scope, completion)
        val websocket = client.newWebSocket(
            Request.Builder().url(configuration.serverUrl).build(),
            listener,
        )
        return try {
            withTimeout(60_000) { completion.await() }
        } finally {
            websocket.close(1000, "sync complete")
            scope.cancel()
        }
    }

    private inner class SessionListener(
        private val scope: CoroutineScope,
        private val completion: CompletableDeferred<Boolean>,
    ) : WebSocketListener() {
        private var uploadHashes: List<String> = emptyList()

        override fun onOpen(webSocket: WebSocket, response: Response) {
            scope.launch {
                val headers = JSONArray().also { array ->
                    store.headers().forEach(array::put)
                }
                webSocket.send(
                    JSONObject()
                        .put("id", "android-handshake")
                        .put("method", "sync.handshake")
                        .put(
                            "params",
                            JSONObject()
                                .put("device_id", configuration.deviceId)
                                .put("public_key", configuration.publicKey)
                                .put("auth_token", authToken)
                                .put("headers", headers),
                        )
                        .toString(),
                )
            }
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            scope.launch {
                try {
                    val message = JSONObject(text)
                    if (message.has("error")) {
                        completion.complete(false)
                        return@launch
                    }
                    when (message.getString("type")) {
                        "sync.handshake.result" -> {
                            val result = message.getJSONObject("result")
                            uploadHashes = result.getJSONArray("request_hashes").strings()
                            val downloadHashes = result.getJSONArray("offer_hashes").strings()
                            if (downloadHashes.isEmpty()) {
                                sendUploadsOrComplete(webSocket)
                            } else {
                                sendRequestBlocks(webSocket, downloadHashes)
                            }
                        }

                        "sync.request_blocks.result" -> {
                            val blocks = message.getJSONObject("result").getJSONArray("blocks")
                            for (index in 0 until blocks.length()) {
                                store.appendValidated(
                                    crypto.decrypt(blocks.getJSONObject(index)),
                                )
                            }
                            sendUploadsOrComplete(webSocket)
                        }

                        "sync.push_blocks.result" -> completion.complete(true)
                    }
                } catch (error: Exception) {
                    completion.completeExceptionally(error)
                }
            }
        }

        private fun sendRequestBlocks(webSocket: WebSocket, hashes: List<String>) {
            webSocket.send(
                JSONObject()
                    .put("id", "android-pull")
                    .put("method", "sync.request_blocks")
                    .put(
                        "params",
                        JSONObject()
                            .put("device_id", configuration.deviceId)
                            .put("auth_token", authToken)
                            .put("hashes", JSONArray(hashes)),
                    )
                    .toString(),
            )
        }

        private suspend fun sendUploadsOrComplete(webSocket: WebSocket) {
            if (uploadHashes.isEmpty()) {
                completion.complete(true)
                return
            }
            val blocks = JSONArray().also { array ->
                store.findByHashes(uploadHashes).forEach { array.put(crypto.encrypt(it)) }
            }
            webSocket.send(
                JSONObject()
                    .put("id", "android-push")
                    .put("method", "sync.push_blocks")
                    .put(
                        "params",
                        JSONObject()
                            .put("device_id", configuration.deviceId)
                            .put("auth_token", authToken)
                            .put("blocks", blocks),
                    )
                    .toString(),
            )
            uploadHashes = emptyList()
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            completion.completeExceptionally(t)
        }
    }
}

private fun JSONArray.strings(): List<String> =
    (0 until length()).map { index -> getString(index) }

class SyncWorker(
    appContext: Context,
    workerParameters: WorkerParameters,
) : CoroutineWorker(appContext, workerParameters) {
    override suspend fun doWork(): Result {
        val configuration = SyncConfigurationStore.load(applicationContext)
            ?: return Result.failure()
        val secrets = SyncSecrets.load(applicationContext) ?: return Result.failure()
        val store = RoomStateStore.open(applicationContext)
        return try {
            store.replay()
            val synced = FleetSyncClient(
                configuration,
                secrets.authToken,
                store,
                FleetCrypto(secrets.masterKey, secrets.fleetSalt),
            ).syncOnce()
            if (synced) Result.success() else Result.retry()
        } catch (_: Exception) {
            Result.retry()
        } finally {
            secrets.masterKey.fill(0)
            secrets.fleetSalt.fill(0)
            store.close()
        }
    }
}

object SyncScheduler {
    private val networkConstraints = Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .build()

    fun schedulePeriodic(context: Context, configuration: SyncConfiguration) {
        SyncConfigurationStore.save(context, configuration)
        val request = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES)
            .setConstraints(networkConstraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            "eira-fleet-periodic-sync",
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }

    fun onStateAdded(context: Context) {
        val request = OneTimeWorkRequestBuilder<SyncWorker>()
            .setConstraints(networkConstraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            "eira-fleet-push-sync",
            ExistingWorkPolicy.REPLACE,
            request,
        )
    }
}
