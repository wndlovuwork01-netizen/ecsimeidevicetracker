package com.example.agent

import android.Manifest
import android.app.*
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.google.android.gms.location.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec
import android.os.PowerManager


class TrackingService : Service() {

    private lateinit var fused: FusedLocationProviderClient
    private val client = OkHttpClient()
    private val TAG = "TrackingService"

    private var serverRoot = "http://192.168.1.11:5000"

    private var deviceImei: String = ""
    private var devicePhone: String = ""
    private var deviceToken: String = ""

    override fun onCreate() {
        super.onCreate()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val pm = getSystemService(PowerManager::class.java)
            if (!pm.isIgnoringBatteryOptimizations(packageName)) {
                val intent = Intent().apply {
                    action = android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS
                    data = android.net.Uri.parse("package:$packageName")
                }
                intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK
                startActivity(intent)
            }
        }
        // Read credentials from EncryptedSharedPreferences
        loadCredentials()

        fused = LocationServices.getFusedLocationProviderClient(this)
        startForegroundWithNotification()
        requestLocationUpdates()
    }

    /**
     * Load credentials securely stored by MainActivity
     */
    private fun loadCredentials() {
        val masterKey = MasterKey.Builder(this)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()

        val prefs = EncryptedSharedPreferences.create(
            this,
            "agent_prefs",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )

        deviceImei = prefs.getString("imei", "") ?: ""
        devicePhone = prefs.getString("phone", "") ?: ""
        deviceToken = prefs.getString("token", "") ?: ""
    }

    /**
     * Start foreground notification for service
     */
    private fun startForegroundWithNotification() {
        val channelId = "tracking_channel"

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "Location Tracking",
                NotificationManager.IMPORTANCE_LOW
            )
            val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            manager.createNotificationChannel(channel)
        }

        val notification: Notification = NotificationCompat.Builder(this, channelId)
            .setContentTitle("Location Tracking Active")
            .setContentText("Posting location updates to server")
            .setSmallIcon(R.mipmap.ic_launcher)
            .setOngoing(true)
            .build()

        startForeground(1001, notification)
    }

    /**
     * Request real GPS location updates
     */
    private fun requestLocationUpdates() {
        val fine = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION)
        val coarse =
            ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION)

        if (fine != PackageManager.PERMISSION_GRANTED && coarse != PackageManager.PERMISSION_GRANTED) {
            stopSelf()
            return
        }

        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 60000L)
            .setMinUpdateIntervalMillis(30000L)
            .build()

        fused.requestLocationUpdates(
            request,
            object : LocationCallback() {
                override fun onLocationResult(result: LocationResult) {
                    val loc = result.lastLocation ?: return
                    postLocation(loc.latitude, loc.longitude)
                }
            },
            Looper.getMainLooper()
        )
    }

    /**
     * Post location with optional AES encryption
     */
    private fun postLocation(lat: Double, lng: Double) {
        // Use WorkManager for reliable background POST
        LocationPostWorker.enqueue(
            context = this,
            serverRoot = serverRoot,
            lat = lat,
            lng = lng,
        )

        Log.d(TAG, "Scheduled location POST via WorkManager: lat=$lat lng=$lng")
    }

    /**
     * Optional AES-256 encryption
     */
    private fun aesEncrypt(input: String): String {
        return try {
            val keyGen = KeyGenerator.getInstance("AES")
            keyGen.init(256)
            val key = keyGen.generateKey()

            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            val iv = ByteArray(12) // 12 bytes IV for GCM
            cipher.init(Cipher.ENCRYPT_MODE, key, GCMParameterSpec(128, iv))
            val encrypted = cipher.doFinal(input.toByteArray(Charsets.UTF_8))

            android.util.Base64.encodeToString(encrypted, android.util.Base64.NO_WRAP)
        } catch (e: Exception) {
            Log.e(TAG, "AES encryption failed", e)
            input
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    /**
     * Ensure service restarts after being killed
     */
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        return START_STICKY
    }

    /**
     * Ensure tracking restarts after task is removed
     */
    override fun onTaskRemoved(rootIntent: Intent?) {
        val restartServiceIntent = Intent(applicationContext, TrackingService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            startForegroundService(restartServiceIntent)
        else
            startService(restartServiceIntent)

        super.onTaskRemoved(rootIntent)
    }
}
