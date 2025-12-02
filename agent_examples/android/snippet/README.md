Android Location Snippet
=========================

What this is
- A minimal Kotlin foreground service (`TrackingService`) that collects location updates and posts them to your server’s `/api/location_update` endpoint.
- Intended to be dropped into a new Android Studio project and built as an APK you can install.

Server endpoint
- Expects JSON: `{ "imei": "optional", "phone": "+263...", "lat": 0.0, "lng": 0.0, "token": "..." }`
- Update your server root URL and token constants inside `LocationAgent.kt`.

Steps to use
1) Create a new Android Studio project (Empty Activity, Kotlin). Min SDK 23+ recommended.
2) Copy `snippet/LocationAgent.kt` into `app/src/main/java/<your package>/TrackingService.kt`.
3) Add permissions to `AndroidManifest.xml`:
   - `<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />`
   - `<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />`
   - `<uses-permission android:name="android.permission.INTERNET" />`
   - `<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />`
4) Register the service in `AndroidManifest.xml`:
   - `<service android:name=".TrackingService" android:exported="false" />`
5) In your `MainActivity`, request runtime location permissions, then start the service:
   - `startForegroundService(Intent(this, TrackingService::class.java))`
6) Set the constants in `TrackingService`:
   - `serverRoot = "http://YOUR_SERVER_HOST:5000"` (or your public URL)
   - `devicePhone = "+263..."` (or null and use IMEI where permitted)
   - `deviceToken = "DEVICE_TOKEN_FROM_DASHBOARD"`
7) Build and install the APK on the device. Once permissions granted, the service posts locations roughly every minute.

Notes
- IMEI access is restricted on modern Android; prefer a stable device ID or phone.
- For background posting after reboot, add a `BOOT_COMPLETED` receiver that restarts the service.
- If your server uses HTTPS with a self-signed cert, configure OkHttp to trust it or use a valid cert.