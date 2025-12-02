package com.example.agent

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.google.android.gms.location.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import org.json.JSONObject

/**
 * Minimal foreground service that posts location to `/api/location_update`.
 * IMPORTANT: This is a snippet. Create a project, add permissions and
 * register this service in AndroidManifest, then start it from your app.
 */
class TrackingService : Service() {
    private lateinit var fused: FusedLocationProviderClient
    private val http = OkHttpClient()

    // TODO: Configure these for your server and device
    private val serverRoot = "http://192.168.8.152:5000"
    private val devicePhone = "+263771112812" // or null and use IMEI if permitted
    private val deviceImei: String? = null // IMEI access is restricted on modern Android
    private val deviceToken = "DEVICE_TOKEN_FROM_DASHBOARD"

    override fun onCreate() {
        super.onCreate()
        fused = LocationServices.getFusedLocationProviderClient(this)
        startForegroundWithNotification()
        requestLocationUpdates()
    }

    private fun startForegroundWithNotification() {
        val channelId = "tracking_channel"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(channelId, "Tracking", NotificationManager.IMPORTANCE_LOW)
            (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(channel)
        }
        val notification: Notification = NotificationCompat.Builder(this, channelId)
            .setContentTitle("Location Tracking Active")
            .setContentText("Posting location updates to server")
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .build()
        startForeground(1001, notification)
    }

    private fun requestLocationUpdates() {
        val fine = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION)
        val coarse = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION)
        if (fine != PackageManager.PERMISSION_GRANTED && coarse != PackageManager.PERMISSION_GRANTED) {
            // Permissions must be granted by Activity before starting this service
            stopSelf()
            return
        }
        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 60_000L)
            .setMinUpdateIntervalMillis(30_000L)
            .build()
        fused.requestLocationUpdates(request, object : LocationCallback() {
            override fun onLocationResult(result: LocationResult) {
                val loc = result.lastLocation ?: return
                postLocation(loc.latitude, loc.longitude)
            }
        }, mainLooper)
    }

    private fun postLocation(lat: Double, lng: Double) {
        val url = "$serverRoot/api/location_update"
        val json = JSONObject().apply {
            if (deviceImei != null) put("imei", deviceImei)
            put("phone", devicePhone)
            put("lat", lat)
            put("lng", lng)
            put("token", deviceToken)
        }
        val body = RequestBody.create("application/json".toMediaType(), json.toString())
        val req = Request.Builder().url(url).post(body).build()
        http.newCall(req).enqueue(object : okhttp3.Callback {
            override fun onFailure(call: okhttp3.Call, e: java.io.IOException) {
                // noop: could log
            }
            override fun onResponse(call: okhttp3.Call, response: okhttp3.Response) {
                response.close()
            }
        })
    }

    override fun onBind(intent: Intent?): IBinder? = null
}

/* Minimal Activity example
// In your Activity:
// - Request location permissions
// - Start the TrackingService once permissions are granted

// AndroidManifest.xml additions:
// <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
// <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
// <uses-permission android:name="android.permission.INTERNET" />
// <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
// <application>
//   <service android:name=".TrackingService" android:exported="false" />
// </application>
*/