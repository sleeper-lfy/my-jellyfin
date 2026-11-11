package net.lumen.media;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.LayerDrawable;
import android.text.TextUtils;
import android.view.ContextThemeWrapper;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.core.content.ContextCompat;
import androidx.core.graphics.ColorUtils;
import com.google.android.material.button.MaterialButton;
import com.google.android.material.card.MaterialCardView;
import com.google.android.material.imageview.ShapeableImageView;
import com.google.android.material.shape.RelativeCornerSize;
import com.google.android.material.shape.ShapeAppearanceModel;
import com.google.android.material.tabs.TabLayout;
import java.util.function.IntConsumer;
import net.lumen.media.ui.theme.NativeActionTokens;

/** View-only pieces for the approved library layout; all data and callbacks stay with the page. */
final class BiliMainUi {
    private BiliMainUi(){}
    private static Context material(Context context){return new ContextThemeWrapper(context,R.style.LumenNativeActionsDark);}
    private static int dp(Context context,float value){return MediaStyle.dp(context,value);}
    static TextView text(Context context,String value,int size,int color){
        TextView view=new TextView(context);view.setText(value);view.setTextSize(size);view.setTextColor(color);view.setIncludeFontPadding(false);return view;
    }
    static LinearLayout vertical(Context context){LinearLayout column=new LinearLayout(context);column.setOrientation(LinearLayout.VERTICAL);return column;}
    static TextView section(Context context,String title){
        TextView view=text(context,title,Math.round(NativeActionTokens.titleMediumSp()),NativeActionTokens.onSurface(true));view.setTypeface(Typeface.DEFAULT,Typeface.BOLD);view.setPadding(0,dp(context,NativeActionTokens.spaceLgDp()),0,dp(context,NativeActionTokens.spaceMdDp()));return view;
    }
    static LinearLayout group(Context context){return new SettingsColumn(context);}
    static MaterialCardView groupCard(Context context,View content){
        MaterialCardView card=card(context);card.addView(content,new FrameLayout.LayoutParams(-1,-2));return card;
    }
    private static MaterialCardView card(Context context){
        MaterialCardView card=new MaterialCardView(material(context));card.setCardElevation(0);card.setUseCompatPadding(false);card.setPreventCornerOverlap(false);card.setRadius(dp(context,NativeActionTokens.cardCornerDp()));card.setCardBackgroundColor(NativeActionTokens.surfaceContainer(true));card.setStrokeWidth(dp(context,1));card.setStrokeColor(ColorUtils.setAlphaComponent(NativeActionTokens.outlineVariant(true),96));return card;
    }
    static void lightAction(Button button,String icon,boolean selected){
        MediaStyle.button(button,false,selected,false);if(icon!=null&&!icon.isEmpty())MediaStyle.icon(button,icon,selected);
        int foreground=selected?NativeActionTokens.primary(true):NativeActionTokens.onSurface(true);
        ColorStateList content=new ColorStateList(new int[][]{{-android.R.attr.state_enabled},{}},new int[]{NativeActionTokens.disabledContent(true),foreground});
        button.setTextColor(content);button.setGravity(Gravity.CENTER);button.setElevation(0);
        if(button instanceof MaterialButton){MaterialButton material=(MaterialButton)button;material.setBackgroundTintList(ColorStateList.valueOf(Color.TRANSPARENT));material.setStrokeWidth(0);material.setIconTint(content);}
        else button.setBackgroundTintList(ColorStateList.valueOf(Color.TRANSPARENT));
    }
    static Button settingsRow(Context context,String title,String icon,Runnable action){
        Button row=MediaStyle.action(context);row.setText(title);lightAction(row,icon,false);row.setTextSize(NativeActionTokens.bodyMediumSp());row.setGravity(Gravity.START|Gravity.CENTER_VERTICAL);row.setMinHeight(dp(context,56));row.setMinimumHeight(dp(context,56));row.setMaxLines(2);row.setPaddingRelative(dp(context,NativeActionTokens.spaceLgDp()),dp(context,12),dp(context,40),dp(context,12));
        Drawable chevron=ContextCompat.getDrawable(context,R.drawable.bili_chevron_right).mutate();chevron.setTint(NativeActionTokens.onSurfaceVariant(true));LayerDrawable foreground=new LayerDrawable(new Drawable[]{chevron});int size=dp(context,NativeActionTokens.iconDp());foreground.setLayerSize(0,size,size);foreground.setLayerGravity(0,Gravity.END|Gravity.CENTER_VERTICAL);foreground.setLayerInsetRight(0,dp(context,NativeActionTokens.spaceMdDp()));row.setForeground(foreground);row.setOnClickListener(v->action.run());return row;
    }
    static com.google.android.material.chip.Chip suggestionChip(Context context,String label,Runnable action){
        com.google.android.material.chip.Chip chip=new com.google.android.material.chip.Chip(material(context));chip.setText(label);chip.setTextSize(NativeActionTokens.labelMediumSp());chip.setCheckable(false);chip.setChipIconVisible(false);chip.setCloseIconVisible(false);
        chip.setChipBackgroundColor(ColorStateList.valueOf(NativeActionTokens.surfaceContainerHigh(true)));chip.setTextColor(NativeActionTokens.onSurface(true));chip.setRippleColor(ColorStateList.valueOf(ColorUtils.setAlphaComponent(NativeActionTokens.primary(true),31)));chip.setChipStrokeWidth(0);chip.setChipStrokeColor(ColorStateList.valueOf(Color.TRANSPARENT));chip.setShapeAppearanceModel(chip.getShapeAppearanceModel().toBuilder().setAllCornerSizes(new RelativeCornerSize(.5f)).build());
        chip.setChipMinHeight(dp(context,NativeActionTokens.visualDp()));chip.setEnsureMinTouchTargetSize(true);chip.ensureAccessibleTouchTarget(dp(context,NativeActionTokens.touchDp()));chip.setOnClickListener(v->action.run());return chip;
    }
    static TabLayout tabs(Context context,String[] labels,int selected,IntConsumer onSelect){
        TabLayout tabs=new TabLayout(material(context));tabs.setBackgroundColor(Color.TRANSPARENT);tabs.setTabMode(TabLayout.MODE_SCROLLABLE);tabs.setTabGravity(TabLayout.GRAVITY_START);tabs.setTabIndicatorFullWidth(false);tabs.setSelectedTabIndicatorColor(NativeActionTokens.primary(true));tabs.setSelectedTabIndicatorHeight(dp(context,3));tabs.setTabTextColors(NativeActionTokens.onSurfaceVariant(true),NativeActionTokens.onSurface(true));tabs.setTabRippleColor(ColorStateList.valueOf(ColorUtils.setAlphaComponent(NativeActionTokens.primary(true),24)));
        for(String label:labels)tabs.addTab(tabs.newTab().setText(label),false);TabLayout.Tab active=tabs.getTabAt(Math.max(0,Math.min(selected,labels.length-1)));if(active!=null)active.select();
        tabs.addOnTabSelectedListener(new TabLayout.OnTabSelectedListener(){public void onTabSelected(TabLayout.Tab tab){onSelect.accept(tab.getPosition());}public void onTabUnselected(TabLayout.Tab tab){}public void onTabReselected(TabLayout.Tab tab){}});return tabs;
    }
    static View profile(Context context){
        LinearLayout page=vertical(context);page.setTag("mineProfile");LinearLayout identity=new LinearLayout(context);identity.setGravity(Gravity.CENTER_VERTICAL);identity.setPadding(0,dp(context,NativeActionTokens.spaceSmDp()),0,dp(context,NativeActionTokens.spaceLgDp()));
        MaterialCardView avatar=card(context);avatar.setRadius(dp(context,36));avatar.setCardBackgroundColor(NativeActionTokens.primaryContainer(true));avatar.setStrokeColor(ColorUtils.setAlphaComponent(NativeActionTokens.primary(true),72));TextView monogram=text(context,"L",40,NativeActionTokens.primary(true));monogram.setTypeface(Typeface.DEFAULT,Typeface.BOLD_ITALIC);monogram.setGravity(Gravity.CENTER);monogram.setContentDescription("Lumen 头像");avatar.addView(monogram,new FrameLayout.LayoutParams(-1,-1));identity.addView(avatar,new LinearLayout.LayoutParams(dp(context,72),dp(context,72)));
        LinearLayout labels=vertical(context);labels.setPadding(dp(context,NativeActionTokens.spaceLgDp()),0,0,0);TextView name=text(context,"Lumen",Math.round(NativeActionTokens.titleLargeSp()),NativeActionTokens.onSurface(true));name.setTypeface(Typeface.DEFAULT,Typeface.BOLD);labels.addView(name);TextView subtitle=text(context,"私人光影库",Math.round(NativeActionTokens.bodyMediumSp()),NativeActionTokens.onSurfaceVariant(true));LinearLayout.LayoutParams subtitleSize=new LinearLayout.LayoutParams(-1,-2);subtitleSize.topMargin=dp(context,NativeActionTokens.spaceSmDp());labels.addView(subtitle,subtitleSize);identity.addView(labels,new LinearLayout.LayoutParams(0,-2,1));page.addView(identity);
        LinearLayout counts=new LinearLayout(context);counts.setTag("mineTotals");counts.setGravity(Gravity.CENTER_VERTICAL);String[] names={"影片","收藏","想看"},keys={"all","favorite","watchlist"};
        for(int i=0;i<names.length;i++){if(i>0){View separator=new View(context);separator.setBackgroundColor(NativeActionTokens.outlineVariant(true));counts.addView(separator,new LinearLayout.LayoutParams(dp(context,1),dp(context,32)));}LinearLayout cell=vertical(context);cell.setGravity(Gravity.CENTER);TextView value=text(context,"—",Math.round(NativeActionTokens.titleLargeSp()),NativeActionTokens.onSurface(true));value.setTypeface(Typeface.DEFAULT,Typeface.BOLD);value.setTag("mineTotal:"+keys[i]);cell.addView(value);TextView label=text(context,names[i],Math.round(NativeActionTokens.labelMediumSp()),NativeActionTokens.onSurfaceVariant(true));LinearLayout.LayoutParams labelSize=new LinearLayout.LayoutParams(-2,-2);labelSize.topMargin=dp(context,NativeActionTokens.spaceSmDp());cell.addView(label,labelSize);cell.setPadding(0,dp(context,NativeActionTokens.spaceSmDp()),0,dp(context,NativeActionTokens.spaceSmDp()));counts.addView(cell,new LinearLayout.LayoutParams(0,-2,1));}
        page.addView(counts,new LinearLayout.LayoutParams(-1,-2));return page;
    }
    static View quickGrid(Context context,Button[] buttons){
        LinearLayout row=new LinearLayout(context);row.setTag("mineQuickGrid");row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(dp(context,NativeActionTokens.spaceXsDp()),dp(context,NativeActionTokens.spaceSmDp()),dp(context,NativeActionTokens.spaceXsDp()),dp(context,NativeActionTokens.spaceSmDp()));
        for(Button button:buttons){if(button instanceof MaterialButton){MaterialButton material=(MaterialButton)button;material.setIconGravity(MaterialButton.ICON_GRAVITY_TEXT_TOP);material.setIconSize(dp(context,24));material.setIconPadding(dp(context,NativeActionTokens.spaceSmDp()));}button.setGravity(Gravity.CENTER);button.setTextSize(NativeActionTokens.labelMediumSp());button.setMinHeight(dp(context,72));button.setMinimumHeight(dp(context,72));button.setMaxLines(2);row.addView(button,new LinearLayout.LayoutParams(0,-2,1));}
        return groupCard(context,row);
    }
    static android.widget.HorizontalScrollView resumeStrip(Context context){return new ResumeStrip(context);}
    private static final class ResumeStrip extends android.widget.HorizontalScrollView {
        ResumeStrip(Context context){super(context);setHorizontalScrollBarEnabled(false);}
        @Override protected void onMeasure(int widthSpec,int heightSpec){
            if(MeasureSpec.getMode(widthSpec)!=MeasureSpec.UNSPECIFIED&&getChildCount()>0){int available=Math.max(1,MeasureSpec.getSize(widthSpec)-getPaddingLeft()-getPaddingRight());ViewGroup row=(ViewGroup)getChildAt(0);int width=Math.min(dp(getContext(),384),available);for(int i=0;i<row.getChildCount();i++)row.getChildAt(i).getLayoutParams().width=width;}
            super.onMeasure(widthSpec,heightSpec);
        }
    }
    static ViewGroup actorGrid(Context context){return new ActorGrid(context);}
    static ShapeableImageView avatar(Context context,int sizeDp){
        ShapeableImageView image=new ShapeableImageView(material(context));image.setShapeAppearanceModel(ShapeAppearanceModel.builder().setAllCornerSizes(new RelativeCornerSize(.5f)).build());image.setScaleType(ImageView.ScaleType.CENTER_CROP);image.setBackgroundColor(NativeActionTokens.surfaceContainerHigh(true));image.setLayoutParams(new LinearLayout.LayoutParams(dp(context,sizeDp),dp(context,sizeDp)));return image;
    }
    static View playlistCard(Context context,String title,String summary,Runnable action){
        MaterialCardView card=card(context);LinearLayout row=new LinearLayout(context);row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(dp(context,NativeActionTokens.spaceLgDp()),dp(context,NativeActionTokens.spaceLgDp()),dp(context,NativeActionTokens.spaceLgDp()),dp(context,NativeActionTokens.spaceLgDp()));
        FrameLayout artwork=new FrameLayout(context);artwork.setTag("playlistArtwork");ImageView placeholder=new ImageView(context);placeholder.setImageResource(R.drawable.design_system_smart_playlist);placeholder.setImageTintList(ColorStateList.valueOf(NativeActionTokens.primary(true)));placeholder.setScaleType(ImageView.ScaleType.CENTER_INSIDE);placeholder.setBackgroundColor(NativeActionTokens.primaryContainer(true));artwork.addView(placeholder,new FrameLayout.LayoutParams(-1,-1));row.addView(artwork,new LinearLayout.LayoutParams(dp(context,96),dp(context,104)));
        LinearLayout labels=vertical(context);labels.setPadding(dp(context,NativeActionTokens.spaceLgDp()),0,0,0);TextView name=text(context,title,Math.round(NativeActionTokens.titleMediumSp()),NativeActionTokens.onSurface(true));name.setMaxLines(2);name.setEllipsize(TextUtils.TruncateAt.END);name.setTypeface(Typeface.DEFAULT,Typeface.BOLD);labels.addView(name);TextView detail=text(context,summary,Math.round(NativeActionTokens.bodyMediumSp()),NativeActionTokens.onSurfaceVariant(true));detail.setMaxLines(3);detail.setEllipsize(TextUtils.TruncateAt.END);LinearLayout.LayoutParams detailSize=new LinearLayout.LayoutParams(-1,-2);detailSize.topMargin=dp(context,NativeActionTokens.spaceSmDp());labels.addView(detail,detailSize);row.addView(labels,new LinearLayout.LayoutParams(0,-2,1));card.addView(row,new FrameLayout.LayoutParams(-1,-2));card.setClickable(true);card.setFocusable(true);card.setOnClickListener(v->action.run());card.setContentDescription(title+" · "+summary);return card;
    }
    static View metric(Context context,String value,String label,String icon){
        LinearLayout content=new LinearLayout(context);content.setGravity(Gravity.CENTER_VERTICAL);content.setPadding(dp(context,NativeActionTokens.spaceLgDp()),dp(context,NativeActionTokens.spaceLgDp()),dp(context,NativeActionTokens.spaceLgDp()),dp(context,NativeActionTokens.spaceLgDp()));ImageView symbol=new ImageView(context);symbol.setImageResource(resource(icon));symbol.setImageTintList(ColorStateList.valueOf(NativeActionTokens.onSurface(true)));content.addView(symbol,new LinearLayout.LayoutParams(dp(context,28),dp(context,28)));
        LinearLayout labels=vertical(context);labels.setPadding(dp(context,NativeActionTokens.spaceMdDp()),0,0,0);TextView number=text(context,value,Math.round(NativeActionTokens.titleLargeSp()),NativeActionTokens.primary(true));number.setTypeface(Typeface.DEFAULT,Typeface.BOLD);number.setMaxLines(1);number.setEllipsize(TextUtils.TruncateAt.END);labels.addView(number);TextView caption=text(context,label,Math.round(NativeActionTokens.labelMediumSp()),NativeActionTokens.onSurfaceVariant(true));LinearLayout.LayoutParams captionSize=new LinearLayout.LayoutParams(-1,-2);captionSize.topMargin=dp(context,NativeActionTokens.spaceXsDp());labels.addView(caption,captionSize);content.addView(labels,new LinearLayout.LayoutParams(0,-2,1));return groupCard(context,content);
    }
    private static int resource(String icon){if(icon==null)return R.drawable.design_system_statistics;switch(icon){case "movie":case "library":return R.drawable.design_system_library;case "series":return R.drawable.design_system_tasks;case "play":return R.drawable.design_system_phone_queue;case "heart":return R.drawable.design_system_favorite;case "bookmark":return R.drawable.design_system_watchlist;case "server":return R.drawable.design_system_connections;case "remote":return R.drawable.design_system_remote;default:return R.drawable.design_system_statistics;}}
    private static final class SettingsColumn extends LinearLayout {
        SettingsColumn(Context context){super(context);setOrientation(VERTICAL);}
        @Override public void addView(View child,int index,ViewGroup.LayoutParams params){
            if(getChildCount()>0){View line=new View(getContext());line.setBackgroundColor(ColorUtils.setAlphaComponent(NativeActionTokens.outlineVariant(true),96));LayoutParams size=new LayoutParams(-1,dp(getContext(),1));size.setMargins(dp(getContext(),NativeActionTokens.spaceLgDp()),0,dp(getContext(),NativeActionTokens.spaceLgDp()),0);super.addView(line,-1,size);}
            super.addView(child,index,params);
        }
    }
    private static final class ActorGrid extends ViewGroup {
        private final int gap;private int columns=3;
        ActorGrid(Context context){super(context);gap=dp(context,NativeActionTokens.spaceLgDp());}
        @Override protected void onMeasure(int widthSpec,int heightSpec){int width=MeasureSpec.getSize(widthSpec),available=Math.max(0,width-getPaddingLeft()-getPaddingRight());columns=Math.max(3,Math.min(6,available/dp(getContext(),104)));int cell=Math.max(1,(available-gap*(columns-1))/columns),height=getPaddingTop()+getPaddingBottom(),row=0,count=0;
            for(int i=0;i<getChildCount();i++){View child=getChildAt(i);if(child.getVisibility()==GONE)continue;if(child instanceof ViewGroup){ViewGroup card=(ViewGroup)child;if(card.getChildCount()>0&&card.getChildAt(0) instanceof ImageView){View face=card.getChildAt(0);ViewGroup.LayoutParams faceSize=face.getLayoutParams();int diameter=Math.max(1,Math.min(dp(getContext(),104),cell-card.getPaddingLeft()-card.getPaddingRight()));faceSize.width=diameter;faceSize.height=diameter;}}child.measure(MeasureSpec.makeMeasureSpec(cell,MeasureSpec.EXACTLY),MeasureSpec.makeMeasureSpec(0,MeasureSpec.UNSPECIFIED));row=Math.max(row,child.getMeasuredHeight());if(++count%columns==0){height+=row+gap;row=0;}}if(count%columns!=0)height+=row;else if(count>0)height-=gap;setMeasuredDimension(resolveSize(width,widthSpec),resolveSize(height,heightSpec));}
        @Override protected void onLayout(boolean changed,int left,int top,int right,int bottom){int x=getPaddingLeft(),y=getPaddingTop(),row=0,column=0;for(int i=0;i<getChildCount();i++){View child=getChildAt(i);if(child.getVisibility()==GONE)continue;child.layout(x,y,x+child.getMeasuredWidth(),y+child.getMeasuredHeight());row=Math.max(row,child.getMeasuredHeight());if(++column==columns){column=0;x=getPaddingLeft();y+=row+gap;row=0;}else x+=child.getMeasuredWidth()+gap;}}
        @Override protected LayoutParams generateDefaultLayoutParams(){return new LayoutParams(-1,-2);}
    }
}
