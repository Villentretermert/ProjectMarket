package com.villentretermert.marketob.spike;

import com.getcapacitor.BridgeActivity;
import android.os.Bundle;

public class MainActivity extends BridgeActivity {
    @Override public void onCreate(Bundle state) {
        registerPlugin(NewsWidgetPlugin.class);
        super.onCreate(state);
    }
}
