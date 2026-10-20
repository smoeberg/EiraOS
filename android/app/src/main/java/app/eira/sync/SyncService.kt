package app.eira.sync

import android.content.Context
import android.app.Service
import android.content.Intent
import android.os.IBinder
import androidx.work.Data
import java.security.MessageDigest
import java.util.Locale
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

data class SyncStateHeader(val id: String, val version: Int, val hash: String, val previousStateId: String?, val timestampNs: Long = 0) {
    fun asJson() = JSONObject().put("id", id).put("version", version).put("hash", hash).put("previous_state_id", previousStateId ?: JSONObject.NULL).put("timestamp_ns", timestampNs)
    companion object { fun fromJson(v: JSONObject) = SyncStateHeader(v.getString("id"), v.getInt("version"), v.getString("hash"), if (v.isNull("previous_state_id")) null else v.getString("previous_state_id"), v.optLong("timestamp_ns", 0)) }
}
data class SyncMerkleSnapshot(val root: String, val headers: List<SyncStateHeader>, val heads: List<String>) {
    fun asDict() = JSONObject().put("root", root).put("heads", JSONArray(heads)).put("headers", JSONArray().also { a -> headers.forEach { a.put(it.asJson()) } })
}
data class SyncDiff(val localRoot: String, val remoteRoot: String, val missingFromLocal: List<String>, val missingFromRemote: List<String>) { val inSync: Boolean get() = localRoot == remoteRoot }
data class SyncForkResolution(val snapshot: SyncMerkleSnapshot, val canonicalHead: String?, val conflictingIds: List<String>) { val hasConflict: Boolean get() = conflictingIds.isNotEmpty() }
interface MerkleSyncEngine {
    fun snapshot(values: List<SyncStateHeader>): SyncMerkleSnapshot
    fun diff(local: List<SyncStateHeader>, remote: List<SyncStateHeader>): SyncDiff
    fun reconcile(local: List<SyncStateHeader>, remote: List<SyncStateHeader>): SyncForkResolution
}
interface StatePayloadEncryptor { fun encrypt_state(state: StateEntity): JSONObject; fun decrypt_state(envelope: JSONObject): StateEntity }
class CanonicalMerkleSyncEngine : MerkleSyncEngine {
    override fun snapshot(values: List<SyncStateHeader>): SyncMerkleSnapshot {
        val byId = linkedMapOf<String, SyncStateHeader>(); val byHash = linkedMapOf<String, SyncStateHeader>()
        values.forEach { h ->
            require(h.id.isNotBlank() && h.hash.matches(Regex("^[0-9a-f]{64}$")) && h.version >= 1 && h.timestampNs >= 0) { "invalid_state_header" }
            require(byHash[h.hash]?.let { it == h } != false) { "conflicting_metadata_for_state_hash" }
            require(byId[h.id]?.let { it.hash == h.hash } != false) { "conflicting_immutable_state_id:" + h.id }
            byHash[h.hash] = h; byId[h.id] = h
        }
        val headers = byHash.values.sortedWith(compareBy<SyncStateHeader>({ it.timestampNs }, { it.id }, { it.hash }))
        val completed = mutableSetOf<String>()
        byId.keys.forEach { start -> val path = mutableSetOf<String>(); var current: String? = start; while (current != null && byId.containsKey(current)) { if (current in completed) break; require(path.add(current)) { "state_dag_cycle_detected" }; current = byId.getValue(current).previousStateId }; completed.addAll(path) }
        val referenced = headers.mapNotNull { it.previousStateId }.toSet(); val heads = headers.filter { it.id !in referenced }.map { it.id }.sorted()
        val cache = mutableMapOf<String, String>()
        fun commitment(h: SyncStateHeader, active: MutableSet<String>): String {
            cache[h.hash]?.let { return it }; require(active.add(h.id)) { "state_dag_cycle_detected" }
            val parent = when { h.previousStateId == null -> "root"; !byId.containsKey(h.previousStateId) -> "missing:" + h.previousStateId; else -> commitment(byId.getValue(h.previousStateId), active) }; active.remove(h.id)
            val material = JSONObject().put("hash", h.hash).put("parent", parent).toString().toByteArray(StandardCharsets.UTF_8)
            val bytes = MessageDigest.getInstance("SHA3-256").digest("eira-merkle-node-v1\u0000".toByteArray(StandardCharsets.UTF_8) + material)
            return bytes.hex().also { cache[h.hash] = it }
        }
        val root = if (headers.isEmpty()) digest("eira-merkle-dag-v1\u0000".toByteArray(StandardCharsets.UTF_8)) else digest("eira-merkle-dag-v1\u0000".toByteArray(StandardCharsets.UTF_8) + heads.map { commitment(byId.getValue(it), mutableSetOf()) }.sorted().joinToString("\n").toByteArray(StandardCharsets.US_ASCII))
        return SyncMerkleSnapshot(root, headers, heads)
    }
    override fun diff(local: List<SyncStateHeader>, remote: List<SyncStateHeader>): SyncDiff { val l = snapshot(local); val r = snapshot(remote); val lh = l.headers.map { it.hash }.toSet(); val rh = r.headers.map { it.hash }.toSet(); return SyncDiff(l.root, r.root, r.headers.filter { it.hash !in lh }.map { it.hash }, l.headers.filter { it.hash !in rh }.map { it.hash }) }
    override fun reconcile(local: List<SyncStateHeader>, remote: List<SyncStateHeader>): SyncForkResolution {
        val all = (local + remote).distinctBy { it.hash }.sortedWith(compareBy<SyncStateHeader>({ it.timestampNs }, { it.id }, { it.hash }))
        val conflicts = all.groupBy { it.id }.filterValues { it.map { h -> h.hash }.distinct().size > 1 }.keys.sorted()
        if (conflicts.isNotEmpty()) { val material = all.joinToString("\n") { it.id + ":" + it.hash + ":" + (it.previousStateId ?: "") }.toByteArray(StandardCharsets.UTF_8); val root = digest("eira-merkle-conflict-v1\u0000".toByteArray(StandardCharsets.UTF_8) + material); val refs = all.mapNotNull { it.previousStateId }.toSet(); return SyncForkResolution(SyncMerkleSnapshot(root, all, all.filter { it.id !in refs }.map { it.id }.distinct().sorted()), null, conflicts) }
        val snap = snapshot(all); val forks = if (snap.heads.size > 1) snap.heads else emptyList(); return SyncForkResolution(snap, if (forks.isEmpty()) snap.heads.firstOrNull() else null, forks)
    }
    private fun digest(bytes: ByteArray) = MessageDigest.getInstance("SHA3-256").digest(bytes).hex()
    private fun ByteArray.hex() = joinToString("") { "%02x".format(Locale.ROOT, it) }
}
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

