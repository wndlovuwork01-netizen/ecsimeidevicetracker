Android Agent Project (Ready-to-Build)
======================================

This is a minimal Android Studio project that starts a foreground service to post location updates to your server’s `/api/location_update` endpoint.

What’s included
- Kotlin `MainActivity` that requests location permissions and starts `TrackingService`.
- Kotlin `TrackingService` that uses FusedLocationProvider to send updates via OkHttp.
- Manifest with required permissions and service registration.

Configure
- Open the project in Android Studio.
- Edit `app/src/main/java/com/example/agent/TrackingService.kt`:
  - `serverRoot = "http://YOUR_SERVER_HOST:5000"` (or your public HTTPS URL)
  - `devicePhone = "+263..."` (or set `deviceImei` if permitted)
  - `deviceToken = "DEVICE_TOKEN_FROM_DASHBOARD"`

Build and Install
1) Open this folder (`app_project`) in Android Studio.
2) Let Gradle sync.
3) Run “Build > Make Project”, then “Run” on a connected device.
4) Grant location permission when prompted.
5) You’ll see a “Location Tracking Active” notification, and the app will post updates periodically.

Notes
- IMEI access is restricted; prefer phone number or a generated device ID.
- For posting after reboot, add a BOOT_COMPLETED receiver.
- Use HTTPS in production.