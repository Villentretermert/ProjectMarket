package com.villentretermert.marketob.spike;

import android.appwidget.AppWidgetManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Build;
import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "NewsWidget")
public class NewsWidgetPlugin extends Plugin {
    @PluginMethod public void publishDemoNews(PluginCall call) {
        JSArray headlines = call.getArray("headlines");
        if (headlines == null || headlines.length() < 1 || headlines.length() > 2) {
            call.reject("Expected one or two public demo headlines"); return;
        }
        String[] safe = new String[headlines.length()];
        for (int i = 0; i < headlines.length(); i++) {
            Object item = headlines.opt(i);
            if (!(item instanceof String) || ((String) item).trim().isEmpty() || ((String) item).length() > 120) {
                call.reject("Invalid demo headline"); return;
            }
            safe[i] = (String) item;
        }
        SharedPreferences.Editor editor = getContext().getSharedPreferences(NewsWidgetProvider.PREFS, Context.MODE_PRIVATE).edit().clear();
        for (int i = 0; i < safe.length; i++) editor.putString("headline" + i, safe[i]);
        // Only resolve once the local cache is durable; no private payload or token is stored.
        if (!editor.putLong("updated", System.currentTimeMillis()).commit()) { call.reject("Cache write failed"); return; }
        call.resolve(new JSObject().put("widgetCount", NewsWidgetProvider.refresh(getContext())));
    }

    @PluginMethod public void clear(PluginCall call) {
        if (!getContext().getSharedPreferences(NewsWidgetProvider.PREFS, Context.MODE_PRIVATE).edit().clear().commit()) {
            call.reject("Cache clear failed"); return;
        }
        NewsWidgetProvider.refresh(getContext()); call.resolve();
    }

    @PluginMethod public void requestPin(PluginCall call) {
        AppWidgetManager manager = AppWidgetManager.getInstance(getContext());
        boolean supported = Build.VERSION.SDK_INT >= 26 && manager.isRequestPinAppWidgetSupported();
        if (supported) manager.requestPinAppWidget(new ComponentName(getContext(), NewsWidgetProvider.class), null, null);
        call.resolve(new JSObject().put("supported", supported));
    }

    static String channelFromIntent(Intent intent) {
        Uri uri = intent == null ? null : intent.getData();
        if (uri == null || !"marketob-demo".equals(uri.getScheme()) || !"channel".equals(uri.getHost())) return "";
        if ("/news".equals(uri.getPath())) return "news";
        if ("/shop".equals(uri.getPath())) return "shop";
        return "";
    }

    @PluginMethod public void getLaunchChannel(PluginCall call) {
        call.resolve(new JSObject().put("channel", channelFromIntent(getActivity().getIntent())));
    }

    @Override protected void handleOnNewIntent(Intent intent) {
        super.handleOnNewIntent(intent);
        String channel = channelFromIntent(intent);
        if (!channel.isEmpty()) notifyListeners("openChannel", new JSObject().put("channel", channel), true);
    }
}
