package app.eira.core

import com.sun.jna.Library
import com.sun.jna.Memory
import com.sun.jna.Native
import com.sun.jna.Pointer

class StateValidationException(
    message: String,
    cause: Throwable? = null,
) : IllegalArgumentException(message, cause)

class EiraStateEngine(
    private val nativeApi: NativeApi = JnaNativeApi(),
) {
    fun computeHash(json: String): String {
        require(json.isNotBlank()) { "State JSON must not be blank" }

        val hash = callNative("state hash calculation failed") {
            nativeApi.computeHash(json.toByteArray(Charsets.UTF_8))
        } ?: throw StateValidationException("Native state hash calculation failed")

        if (!HASH_PATTERN.matches(hash)) {
            throw StateValidationException("Native state hash has invalid format")
        }
        return hash
    }

    fun validateChain(chainJson: String): Int {
        require(chainJson.isNotBlank()) { "State chain JSON must not be blank" }

        val result = callNative("state-chain validation failed") {
            nativeApi.validateChain(chainJson.toByteArray(Charsets.UTF_8))
        }

        if (result < 0) {
            throw StateValidationException("Native state-chain validation failed")
        }
        return result
    }

    private inline fun <T> callNative(
        message: String,
        block: () -> T,
    ): T {
        try {
            return block()
        } catch (error: StateValidationException) {
            throw error
        } catch (error: Exception) {
            throw StateValidationException(message, error)
        } catch (error: LinkageError) {
            throw StateValidationException(message, error)
        }
    }

    companion object {
        private val HASH_PATTERN = Regex("[0-9a-f]{64}")
    }
}

internal interface NativeApi {
    fun computeHash(jsonUtf8: ByteArray): String?

    fun validateChain(chainJsonUtf8: ByteArray): Int
}

private interface EiraCoreLibrary : Library {
    fun eira_state_compute_hash(jsonPayload: Pointer): Pointer?

    fun eira_state_validate_chain(statesJson: Pointer): Int

    fun eira_free_string(pointer: Pointer)
}

internal class JnaNativeApi : NativeApi {
    private val library: EiraCoreLibrary = try {
        System.loadLibrary("eira_core")
        Native.load("eira_core", EiraCoreLibrary::class.java)
    } catch (error: Throwable) {
        throw StateValidationException("Unable to load libeira_core.so", error)
    }

    override fun computeHash(jsonUtf8: ByteArray): String? =
        withUtf8Input(jsonUtf8) { input ->
            val result = library.eira_state_compute_hash(input) ?: return@withUtf8Input null
            try {
                result.getString(0, Charsets.UTF_8.name())
            } finally {
                library.eira_free_string(result)
            }
        }

    override fun validateChain(chainJsonUtf8: ByteArray): Int =
        withUtf8Input(chainJsonUtf8) { input ->
            library.eira_state_validate_chain(input)
        }

    private inline fun <T> withUtf8Input(
        bytes: ByteArray,
        block: (Pointer) -> T,
    ): T {
        val input = Memory(bytes.size.toLong() + 1L)
        input.write(0L, bytes, 0, bytes.size)
        input.setByte(bytes.size.toLong(), 0)
        return block(input)
    }
}
