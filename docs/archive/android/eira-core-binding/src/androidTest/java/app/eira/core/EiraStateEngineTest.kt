package app.eira.core

import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class EiraStateEngineTest {
    private val state = """
        {
          "type":"DocumentState",
          "timestamp_ns":1,
          "payload":{"æ":"ø","a":1},
          "previous_state_id":null,
          "version":1,
          "id":"00000000-0000-0000-0000-000000000001"
        }
    """.trimIndent()

    @Test
    fun hashMatchesPythonCanonicalContract() {
        assertEquals(
            "b171d45f3bd8ffba4cfcbcbdf8275da4512db8ea934dd3c31fe5d0030c6fbf43",
            EiraStateEngine.computeHash(state),
        )
    }

    @Test
    fun tamperedChainIsRejected() {
        val invalid = state.dropLast(1) + ",\"hash\":\"invalid\"}"
        assertFalse(EiraStateEngine.validateChain("[$invalid]"))
    }
}
