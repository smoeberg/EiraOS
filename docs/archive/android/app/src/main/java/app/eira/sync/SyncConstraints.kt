package app.eira.sync

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.BatteryManager
import androidx.work.Constraints
import androidx.work.NetworkType
import java.net.URI

/** Fail-closed trust and scheduling policy for background fleet sync. */
object SyncConstraints {
    val workConstraints: Constraints = Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .setRequiresBatteryNotLow(true)
        .build()

    fun isTrustedEndpoint(serverUrl: String): Boolean {
        return try {
            val uri = URI(serverUrl)
            uri.scheme == "ws" &&
                uri.port in 1..65535 &&
                uri.userInfo == null &&
                uri.query == null &&
                uri.fragment == null &&
                uri.path.orEmpty() in listOf("", "/") &&
                uri.host != null &&
                (uri.host.equals("127.0.0.1", true) ||
                    uri.host.equals("localhost", true) ||
                    uri.host.equals("::1", true))
        } catch (_: Exception) {
            false
        }
    }

    /** Returns false for missing, disconnected, or unvalidated network and low/unknown battery. */
    fun constraintsSatisfied(context: Context): Boolean {
        return try {
            val connectivity = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
            val network = connectivity.activeNetwork ?: return false
            val capabilities = connectivity.getNetworkCapabilities(network) ?: return false
            if (!capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) ||
                !capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)) return false
            val battery = context.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
            battery.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY).let { it in 20..100 }
        } catch (_: Exception) {
            false
        }
    }
}
