# NookFrame

A wall-mounted weather display, repurposed from a Nook Simple Touch Glow with a dead touchscreen.

Built ~June 2026. This README is written for future-Matt who has forgotten everything.

---

## What this is

A 14-year-old e-reader (Nook Simple Touch Glow, ~2011, Android 2.1) shows current weather and a 3-day forecast on its e-ink screen, hung by the front door. Power is supplied permanently via a wall charger. A small Python server on the Pi-hole fetches weather from Open-Meteo, renders a PNG, and serves it over plain HTTP. The Nook fetches that PNG every 15 minutes.

The touchscreen on the device is fully dead. All maintenance happens via ADB over USB or WiFi. There is no way to interact with the Nook except through code.

## High-level architecture

```
+-----------------+         HTTPS         +--------------+
|  Open-Meteo API |  <------------------  | Pi-hole      |
|  (free, no key) |                       | (Python +    |
+-----------------+                       |  Pillow)     |
                                          +------+-------+
                                                 |
                                       HTTP :8080| weather.png
                                                 |
                                          +------v-------+
                                          | Nook on WiFi |
                                          | Custom APK   |
                                          | every 15 min |
                                          +--------------+
```

The Pi does the HTTPS hop because the Nook can't (Android 2.1 has no TLS 1.2). The Nook only ever speaks plain HTTP, on the LAN.

## Repo layout

```
nookframe/
├── README.md                      <- this file
├── settings.gradle
├── build.gradle                   <- root, AGP version
├── app/
│   ├── build.gradle               <- the one with android { ... }
│   └── src/main/
│       ├── AndroidManifest.xml
│       └── java/com/nookframe/weather/
│           ├── WeatherActivity.java   <- the whole app
│           └── BootReceiver.java      <- self-relaunch on boot
└── server/
    └── weather-server.py          <- Python server on the Pi
```

The CWM SD card (physical) is the disaster-recovery snapshot. Don't lose it.

---

## How the app works

`WeatherActivity.java` does three things:

1. Paints itself over the slide-to-unlock keyguard using window flags `FLAG_SHOW_WHEN_LOCKED | FLAG_DISMISS_KEYGUARD | FLAG_KEEP_SCREEN_ON | FLAG_FULLSCREEN`. **This is the only thing that gets past the lock screen on Android 2.1.** Without it, the slide-to-unlock blocks the whole device. SQLite edits to `lockscreen.disabled`, ADB settings commands, and NTMM XML edits all failed — only painting over with these flags works.
2. Fetches `IMAGE_URL` every `REFRESH_MS` (default 15 minutes) and on every `onResume` / `onNewIntent`.
3. Displays the PNG full-screen.

`BootReceiver.java` listens for `BOOT_COMPLETED` and re-launches the activity. This is the self-healing mechanism — power blip, router reboot, anything kicks the device, and it comes back to weather on its own.

`AndroidManifest.xml` claims `category.HOME` so the n button (hardwired to fire HOME) lands on the app instead of a launcher.

## The big "don'ts" (hard-won)

These are things that broke things during development:

- **Don't disable any system packages besides `org.adwfreak.launcher`.** Disabling `com.home.nmyshkin.nstweather`, `com.home.nmyshkin.quicktiles`, `com.home.nmyshkin.glgesture`, `com.home.nmyshkin.setcover`, or `com.bn.nook.home` caused cascading failures and a boot loop.
- **Don't raise `minSdk` above 7.** The Nook will refuse to install the APK. Android Studio may suggest "you should target a higher SDK" — ignore.
- **Don't upgrade Gradle Plugin past AGP 7.1.3.** Newer AGPs may drop minSdk 7 entirely. The toolchain we use: AGP 7.1.3, Gradle 7.2, JDK 17, build-tools 30.
- **Don't use JDK 21 or higher for Gradle.** AGP 7.1.3 won't build with it. Set Studio's Gradle JDK to 17 (Settings → Build → Gradle → Gradle JDK).
- **Don't trust `am force-stop`** — doesn't exist on Android 2.1.
- **Don't edit NTMM's prefs XML and expect changes to apply.** NTMM caches its config; XML edits get ignored. This burned us twice.
- **Don't use `https://` for the Nook's image URL.** Android 2.1 has no TLS 1.2. wttr.in seems tempting but force-redirects to https.
- **Don't deploy from Studio as an App Bundle.** Bundletool variant-matching fails on the Nook's density. Use plain APK deploys.

## The big "do"s

- **Always have the CWM SD card on hand.** It's the only true safety net. Restore via boot-from-SD if you brick the device.
- **Keep `org.adwfreak.launcher` disabled** (`pm disable org.adwfreak.launcher`). This is the only system change needed to make the n button land on the weather app.
- **Set Studio's Before-Launch external tool to `adb uninstall com.nookframe.weather`** so iteration is clean. Studio's built-in "terminate" step doesn't work on Android 2.1.
- **When the USB cable is plugged in, the screen shows a USB Mode overlay** that hides whatever the app is drawing. This is normal. On a plain wall charger (no data lines), the overlay never appears.

---

