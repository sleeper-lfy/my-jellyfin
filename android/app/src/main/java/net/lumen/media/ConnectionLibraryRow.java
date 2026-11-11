package net.lumen.media;

import android.content.Context;
import android.content.res.ColorStateList;
import android.text.TextUtils;
import android.view.ContextThemeWrapper;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.core.graphics.ColorUtils;
import com.google.android.material.card.MaterialCardView;
import net.lumen.media.ui.theme.NativeActionTokens;

/** One inset text column keeps a library name and its address aligned. */
final class ConnectionLibraryRow extends MaterialCardView {
    ConnectionLibraryRow(Context context,String title,String address,int icon,Runnable action){
        super(new ContextThemeWrapper(context,R.style.LumenNativeActionsDark));
        setCardElevation(0);setStrokeWidth(0);setRadius(0);setUseCompatPadding(false);setPreventCornerOverlap(false);
        setCardBackgroundColor(NativeActionTokens.surfaceContainer(true));
        setRippleColor(ColorStateList.valueOf(ColorUtils.setAlphaComponent(NativeActionTokens.primary(true),31)));
        setClickable(true);setFocusable(true);setOnClickListener(view->action.run());
        setContentDescription(address.isEmpty()?title:title+" · "+address);

        LinearLayout content=new LinearLayout(context);content.setGravity(Gravity.CENTER_VERTICAL);
        content.setMinimumHeight(dp(64));
        content.setPaddingRelative(dp(NativeActionTokens.spaceLgDp()),dp(NativeActionTokens.spaceSmDp()),dp(NativeActionTokens.spaceLgDp()),dp(NativeActionTokens.spaceSmDp()));
        ImageView symbol=icon(context,icon,"connectionLibraryIcon");
        content.addView(symbol,new LinearLayout.LayoutParams(dp(NativeActionTokens.iconDp()),dp(NativeActionTokens.iconDp())));

        LinearLayout labels=new LinearLayout(context);labels.setOrientation(LinearLayout.VERTICAL);labels.setTag("connectionLibraryText");
        TextView name=text(context,title,NativeActionTokens.bodyMediumSp(),NativeActionTokens.onSurface(true));name.setTag("connectionLibraryName");name.setMaxLines(2);
        labels.addView(name,new LinearLayout.LayoutParams(-1,-2));
        if(!address.isEmpty()){
            TextView location=text(context,address,NativeActionTokens.labelMediumSp(),NativeActionTokens.onSurfaceVariant(true));location.setTag("connectionLibraryAddress");location.setMaxLines(2);location.setTextDirection(View.TEXT_DIRECTION_LTR);
            LinearLayout.LayoutParams size=new LinearLayout.LayoutParams(-1,-2);size.topMargin=dp(NativeActionTokens.spaceXsDp());labels.addView(location,size);
        }
        LinearLayout.LayoutParams textSize=new LinearLayout.LayoutParams(0,-2,1);textSize.setMarginStart(dp(NativeActionTokens.spaceMdDp()));content.addView(labels,textSize);
        ImageView arrow=icon(context,R.drawable.bili_chevron_right,"connectionLibraryArrow");arrow.getDrawable().setAutoMirrored(true);
        LinearLayout.LayoutParams arrowSize=new LinearLayout.LayoutParams(dp(NativeActionTokens.iconDp()),dp(NativeActionTokens.iconDp()));arrowSize.setMarginStart(dp(NativeActionTokens.spaceSmDp()));content.addView(arrow,arrowSize);
        addView(content,new FrameLayout.LayoutParams(-1,-2));
    }
    private int dp(float value){return MediaStyle.dp(getContext(),value);}
    private static TextView text(Context context,String value,float size,int color){
        TextView text=new TextView(context);text.setText(value);text.setTextSize(size);text.setTextColor(color);text.setIncludeFontPadding(false);text.setEllipsize(TextUtils.TruncateAt.END);text.setGravity(Gravity.START);text.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);return text;
    }
    private static ImageView icon(Context context,int resource,String tag){
        ImageView icon=new ImageView(context);icon.setImageResource(resource);icon.setImageTintList(ColorStateList.valueOf(NativeActionTokens.onSurfaceVariant(true)));icon.setTag(tag);icon.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);return icon;
    }
}
