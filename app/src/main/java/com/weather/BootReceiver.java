package com.nookframe.weather;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/**
 * Relaunches WeatherActivity on every boot, so the frame comes back (and the
 * keyguard gets dismissed again) after a reboot or power blip without you
 * having to touch ADB.
 */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        Intent i = new Intent(context, WeatherActivity.class);
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        context.startActivity(i);
    }
}