## Recovery: when it stops working

### Symptom: Nook screen is blank but device is powered

1. Server isn't reachable. SSH to the Pi: `systemctl status nookframe` — if it's not running, `sudo systemctl restart nookframe`.
2. Server is up but the Nook's WiFi is sleeping. Plug USB in, `./adb.exe shell ip addr` — if no `inet` on `tiwlan0`, do `./adb.exe shell svc wifi disable && ./adb.exe shell svc wifi enable`.
3. App crashed. `./adb.exe shell ps | grep nookframe` — if empty, `./adb.exe shell am start -n com.nookframe.weather/.WeatherActivity` to relaunch. Then reboot the Nook so the BootReceiver re-arms.

### Symptom: Nook is stuck in a boot loop

The hardest scenario. CWM is your recovery.

1. Hold power ~10 seconds to force off
2. Insert the CWM SD card
3. Power on — it boots into CWM
4. Use the page-turn buttons (up/down) and the **n** button (select) to navigate (touchscreen is dead but CWM uses hardware buttons)
5. **backup and restore → restore → pick the Phase 3 backup**
6. Confirm; wait for the bars
7. **reboot system now**; pull the SD card while the BNRV logo is showing

After restore, you have a clean Phase 3 system. To re-deploy NookFrame:
- Rebuild APK in Studio (`Build → Build APK`)
- `./adb.exe install -r app-debug.apk`
- `./adb.exe shell am start -n com.nookframe.weather/.WeatherActivity` (this also dismisses the keyguard via the window flags)
- `./adb.exe shell pm disable org.adwfreak.launcher` to make HOME land on the app
- Done. Don't touch anything else.

### Symptom: WiFi changed (e.g. you moved)

The Nook has no UI for entering credentials. Update over USB-ADB:

```
./adb.exe pull /data/misc/wifi/wpa_supplicant.conf .
```

Open the file in Notepad. Replace or add a `network={...}` block:

```
network={
    ssid="YourNewNetworkName"
    psk="YourNewPassword"
    key_mgmt=WPA-PSK
    priority=1
}
```

The Nook only supports **2.4GHz, 802.11b/g, WPA2-PSK (AES or TKIP)**. It does **not** support 5GHz, 802.11n, or WPA3. If your new router is WPA3-only, enable a dedicated 2.4GHz WPA2 SSID for IoT devices and use that.

Then push and restart WiFi:

```
./adb.exe push wpa_supplicant.conf /data/misc/wifi/wpa_supplicant.conf
./adb.exe shell svc wifi disable
./adb.exe shell svc wifi enable
```

Wait 20 seconds, verify with `./adb.exe shell ip addr` — you want `inet 192.168.x.x` on `tiwlan0`.

### Symptom: Pi-hole's IP changed and the Nook is now showing the last image forever

Two fixes:
1. Set the Pi-hole's IP as a static lease in your router (the right answer).
2. Update `IMAGE_URL` in `WeatherActivity.java`, rebuild, reinstall.

### Symptom: Weather hasn't updated in ages

The PNG fetch silently fails on network errors and keeps the last image up. To force a refresh:
- Press the **n button** — fires HOME, lands on the app, `onResume` triggers an immediate fetch
- Or unplug power for 5 seconds, plug back in — BootReceiver re-launches the app, immediate fetch

If neither helps, the server is down or the Nook is offline — see the blank-screen section.

---

## Server (Python on Pi-hole)

### Lives at

`/home/pi/nookframe/weather-server.py`

### How it runs

A systemd service named `nookframe`. To control:

```
sudo systemctl status nookframe       # is it running?
sudo systemctl restart nookframe      # apply code changes
sudo systemctl stop nookframe         # disable temporarily
sudo systemctl start nookframe
journalctl -u nookframe -n 50         # recent logs
journalctl -u nookframe -f            # live logs
```

The unit file is at `/etc/systemd/system/nookframe.service`:

```ini
[Unit]
Description=NookFrame weather server
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/nookframe
ExecStart=/usr/bin/python3 /home/pi/nookframe/weather-server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Dependencies

- Python 3.6+ (preinstalled on Pi OS)
- Pillow (`sudo apt install python3-pil` — preinstalled on most Pi OS variants)
- Internet access (for the HTTPS hop to Open-Meteo)

No npm, no node-canvas, no compile step. This is the second iteration — the first was Node.js with node-canvas, which took an hour+ to compile on the Pi and never finished.

### Editing the layout

All visual stuff is in `weather-server.py`. The Nook doesn't render or know anything — it just fetches and shows the PNG. To iterate:

1. Edit `weather-server.py` on the Pi (`nano ~/nookframe/weather-server.py`)
2. `sudo systemctl restart nookframe`
3. Refresh in any browser: `http://<pi-ip>:8080/weather.png`
4. Nook picks up changes within 15 minutes, or press n for immediate refresh

URL params for live A/B compare in browser:
- `?o=portrait` — vertical
- `?o=landscape` — rotated for the panel (looks sideways in browser, correct on Nook)
- `?o=landscape-preview` — landscape un-rotated, for comfortable PC viewing

