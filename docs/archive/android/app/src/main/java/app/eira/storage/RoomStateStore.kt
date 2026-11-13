package app.eira.storage

import android.content.Context
import androidx.room.Room
import androidx.room.RoomDatabase
import app.eira.core.EiraStateEngine
import app.eira.core.StateValidationException
import app.eira.security.WrappedSecretStore
import net.zetetic.database.sqlcipher.SupportOpenHelperFactory
import org.json.JSONObject

@Database(entities = [StateEntity::class], version = 1, exportSchema = true)
abstract class EiraStateDatabase : RoomDatabase() {
    abstract fun stateDao(): StateDao
}

class RoomStateStore private constructor(
    private val database: EiraStateDatabase,
) : AutoCloseable {
    suspend fun appendValidated(state: StateEntity): Boolean {
        if (EiraStateEngine.computeHash(state.jsonForHash()) != state.hash) {
            throw StateValidationException("State hash is invalid")
        }
        return database.stateDao().insert(state) != -1L
    }

    suspend fun headers(): List<JSONObject> =
        database.stateDao().all().map(StateEntity::headerJson)

    suspend fun findByHashes(hashes: List<String>): List<StateEntity> =
        if (hashes.isEmpty()) emptyList() else database.stateDao().findByHashes(hashes)

    suspend fun replay(): List<StateEntity> {
        val states = database.stateDao().all()
        val seen = mutableSetOf<String>()
        states.forEach { state ->
            if (state.previous_state_id != null && state.previous_state_id !in seen) {
                throw StateValidationException(
                    "Broken local chain before state ${state.id}",
                )
            }
            if (EiraStateEngine.computeHash(state.jsonForHash()) != state.hash) {
                throw StateValidationException("Tampered local state ${state.id}")
            }
            check(seen.add(state.id)) { "Duplicate local state ${state.id}" }
        }
        return states
    }

    suspend fun replayAll(): List<StateEntity> {
        val states = database.stateDao().all()
        val seen = mutableSetOf<String>()
        val result = mutableListOf<StateEntity>()

        states.forEach { state ->
            if (state.previous_state_id != null && state.previous_state_id !in seen) {
                throw StateValidationException(
                    "Broken local chain before state ${state.id}",
                )
            }
            if (EiraStateEngine.computeHash(state.jsonForHash()) != state.hash) {
                throw StateValidationException("Tampered local state ${state.id}")
            }
            check(seen.add(state.id)) { "Duplicate local state ${state.id}" }
            result.add(state)
        }
        return result
    }

    override fun close() = database.close()

    companion object {
        const val DATABASE_NAME = "eira-state.db"

        fun open(context: Context): RoomStateStore {
            System.loadLibrary("sqlcipher")
            val passphrase = WrappedSecretStore(
                context,
                keyAlias = "eira-state-db-wrap-v1",
                preferencesName = "eira-state-db-key",
            ).getOrCreate("passphrase", 32)
            val database = Room.databaseBuilder(
                context.applicationContext,
                EiraStateDatabase::class.java,
                DATABASE_NAME,
            )
                .openHelperFactory(SupportOpenHelperFactory(passphrase))
                .build()
            database.openHelper.writableDatabase
            passphrase.fill(0)
            return RoomStateStore(database)
        }
    }
}
