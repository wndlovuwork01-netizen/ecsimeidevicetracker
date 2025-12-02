package com.example.agent

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

class MainActivity : AppCompatActivity() {

    private lateinit var imeiInput: EditText
    private lateinit var phoneInput: EditText
    private lateinit var tokenInput: EditText
    private lateinit var statusText: TextView
    private lateinit var btnValidate: Button
    private lateinit var btnStart: Button
    private lateinit var btnStop: Button

    private lateinit var sharedPrefs: SharedPreferences

    private val TAG = "MainActivity"
    private val serverRoot = "http://192.168.1.11:5000"
    private val client = OkHttpClient()

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val fine = permissions[Manifest.permission.ACCESS_FINE_LOCATION] ?: false
        val coarse = permissions[Manifest.permission.ACCESS_COARSE_LOCATION] ?: false
        val background =
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q)
                permissions[Manifest.permission.ACCESS_BACKGROUND_LOCATION] ?: false
            else true

        if (fine && coarse && background) startTrackingService()
        else Toast.makeText(this, "Permissions are required", Toast.LENGTH_SHORT).show()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        // Initialize UI elements
        imeiInput = findViewById(R.id.imeiEditText)
        phoneInput = findViewById(R.id.phoneEditText)
        tokenInput = findViewById(R.id.tokenEditText)
        statusText = findViewById(R.id.statusText)
        btnValidate = findViewById(R.id.btnValidate)
        btnStart = findViewById(R.id.btnStart)
        btnStop = findViewById(R.id.btnStop)

        // EncryptedSharedPreferences
        val masterKey = MasterKey.Builder(this)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()

        sharedPrefs = EncryptedSharedPreferences.create(
            this,
            "agent_prefs",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )

        // Load saved credentials if available
        loadSavedCredentials()

        // Button listeners
        btnValidate.setOnClickListener { validateCredentials() }
        btnStart.setOnClickListener { checkPermissionsAndStartService() }
        btnStop.setOnClickListener { stopTrackingService() }

        // Check permissions on start
        checkPermissionsAndStartService()
    }

    private fun loadSavedCredentials() {
        imeiInput.setText(sharedPrefs.getString("imei", ""))
        phoneInput.setText(sharedPrefs.getString("phone", ""))
        tokenInput.setText(sharedPrefs.getString("token", ""))
    }

    private fun saveCredentials(imei: String, phone: String, token: String) {
        sharedPrefs.edit().apply {
            putString("imei", imei)
            putString("phone", phone)
            putString("token", token)
            apply()
        }
    }

    private fun checkPermissionsAndStartService() {
        val required = mutableListOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q)
            required.add(Manifest.permission.ACCESS_BACKGROUND_LOCATION)

        val missing = required.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (missing.isEmpty()) startTrackingService()
        else permissionLauncher.launch(missing.toTypedArray())
    }

    private fun startTrackingService() {
        val intent = Intent(this, TrackingService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            startForegroundService(intent)
        else startService(intent)
        statusText.text = "Status: Tracking service started"
    }

    private fun stopTrackingService() {
        val intent = Intent(this, TrackingService::class.java)
        stopService(intent)
        statusText.text = "Status: Tracking service stopped"
    }

    private fun validateCredentials() {
        val imei = imeiInput.text.toString().trim()
        val phone = phoneInput.text.toString().trim()
        val token = tokenInput.text.toString().trim()

        if (imei.isEmpty() || phone.isEmpty() || token.isEmpty()) {
            Toast.makeText(this, "All fields are required", Toast.LENGTH_SHORT).show()
            return
        }

        val json = JSONObject().apply {
            put("imei", imei)
            put("phone", phone)
            put("token", token)
        }

        val body = json.toString().toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url("$serverRoot/api/validate_device")
            .post(body)
            .build()

        client.newCall(request).enqueue(object : okhttp3.Callback {
            override fun onFailure(call: okhttp3.Call, e: java.io.IOException) {
                runOnUiThread {
                    statusText.text = "Status: Validation failed (network error)"
                    Toast.makeText(this@MainActivity, "Network error", Toast.LENGTH_SHORT).show()
                }
            }

            override fun onResponse(call: okhttp3.Call, response: okhttp3.Response) {
                val respBody = response.body?.string()
                response.close()

                runOnUiThread {
                    if (response.isSuccessful) {
                        statusText.text = "Status: Device validated!"
                        Toast.makeText(this@MainActivity, "Validation successful", Toast.LENGTH_SHORT).show()
                        saveCredentials(imei, phone, token)
                    } else {
                        statusText.text = "Status: Validation failed (server)"
                        Toast.makeText(this@MainActivity, "Invalid credentials", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        })
    }
}
