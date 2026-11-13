package app.eira.storage

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface StateDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(state: StateEntity): Long

    @Query("SELECT * FROM states ORDER BY timestamp_ns, id")
    suspend fun all(): List<StateEntity>

    @Query("SELECT * FROM states WHERE hash IN (:hashes) ORDER BY timestamp_ns, id")
    suspend fun findByHashes(hashes: List<String>): List<StateEntity>
}
