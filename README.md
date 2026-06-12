# NookFrame — a wall weather frame for the Nook Simple Touch

Turns a Nook Simple Touch (Android 2.1) with a **dead touchscreen** into an
always-on e-ink weather display. The trick: instead of trying to *remove* the
slide-to-unlock keyguard (which is baked into the 2.1 framework and ignores the
usual settings), this app paints itself **on top of** the keyguard with
`FLAG_SHOW_WHEN_LOCKED | FLAG_DISMISS_KEYGUARD`, which dismisses the
(non-secure) keyguard with zero touch input. A boot receiver brings it back
after every reboot.

## What's here

- `app/` — the Android app (the keyguard-killer + image display)
- `server/weather-server.js` — a tiny Node/Express server that renders an
  e-ink-friendly weather PNG and serves it over plain HTTP

## The one big gotcha: TLS

Android 2.1 has **no TLS 1.2**, so the Nook cannot fetch anything over
`https://`. Almost every weather URL today (including wttr.in, which redirects
http→https) will therefore fail *on the device*. Two ways around it:

1. **Recommended — run the companion server on your LAN.** Your PC/NAS does the
   HTTPS call to the weather API; the Nook only talks plain HTTP to your server.
   Robust, and you control exactly how the e-ink screen looks.
2. **Try wttr.in directly** by setting `IMAGE_URL` to `http://wttr.in/Ottawa_0.png`.
   It *may* work if it doesn't force a redirect, but don't count on it.

## Build the app

Toolchain that's comfortable with the very low `minSdk`: **AGP 7.0.4 / Gradle
7.2 / build-tools 30.0.3** (newer usually works too).

Option A — Android Studio: open the `nookframe/` folder, let it sync, then
Build > Build APK.

Option B — command line:
```
cd nookframe
gradle wrapper --gradle-version 7.2   # generates ./gradlew if you don't have it
./gradlew assembleDebug
```
The APK lands at `app/build/outputs/apk/debug/app-debug.apk`.

> **Signing:** the Nook only understands v1 (JAR) signatures. Debug builds
> include v1 automatically for `minSdk < 24`, so the debug APK installs as-is.
> If you make a release build, sign it with `apksigner` and keep **v1 enabled**.
>
> **Don't raise `minSdk`.** If the build ever complains, fix the toolchain —
> not the minSdk. A manifest `minSdk > 7` makes the Nook reject the APK outright.

## Install and test

With the Nook connected (USB or your existing ADB-over-WiFi):
```
./adb.exe install -r app/build/outputs/apk/debug/app-debug.apk
./adb.exe shell am start -n com.nookframe.weather/.WeatherActivity
```
Moment of truth: the keyguard should vanish and the weather image should appear,
no touchscreen needed. From now on it also relaunches itself on every boot.

If you only see a white screen, the app is running but can't reach the image URL
(server not up yet, or a TLS/https target). Fix the URL/server and it'll fill in
on the next 15-minute refresh (or just relaunch the activity).

## Run the weather server

```
cd nookframe/server
npm init -y
npm install express canvas
node weather-server.js
```
Find your machine's LAN IP (`ipconfig` on Windows / `ip addr` on Linux), then set
this near the top of `WeatherActivity.java` and rebuild:
```java
private static final String IMAGE_URL = "http://192.168.1.50:8080/weather.png";
```
Keep the server running on a machine that's always on. Open
`http://<that-ip>:8080/weather.png` in a browser to confirm it renders.

## Tuning

- **Refresh rate:** `REFRESH_MS` in `WeatherActivity.java` (default 15 min). E-ink
  has no cost to staying on, but don't hammer the weather API.
- **Layout / city:** edit `renderPng()` and `LAT`/`LON`/`LABEL` in
  `weather-server.js`. Big black text on white is ideal for E-Ink.
- **Power:** leave it on the charger permanently; `FLAG_KEEP_SCREEN_ON` plus the
  `screen_off_timeout = -1` you already set keeps it awake.
- **E-Ink ghosting:** if faint old text builds up, the Nook's framework usually
  does a full refresh on a full-bitmap swap; if it bothers you, occasionally
  render an all-white then the real frame. The advanced route is the Nook's
  `N2EpdController` via reflection — overkill for most.
