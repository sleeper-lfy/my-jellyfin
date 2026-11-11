package net.lumen.media;

import android.content.Context;
import android.view.ContextThemeWrapper;
import com.google.android.material.button.MaterialButton;

/** Actual Material 3 View button for pages that retain Java Button state APIs. */
final class NativeActionButton extends MaterialButton {
    private final boolean dark;
    NativeActionButton(Context context,boolean dark){
        this(context,dark,false);
    }
    NativeActionButton(Context context,boolean dark,boolean cardIcon){
        super(new ContextThemeWrapper(context,cardIcon?(dark?R.style.LumenNativeCardIconsDark:R.style.LumenNativeCardIconsLight):(dark?R.style.LumenNativeActionsDark:R.style.LumenNativeActionsLight)),null,com.google.android.material.R.attr.materialButtonStyle);
        this.dark=dark;
    }
    boolean isDarkTheme(){return dark;}
}
