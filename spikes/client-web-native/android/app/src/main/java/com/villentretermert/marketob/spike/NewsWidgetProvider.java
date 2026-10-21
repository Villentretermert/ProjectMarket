package com.villentretermert.marketob.spike;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.widget.RemoteViews;
import java.text.DateFormat;
import java.util.Date;

/** Public synthetic fixtures only; product access/TTL belongs to PM-020. */
public class NewsWidgetProvider extends AppWidgetProvider {
    static final String PREFS = "marketob_demo_widget";

    static int refresh(Context context) {
        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        int[] ids = manager.getAppWidgetIds(new ComponentName(context, NewsWidgetProvider.class));
        render(context, manager, ids);
        return ids.length;
    }

    @Override public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        render(context, manager, ids);
    }

    private static void render(Context context, AppWidgetManager manager, int[] ids) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        long updated = prefs.getLong("updated", 0);
        for (int id : ids) {
            RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.news_widget);
            views.setTextViewText(R.id.widget_headline_one, prefs.getString("headline0", "Open the app to load demo news"));
            views.setTextViewText(R.id.widget_headline_two, prefs.getString("headline1", ""));
            views.setTextViewText(R.id.widget_updated, updated == 0 ? "Demo cache is empty" : "Cached " + DateFormat.getTimeInstance(DateFormat.SHORT).format(new Date(updated)));
            Intent open = new Intent(context, MainActivity.class)
                .setAction(Intent.ACTION_VIEW).setData(Uri.parse("marketob-demo://channel/news"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            PendingIntent click = PendingIntent.getActivity(context, id, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            views.setOnClickPendingIntent(R.id.widget_root, click);
            manager.updateAppWidget(id, views);
        }
    }
}