The Nook fetches `weather.png` with no params, so it gets whatever is set as `DEFAULT_ORIENTATION` at the top of the .py file. Same file has `LANDSCAPE_ROTATION = 'cw'` or `'ccw'` for which way the device is mounted.

### Timezone

The Pi's system timezone is set to `America/Toronto` (`sudo timedatectl set-timezone America/Toronto`). If the timestamp on the weather page is wrong, that's the thing to check. Run `timedatectl` to see current setting.

---

## App (Android, Java)

### Build environment

- Android Studio 2024.x or 2025.x
- Gradle JDK: **17** (NOT 21 or higher) — set via Settings → Build, Execution, Deployment → Build Tools → Gradle
- Gradle Plugin: **AGP 7.1.3** — don't upgrade
- Gradle wrapper: **7.2**
- minSdk: **7** — don't raise. The Nook will reject any APK with higher minSdk.

If Studio prompts to upgrade AGP, decline. If Studio's bundled JDK is 21+, it won't break compilation but may break Gradle if not overridden as above.

### Iteration workflow

Studio's Run button works with these prerequisites set up:

**Before Launch external tool** (Run → Edit Configurations → Before launch → + → Run External Tool):
- Name: `Uninstall NookFrame`
- Program: `C:\Users\feldm\Downloads\platform-tools-latest-windows\platform-tools\adb.exe`
- Arguments: `uninstall com.nookframe.weather`

This makes every Run a clean install instead of an in-place update, which sidesteps the broken-terminate problem on Android 2.1.

**Run config Deploy setting**: "Default APK" (NOT "APK from app bundle"). App bundle deploy fails on the Nook's density due to bundletool variant matching.

### What `IMAGE_URL` should be

In `WeatherActivity.java`:

```java
private static final String IMAGE_URL = "http://<pi-hole-ip>:8080/weather.png";
```

Must be `http://`, not `https://`. The Pi-hole IP should be a static-leased one in your router so it never changes.

### ADB

Tools live at: `C:\Users\feldm\Downloads\platform-tools-latest-windows\platform-tools\adb.exe`

USB mode just works — `./adb.exe devices` should show the Nook.

WiFi mode (handy when the Nook is wall-mounted):
```
./adb.exe tcpip 5555            # while still on USB
./adb.exe connect 192.168.2.233:5555
```

WiFi ADB mode resets on every Nook reboot. To re-enable, plug in USB and re-run the `tcpip 5555` step.

---

## Hardware reference

| Property | Value |
|---|---|
| Model | Nook Simple Touch with Glow (BNRV350) |
| Screen | 600×800, 6" E-Ink Pearl, front-lit |
| CPU | TI OMAP 3621, 800MHz |
| RAM | 256MB |
| OS | Android 2.1 Eclair (no TLS 1.2, no `am force-stop`, no `input swipe`) |
| WiFi | 802.11b/g, 2.4GHz only, no WPA3 |
| Touchscreen | DEAD. Do not rely on it for any reason. |
| Buttons that still work | Power, n button (HOME), page-turn buttons (act as up/down in CWM) |
| Power | Micro-USB. Plain wall chargers don't trigger USB Mode overlay. Data USB does. |
| OS image origin | XDA Phoenix Project Phase 3 (rooted, B&N removed, ADW Launcher, NTMM utilities) |

---

## Useful ADB commands reference

```
# Connection
./adb.exe devices
./adb.exe connect 192.168.2.233:5555

# App control
./adb.exe install -r app-debug.apk
./adb.exe uninstall com.nookframe.weather
./adb.exe shell am start -n com.nookframe.weather/.WeatherActivity

# Diagnostics
./adb.exe shell dumpsys window | findstr "mCurrentFocus"
./adb.exe shell ps | findstr nookframe
./adb.exe logcat -d -t 101
./adb.exe shell ip addr

# Network test from Nook
./adb.exe shell ping -c 3 192.168.2.101
./adb.exe shell wget -O /data/local/tmp/test.png http://192.168.2.101:8080/weather.png

# WiFi
./adb.exe shell svc wifi disable
./adb.exe shell svc wifi enable
./adb.exe pull /data/misc/wifi/wpa_supplicant.conf .

# Lifecycle
./adb.exe shell reboot

# Panic button (re-enable ADW if HOME claim breaks)
./adb.exe shell pm enable org.adwfreak.launcher
```

---

## What this project taught me

Mostly: software stacks from 2010-2011 are simultaneously fragile and immortal. The Nook will probably outlast everything around it by sheer indifference to modernity.

Also: when something doesn't work, check the USB Mode overlay first. Three separate times in development I was convinced the app was broken when actually the screen was just being hidden by the USB Mode dialog. On a wall charger (no data pins), it never appears.

Also: if a fix involves disabling a system package, disable exactly one and test before disabling another. Cascading disables are how you get a boot loop.

Finally: the CWM SD card is the most important physical artifact of this project. Without it, "I'll just experiment" becomes "I just bricked the device." With it, every disaster is reversible.

Happy hacking, future-me. Hope this one is still going by your front door.
