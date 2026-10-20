package app.eira.storage

import androidx.room.Entity
import androidx.room.PrimaryKey
import org.json.JSONObject

@Entity(tableName = "states")
data class StateEntity(
    @PrimaryKey val id: String,
    val version: Int,
    val timestamp_ns: Long,
    val type: String,
    val payload: String,
    val previous_state_id: String?,
    val hash: String,
) {
    fun jsonForHash(): String = buildString {
        append("{")
        append("\"id\":\"")
        append(id)
        append("\",")
        append("\"payload\":")
        append(payload)
        append(",")
        append("\"previous_state_id\":")
        if (previous_state_id != null) {
            append("\"")
            append(previous_state_id)
            append("\"")
        } else {
            append("null")
        }
        append(",")
        append("\"timestamp_ns\":")
        append(timestamp_ns)
        append(",")
        append("\"type\":\"")
        append(type)
        append("\",")
        append("\"version\":")
        append(version)
        append("}")
    }

    fun headerJson(): JSONObject = JSONObject()
        .put("id", id)
        .put("version", version)
        .put("hash", hash)
        .put("previous_state_id", previous_state_id ?: JSONObject.NULL)
        .put("timestamp_ns", timestamp_ns)
}
