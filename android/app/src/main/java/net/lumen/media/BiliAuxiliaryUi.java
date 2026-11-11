package net.lumen.media;

import android.app.Activity;
import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.text.TextUtils;
import android.view.ContextThemeWrapper;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import com.google.android.material.button.MaterialButton;
import com.google.android.material.card.MaterialCardView;
import net.lumen.media.ui.theme.NativeActionTokens;

/** Layout primitives scoped to the remote, update and computer-task pages. */
final class BiliAuxiliaryUi {
    private BiliAuxiliaryUi(){}
    static int dp(Context context,float value){return MediaStyle.dp(context,value);}
    static Context themed(Context context){return new ContextThemeWrapper(context,R.style.LumenNativeActionsDark);}
    static LinearLayout column(Context context){LinearLayout view=new LinearLayout(context);view.setOrientation(LinearLayout.VERTICAL);return view;}
    static LinearLayout row(Context context){LinearLayout view=new LinearLayout(context);view.setOrientation(LinearLayout.HORIZONTAL);view.setGravity(Gravity.CENTER_VERTICAL);return view;}
    static TextView text(Context context,String value,float size,int color){
        TextView text=new TextView(context);text.setText(value);text.setTextSize(size);text.setTextColor(color);text.setIncludeFontPadding(false);return text;
    }
    static TextView body(Context context,String value){return text(context,value,NativeActionTokens.bodySp(),NativeActionTokens.onSurface(true));}
    static TextView supporting(Context context,String value){return text(context,value,NativeActionTokens.supportingSp(),NativeActionTokens.onSurfaceVariant(true));}
    static TextView section(Context context,String value){TextView text=body(context,value);text.setTypeface(Typeface.DEFAULT,Typeface.BOLD);text.setPadding(0,dp(context,16),0,dp(context,8));return text;}
    static LinearLayout header(Activity activity,String title,Runnable back){
        LinearLayout header=row(activity);header.setMinimumHeight(dp(activity,56));
        PlaybackIconButton previous=new PlaybackIconButton(activity,"back",activity.getString(R.string.bili_aux_back));previous.setOnClickListener(v->back.run());header.addView(previous,new LinearLayout.LayoutParams(dp(activity,48),dp(activity,48)));
        TextView heading=text(activity,title,NativeActionTokens.titleSp(),NativeActionTokens.onSurface(true));heading.setTypeface(Typeface.DEFAULT,Typeface.BOLD);heading.setMaxLines(2);heading.setEllipsize(TextUtils.TruncateAt.END);header.addView(heading,new LinearLayout.LayoutParams(0,-2,1));return header;
    }
    static MaterialCardView card(Context context,String tag){
        MaterialCardView card=new MaterialCardView(themed(context));card.setTag(tag);card.setRadius(dp(context,NativeActionTokens.cardCornerDp()));card.setCardElevation(0);card.setStrokeWidth(0);card.setCardBackgroundColor(NativeActionTokens.surfaceContainer(true));card.setPreventCornerOverlap(false);card.setUseCompatPadding(false);return card;
    }
    static LinearLayout cardContent(MaterialCardView card,int padding){
        LinearLayout body=column(card.getContext());int space=dp(card.getContext(),padding);body.setPadding(space,space,space,space);card.addView(body,new ViewGroup.LayoutParams(-1,-2));return body;
    }
    static void add(LinearLayout parent,View child,int topGap){LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);params.topMargin=dp(parent.getContext(),topGap);parent.addView(child,params);}
    static ImageView icon(Context context,int resource,String description){
        ImageView icon=new ImageView(context);icon.setImageResource(resource);icon.setImageTintList(ColorStateList.valueOf(NativeActionTokens.onSurfaceVariant(true)));icon.setContentDescription(description);return icon;
    }
    static void divider(LinearLayout parent){View divider=new View(parent.getContext());divider.setBackgroundColor(NativeActionTokens.outlineVariant(true));parent.addView(divider,new LinearLayout.LayoutParams(-1,dp(parent.getContext(),1)));}
    static TextView infoRow(LinearLayout parent,int icon,String label,String value){
        Context context=parent.getContext();LinearLayout row=row(context);row.setMinimumHeight(dp(context,48));row.setPadding(dp(context,12),dp(context,8),dp(context,12),dp(context,8));
        row.addView(icon(context,icon,null),new LinearLayout.LayoutParams(dp(context,20),dp(context,20)));
        TextView title=body(context,label);LinearLayout.LayoutParams titleParams=new LinearLayout.LayoutParams(0,-2,1);titleParams.setMarginStart(dp(context,12));row.addView(title,titleParams);
        TextView detail=supporting(context,value);detail.setGravity(Gravity.END);detail.setMaxLines(2);detail.setEllipsize(TextUtils.TruncateAt.END);row.addView(detail,new LinearLayout.LayoutParams(0,-2,1));parent.addView(row,new LinearLayout.LayoutParams(-1,-2));return detail;
    }
    static void textAction(Button action,boolean destructive){
        boolean dark=true;int active=destructive?NativeActionTokens.error(dark):NativeActionTokens.primary(dark);
        ColorStateList foreground=new ColorStateList(new int[][]{{-android.R.attr.state_enabled},{}},new int[]{NativeActionTokens.disabledContent(dark),active});
        action.setTextColor(foreground);
        if(action instanceof MaterialButton){MaterialButton material=(MaterialButton)action;material.setBackgroundTintList(ColorStateList.valueOf(Color.TRANSPARENT));material.setIconTint(foreground);material.setStrokeWidth(0);}
    }
    static void quickAction(Button action,int icon){
        textAction(action,false);action.setTextColor(NativeActionTokens.onSurface(true));action.setMinHeight(dp(action.getContext(),64));
        if(action instanceof MaterialButton){MaterialButton material=(MaterialButton)action;material.setIconResource(icon);material.setIconTint(ColorStateList.valueOf(NativeActionTokens.onSurface(true)));material.setIconGravity(MaterialButton.ICON_GRAVITY_TOP);material.setIconSize(dp(action.getContext(),24));material.setIconPadding(dp(action.getContext(),4));material.setInsetTop(0);material.setInsetBottom(0);}
        action.setContentDescription(action.getText());
    }
}
