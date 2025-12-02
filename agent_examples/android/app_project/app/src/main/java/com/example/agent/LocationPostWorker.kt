package com.example.agent

import android.content.Context
import android.util.Log
import androidx.work.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

class LocationPostWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    private val TAG = "LocationPostWorker"
    private val client = OkHttpClient()

    override suspend fun doWork(): Result {
        val serverRoot = inputData.getString("serverRoot") ?: return Result.failure()
        val lat = inputData.getDouble("lat", 0.0)
        val lng = inputData.getDouble("lng", 0.0)

        // ALWAYS load fresh saved credentials
        val masterKey = MasterKey.Builder(applicationContext)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()

        val prefs = EncryptedSharedPreferences.create(
            applicationContext,
            "agent_prefs",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )

        val imei = prefs.getString("imei", "") ?: ""
        val phone = prefs.getString("phone", "") ?: ""
        val token = prefs.getString("token", "") ?: ""

        val json = JSONObject().apply {
            put("imei", imei)
            put("phone", phone)
            put("lat", lat)
            put("lng", lng)
            put("token", token)
        }

        val url = "$serverRoot/api/location_update"
        val body = json.toString().toRequestBody("application/json".toMediaType())
        val request = Request.Builder().url(url).post(body).build()

        return try {
            val response = client.newCall(request).execute()
            val code = response.code
            response.close()
            if (code in 200..299) Result.success()
            else Result.retry()
        } catch (e: Exception) {
            Log.e(TAG, "POST failed, scheduling retry", e)
            Result.retry()
        }
    }

    companion object {
        fun enqueue(
            context: Context,
            serverRoot: String,
            lat: Double,
            lng: Double,

        ) {
            val data = workDataOf(
                "serverRoot" to serverRoot,
                "lat" to lat,
                "lng" to lng,
            )

            val request = OneTimeWorkRequestBuilder<LocationPostWorker>()
                .setInputData(data)
                .setBackoffCriteria(
                    BackoffPolicy.EXPONENTIAL,
                    15, TimeUnit.SECONDS
                )
                .build()

            WorkManager.getInstance(context).enqueue(request)
        }
    }
}
