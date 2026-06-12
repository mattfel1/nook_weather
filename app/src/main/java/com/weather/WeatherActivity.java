package com.nookframe.weather;

import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.view.WindowManager;
import android.widget.ImageView;

import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Full-screen weather frame for the Nook Simple Touch (Android 2.1 / API 7).
 *
 * It paints itself ON TOP of the slide-to-unlock keyguard using
 * FLAG_SHOW_WHEN_LOCKED + FLAG_DISMISS_KEYGUARD, which dismisses the
 * (non-secure) keyguard without any touchscreen interaction. Combined with
 * the BootReceiver, it re-asserts itself after every reboot, so you never
 * have to ADB your way past the lock again.
 */
public class WeatherActivity extends Activity {

    // ---- CONFIG ----------------------------------------------------------
    // PLAIN HTTP ONLY. Android 2.1 has no TLS 1.2, so any https:// target
    // will fail to connect. Point this at your LAN weather server
    // (see server/weather-server.js), e.g.:
    private static final String IMAGE_URL = "http://192.168.2.247:8080/weather.png?o=landscape";
    // wttr.in alternative (often fails: it redirects http -> https):
    //   "http://wttr.in/Ottawa_0.png"

    private static final long REFRESH_MS = 15 * 60 * 1000L; // refresh every N min
    // ----------------------------------------------------------------------

    private static final int WINDOW_FLAGS =
              WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
            | WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD
            | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
            | WindowManager.LayoutParams.FLAG_FULLSCREEN;

    private ImageView imageView;
    private final Handler handler = new Handler();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Eclair/Froyo HttpURLConnection has a connection-reuse bug; disable
        // keep-alive so repeated fetches don't go stale.
        System.setProperty("http.keepAlive", "false");

        getWindow().addFlags(WINDOW_FLAGS);

        imageView = new ImageView(this);
        imageView.setScaleType(ImageView.ScaleType.FIT_CENTER);
        imageView.setBackgroundColor(Color.WHITE);
        setContentView(imageView);

        refreshLoop.run(); // fetch immediately, then on the timer
    }

    @Override
    protected void onResume() {
        super.onResume();
        getWindow().addFlags(WINDOW_FLAGS);
        fetchAndShow();   // <-- add this: every visit = instant refresh
    }

    @Override
    protected void onNewIntent(android.content.Intent intent) {
        super.onNewIntent(intent);
        getWindow().addFlags(WINDOW_FLAGS);
        fetchAndShow();   // re-fetch when n-button re-enters us
    }

    private final Runnable refreshLoop = new Runnable() {
        public void run() {
            fetchAndShow();
            handler.postDelayed(this, REFRESH_MS);
        }
    };

    private void fetchAndShow() {
        new Thread(new Runnable() {
            public void run() {
                final Bitmap bmp = downloadBitmap(IMAGE_URL);
                if (bmp != null) {
                    handler.post(new Runnable() {
                        public void run() {
                            imageView.setImageBitmap(bmp);
                        }
                    });
                }
            }
        }).start();
    }

    private static Bitmap downloadBitmap(String urlStr) {
        HttpURLConnection conn = null;
        InputStream in = null;
        try {
            URL url = new URL(urlStr);
            conn = (HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(15000);
            conn.setReadTimeout(15000);
            conn.setInstanceFollowRedirects(true);
            conn.connect();
            in = conn.getInputStream();
            return BitmapFactory.decodeStream(in);
        } catch (Exception e) {
            // Network down, server off, TLS target, etc. Keep the last image up.
            return null;
        } finally {
            try { if (in != null) in.close(); } catch (Exception ignored) {}
            if (conn != null) conn.disconnect();
        }
    }
}
