# Android Agent (Example Scaffold)

This is a minimal example showing how a consented Android agent can post location updates to your server’s `/api/location_update` endpoint.

Important: Obtain explicit user consent, show a persistent notification when tracking, and provide an easy opt-out. Follow platform policies and local regulations.

## Kotlin Snippet (Posting Location)
```kotlin
// build.gradle (app)
// implementation("com.squareup.okhttp3:okhttp:4.12.0")
// implementation("com.google.android.gms:play-services-location:21.3.0")

class LocationPoster(private val context: Context) {
  private val client = OkHttpClient()
  private val fused = LocationServices.getFusedLocationProviderClient(context)

  fun postLastLocation(imei: String?, phone: String) {
    val req = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 10_000).build()
    fused.getCurrentLocation(Priority.PRIORITY_HIGH_ACCURACY, CancellationTokenSource().token)
      .addOnSuccessListener { loc ->
        if (loc != null) {
          val json = """
            {"imei": ${jsonValue(imei)}, "phone": "${phone}", "lat": ${loc.latitude}, "lng": ${loc.longitude}}
          """.trimIndent()
          val body = json.toRequestBody("application/json".toMediaType())
          val req = Request.Builder()
            .url("http://YOUR_SERVER_HOST:5000/api/location_update")
            .post(body)
            .build()
          client.newCall(req).enqueue(object: Callback {
            override fun onFailure(call: Call, e: IOException) {}
            override fun onResponse(call: Call, response: Response) { response.close() }
          })
        }
      }
  }

  private fun jsonValue(s: String?): String = if (s == null) "null" else "\"$s\""
}
```

## Permissions and Consent
- Request `ACCESS_FINE_LOCATION` and `ACCESS_COARSE_LOCATION` at runtime.
- Display transparent consent explaining tracking purpose.
- Keep a foreground service with persistent notification when tracking is active.

## Install Link
Send users an SMS with your `AGENT_DOWNLOAD_URL` from the web dashboard once Vonage is configured.

## Notes
- Replace `YOUR_SERVER_HOST` with the server address reachable by the device.
- Consider posting periodically using WorkManager and exponential backoff.
- Secure your endpoint with auth tokens bound to enrolled devices.