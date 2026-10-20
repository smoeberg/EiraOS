package app.eira.core

import java.security.MessageDigest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class EiraStateEngineTest {
    private class FakeNativeApi(
        private val hash: String? = EXPECTED_HASH,
        private val validationResult: Int = 1,
        private val hashFailure: Throwable? = null,
        private val validationFailure: Throwable? = null,
    ) : NativeApi {
        override fun computeHash(jsonUtf8: ByteArray): String? {
            hashFailure?.let { throw it }
            return hash
        }

        override fun validateChain(chainJsonUtf8: ByteArray): Int {
            validationFailure?.let { throw it }
            return validationResult
        }
    }

    @Test
    fun sha3_256_known_state_vector_matches_python_contract() {
        val engine = EiraStateEngine(FakeNativeApi())

        val actual = engine.computeHash(KNOWN_STATE_JSON)

        assertEquals(EXPECTED_HASH, actual)
        assertEquals(EXPECTED_HASH, sha3_256(CANONICAL_STATE_JSON))
    }

    @Test
    fun validate_chain_returns_native_result() {
        val engine = EiraStateEngine(FakeNativeApi(validationResult = 1))

        assertEquals(1, engine.validateChain("[{}]"))
    }

    @Test
    fun invalid_chain_is_returned_without_being_treated_as_native_error() {
        val engine = EiraStateEngine(FakeNativeApi(validationResult = 0))

        assertEquals(0, engine.validateChain("[{}]"))
    }

    @Test
    fun negative_native_validation_result_fails_closed() {
        val engine = EiraStateEngine(FakeNativeApi(validationResult = -1))

        assertFailsWith<StateValidationException> {
            engine.validateChain("[{}]")
        }
    }

    @Test
    fun unknown_positive_native_validation_result_fails_closed() {
        val engine = EiraStateEngine(FakeNativeApi(validationResult = 2))

        assertFailsWith<StateValidationException> {
            engine.validateChain("[{}]")
        }
    }

    @Test
    fun null_native_hash_fails_closed() {
        val engine = EiraStateEngine(FakeNativeApi(hash = null))

        assertFailsWith<StateValidationException> {
            engine.computeHash(KNOWN_STATE_JSON)
        }
    }

    @Test
    fun native_exception_fails_closed() {
        val engine = EiraStateEngine(
            FakeNativeApi(hashFailure = IllegalStateException("native failure")),
        )

        assertFailsWith<StateValidationException> {
            engine.computeHash(KNOWN_STATE_JSON)
        }
    }

    @Test
    fun malformed_native_hash_fails_closed() {
        val engine = EiraStateEngine(FakeNativeApi(hash = "not-a-sha3-hash"))

        assertFailsWith<StateValidationException> {
            engine.computeHash(KNOWN_STATE_JSON)
        }
    }

    @Test
    fun blank_inputs_are_rejected_before_native_call() {
        var calls = 0
        val api = object : NativeApi {
            override fun computeHash(jsonUtf8: ByteArray): String? {
                calls += 1
                return EXPECTED_HASH
            }

            override fun validateChain(chainJsonUtf8: ByteArray): Int {
                calls += 1
                return 1
            }
        }
        val engine = EiraStateEngine(api)

        assertFailsWith<IllegalArgumentException> { engine.computeHash("  \n\t") }
        assertFailsWith<IllegalArgumentException> { engine.validateChain("  \n\t") }
        assertEquals(0, calls)
    }

    @Test
    fun utf8_state_json_is_forwarded_as_utf8() {
        var received = ByteArray(0)
        val api = object : NativeApi {
            override fun computeHash(jsonUtf8: ByteArray): String? {
                received = jsonUtf8
                return EXPECTED_HASH
            }

            override fun validateChain(chainJsonUtf8: ByteArray): Int = 1
        }
        val engine = EiraStateEngine(api)

        engine.computeHash(KNOWN_STATE_JSON)

        assertTrue(received.contentEquals(KNOWN_STATE_JSON.toByteArray(Charsets.UTF_8)))
    }

    private fun sha3_256(value: String): String =
        MessageDigest.getInstance("SHA3-256")
            .digest(value.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }

    companion object {
        private const val KNOWN_STATE_JSON =
            """{"type":"DocumentState","timestamp_ns":1,"payload":{"æ":"ø","a":1},"previous_state_id":null,"version":1,"id":"00000000-0000-0000-0000-000000000001"}"""

        private const val CANONICAL_STATE_JSON =
            """{"id":"00000000-0000-0000-0000-000000000001","payload":{"a":1,"æ":"ø"},"previous_state_id":null,"timestamp_ns":1,"type":"DocumentState","version":1}"""

        private const val EXPECTED_HASH =
            "b171d45f3bd8ffba4cfcbcbdf8275da4512db8ea934dd3c31fe5d0030c6fbf43"
    }
}
