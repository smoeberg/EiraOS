package app.eira.storage

import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import app.eira.core.EiraStateEngine
import java.nio.charset.StandardCharsets
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class RoomStateStoreTest {
    private val context = ApplicationProvider.getApplicationContext<android.content.Context>()

    @Before
    @After
    fun removeDatabase() {
        context.deleteDatabase(RoomStateStore.DATABASE_NAME)
    }

    @Test
    fun payloadIsNotStoredAsPlaintext() = runBlocking {
        val marker = "EIRA-CLEARTEXT-MARKER-8d2be3"
        val unhashed = StateEntity(
            id = "00000000-0000-0000-0000-000000000001",
            version = 1,
            timestamp_ns = 1,
            type = "SecretState",
            payload = "{\"secret\":\"$marker\"}",
            previous_state_id = null,
            hash = "",
        )
        val state = unhashed.copy(hash = EiraStateEngine.computeHash(unhashed.jsonForHash()))
        RoomStateStore.open(context).use { store ->
            store.appendValidated(state)
        }
        val databaseBytes = context.getDatabasePath(RoomStateStore.DATABASE_NAME).readBytes()
        assertFalse(
            databaseBytes.toString(StandardCharsets.UTF_8).contains(marker),
        )
    }
}
