package app.eira.security

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class WrappedSecretStore(
    context: Context,
    private val keyAlias: String,
    preferencesName: String,
) {
    private val preferences = context.applicationContext.getSharedPreferences(
        preferencesName,
        Context.MODE_PRIVATE,
    )

    private fun wrappingKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(keyAlias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES,
            "AndroidKeyStore",
        ).apply {
            init(
                KeyGenParameterSpec.Builder(
                    keyAlias,
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                )
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setKeySize(256)
                    .build(),
            )
        }.generateKey()
    }

    fun put(name: String, secret: ByteArray) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, wrappingKey())
        val encrypted = cipher.doFinal(secret)
        val value = cipher.iv + encrypted
        preferences.edit()
            .putString(name, Base64.encodeToString(value, Base64.NO_WRAP))
            .commit()
    }

    fun get(name: String): ByteArray? {
        val encoded = preferences.getString(name, null) ?: return null
        val wrapped = Base64.decode(encoded, Base64.NO_WRAP)
        require(wrapped.size > GCM_NONCE_SIZE) { "Wrapped secret is truncated" }
        val nonce = wrapped.copyOfRange(0, GCM_NONCE_SIZE)
        val ciphertext = wrapped.copyOfRange(GCM_NONCE_SIZE, wrapped.size)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, wrappingKey(), GCMParameterSpec(128, nonce))
        return cipher.doFinal(ciphertext)
    }

    fun getOrCreate(name: String, length: Int): ByteArray {
        get(name)?.let {
            require(it.size == length) { "Stored secret has an invalid length" }
            return it
        }
        return ByteArray(length).also { secret ->
            java.security.SecureRandom().nextBytes(secret)
            put(name, secret)
        }
    }

    companion object {
        private const val GCM_NONCE_SIZE = 12
    }
}
