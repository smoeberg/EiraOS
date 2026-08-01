package app.eira.core

class StateValidationException(message: String) : IllegalArgumentException(message)

object EiraStateEngine {
    init {
        System.loadLibrary("eira_core")
        System.loadLibrary("eira_jni")
    }

    private external fun computeHashNative(jsonUtf8: ByteArray): String?
    private external fun validateChainNative(statesJsonUtf8: ByteArray): Int

    fun computeHash(jsonPayload: String): String =
        computeHashNative(jsonPayload.toByteArray(Charsets.UTF_8))
            ?: throw StateValidationException("Native state hash calculation failed")

    fun validateChain(statesJson: String): Boolean =
        when (validateChainNative(statesJson.toByteArray(Charsets.UTF_8))) {
            1 -> true
            0 -> false
            else -> throw StateValidationException("Native state-chain input is invalid")
        }
}