class FleetCrypto(masterKey: ByteArray, fleetSalt: ByteArray) : StatePayloadEncryptor {
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

    override fun encrypt_state(state: StateEntity): JSONObject {
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

    override fun decrypt_state(envelope: JSONObject): StateEntity {
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
    private val crypto: StatePayloadEncryptor,
    private val merkle: MerkleSyncEngine? = null,
    private val client: OkHttpClient = OkHttpClient(),
) {
    suspend fun syncOnce(): Boolean {
        require(SyncConstraints.isTrustedEndpoint(configuration.serverUrl)) { "untrusted_sync_endpoint" }
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
        private var remoteRoot: String? = null

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
                            require(result.optBoolean("accepted", false)) { "sync_handshake_rejected" }
                            val local = store.headers().map { SyncStateHeader.fromJson(it) }
                            val remote = result.getJSONArray("headers").objects().map { SyncStateHeader.fromJson(it) }
                            val diff = merkle.diff(local, remote)
                            require(!merkle.reconcile(local, remote).hasConflict) { "sync_merkle_conflict" }
                            if (diff.inSync) require(diff.localRoot == diff.remoteRoot) { "sync_root_disagreement" }
                            remoteRoot = result.optString("root")
                            require(remoteRoot == merkle.snapshot(remote).root) { "sync_remote_root_mismatch" }
                            val requests = result.getJSONArray("request_hashes").strings()
                            val offers = result.getJSONArray("offer_hashes").strings()
                            require(requests.toSet() == diff.missingFromRemote.toSet() && offers.toSet() == diff.missingFromLocal.toSet()) { "sync_diff_mismatch" }
                            uploadHashes = requests
                            val downloadHashes = offers
                            if (downloadHashes.isEmpty()) {
                                sendUploadsOrComplete(webSocket)
                            } else {
                                sendRequestBlocks(webSocket, downloadHashes)
                            }
                        }

                        "sync.request_blocks.result" -> {
                            val blocks = message.getJSONObject("result").getJSONArray("blocks")
                            for (index in 0 until blocks.length()) {
                                require(store.appendValidated(
                                    crypto.decrypt_state(blocks.getJSONObject(index)),
                                )) { "sync_download_block_rejected" }
                            }
                            sendUploadsOrComplete(webSocket)
                        }

                        "sync.push_blocks.result" -> {
                            val result = message.getJSONObject("result")
                            require(result.optInt("invalid", -1) == 0) { "sync_server_rejected_blocks" }
                            require(result.optString("root") == merkle.snapshot(store.headers().map { SyncStateHeader.fromJson(it) }).root) { "sync_final_root_mismatch" }
                            completion.complete(true)
                        }
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
                val local = store.headers().map { SyncStateHeader.fromJson(it) }
                completion.complete(merkle.snapshot(local).root == remoteRoot)
                return
            }
            val blocks = JSONArray().also { array ->
                store.findByHashes(uploadHashes).forEach { array.put(crypto.encrypt_state(it)) }
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

private fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { index -> getJSONObject(index) }

private fun JSONArray.strings(): List<String> =
    (0 until length()).map { index -> getString(index) }

class SyncWorker(
    appContext: Context,
    workerParameters: WorkerParameters,
) : CoroutineWorker(appContext, workerParameters) {
    override suspend fun doWork(): Result {
        val configuration = SyncConfigurationStore.load(applicationContext)
            ?: return Result.failure(Data.Builder().putString("sync_error", "missing_sync_configuration").build())
        if (!SyncConstraints.isTrustedEndpoint(configuration.serverUrl)) return Result.failure(Data.Builder().putString("sync_error", "untrusted_sync_endpoint").build())
        if (!SyncConstraints.constraintsSatisfied(applicationContext)) return Result.retry()
        val secrets = SyncSecrets.load(applicationContext) ?: return Result.failure(Data.Builder().putString("sync_error", "missing_sync_secrets").build())
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
    private val networkConstraints = SyncConstraints.workConstraints

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

class SyncService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        SyncScheduler.onStateAdded(applicationContext)
        stopSelf(startId)
        return START_NOT_STICKY
    }
}
