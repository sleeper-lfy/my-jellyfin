package net.lumen.media;

import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.graphics.drawable.InsetDrawable;
import androidx.core.content.ContextCompat;
import com.google.android.material.button.MaterialButton;
import com.google.android.material.shape.MaterialShapeDrawable;
import com.google.android.material.shape.ShapeAppearanceModel;
import net.lumen.media.ui.theme.NativeActionTokens;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.ColorFilter;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.content.res.ColorStateList;
import android.widget.Button;

/** Shared surfaces and vector actions for media cards, details and filters. */
final class MediaStyle {
    static final int SPACE=8, PAGE=16, SECTION=24, TOUCH=48;
    static final int BG=0xff0b1117, SURFACE=0xff15212c, PANEL=0xff131e28, BORDER=0xff2c414f, TEXT=0xffeef3f5, MUTED=0xff91a9b8, ACCENT=0xff79d8ec, HEART=0xfff3a4b8;
    static int dp(Context context,float value){return Math.round(value*context.getResources().getDisplayMetrics().density);}
    /** Horizontal controls share one gap; weights leave narrow-window inputs room to shrink. */
    static LinearRow row(Context context){return new LinearRow(context);}
    static class LinearRow extends android.widget.LinearLayout {
        LinearRow(Context context){super(context);setOrientation(HORIZONTAL);setGravity(android.view.Gravity.CENTER_VERTICAL);}
        @Override public void addView(android.view.View child,int index,android.view.ViewGroup.LayoutParams params){
            LayoutParams cell=params instanceof LayoutParams?(LayoutParams)params:new LayoutParams(params);
            cell.setMarginStart(getChildCount()==0?0:dp(getContext(),SPACE));cell.setMarginEnd(0);
            super.addView(child,index,cell);
        }
    }
    /** Separate action spacing from form fields and navigation spacing. */
    static LinearRow actionRow(Context context){return new ActionLine(context,false);}
    static LinearRow actionColumn(Context context){return new ActionLine(context,true);}
    static ChipLayout actionFlow(Context context){return new ChipLayout(context,Math.round(NativeActionTokens.actionGapDp()));}
    static final class ActionLine extends LinearRow {
        ActionLine(Context context,boolean vertical){super(context);setOrientation(vertical?VERTICAL:HORIZONTAL);setGravity(vertical?Gravity.START:Gravity.CENTER_VERTICAL);}
        @Override protected void onMeasure(int widthSpec,int heightSpec){
            boolean first=true;int gap=dp(getContext(),NativeActionTokens.actionGapDp());
            for(int i=0;i<getChildCount();i++){View child=getChildAt(i);boolean visible=child.getVisibility()!=GONE;LayoutParams cell=(LayoutParams)child.getLayoutParams();
                actionMargins(cell,getOrientation()==VERTICAL,visible&&!first?gap:0,getLayoutDirection());if(visible)first=false;
            }
            super.onMeasure(widthSpec,heightSpec);
        }
    }
    /** Relative margins alone can leave a previously resolved physical 8dp margin behind. */
    private static void actionMargins(ViewGroup.MarginLayoutParams cell,boolean vertical,int gap,int direction){
        cell.setMarginStart(vertical?0:gap);cell.setMarginEnd(0);
        if(vertical){cell.topMargin=gap;cell.bottomMargin=0;}
        cell.resolveLayoutDirection(direction);
        cell.leftMargin=!vertical&&direction!=View.LAYOUT_DIRECTION_RTL?gap:0;
        cell.rightMargin=!vertical&&direction==View.LAYOUT_DIRECTION_RTL?gap:0;
    }
    static Button action(Context context){return action(context,true);}
    static Button action(Context context,boolean dark){Button view=new NativeActionButton(context,dark);button(view,false,false,false);return view;}
    /** Poster actions retain a 48dp Material touch target around a compact circular scrim. */
    static Button cardIcon(Context context){return new NativeActionButton(context,true,true);}
    static void cardMark(Button view,String symbol,boolean selected){
        styleAction(view,3,selected);icon(view,symbol,selected);view.setText("");
        MaterialButton material=(MaterialButton)view;Context context=view.getContext();
        int scrim=(NativeActionTokens.scrim(true)&0x00ffffff)|0x99000000;
        material.setBackgroundTintList(ColorStateList.valueOf(scrim));
        material.setCornerRadius(dp(context,NativeActionTokens.visualDp()/2));
        int color=NativeActionTokens.onPhotoScrim(selected);
        ColorStateList tint=new ColorStateList(new int[][]{{-android.R.attr.state_enabled},{}},new int[]{(color&0x00ffffff)|0x99000000,color});
        material.setIconTint(tint);material.setTextColor(tint);
        material.setIconSize(dp(context,NativeActionTokens.posterIconDp()));material.setIconPadding(0);
        int inset=dp(context,NativeActionTokens.insetDp());material.setPaddingRelative(inset,inset,inset,inset);
    }
    /** Resume cards follow the actual viewport rather than the physical display. */
    static final class ResumeStrip extends android.widget.HorizontalScrollView {
        ResumeStrip(Context context){super(context);setHorizontalScrollBarEnabled(false);}
        @Override protected void onMeasure(int ws,int hs){
            int available=Math.max(1,android.view.View.MeasureSpec.getSize(ws)-getPaddingLeft()-getPaddingRight());
            if(getChildCount()>0&&getChildAt(0) instanceof android.view.ViewGroup){android.view.ViewGroup row=(android.view.ViewGroup)getChildAt(0);
                int width=Math.min(dp(getContext(),336),Math.max(1,available-dp(getContext(),16)));
                for(int i=0;i<row.getChildCount();i++){android.view.View card=row.getChildAt(i);card.getLayoutParams().width=width;if(card instanceof android.view.ViewGroup){android.view.View image=((android.view.ViewGroup)card).getChildAt(0);image.getLayoutParams().height=Math.round(width*9f/16);}}
            }
            super.onMeasure(ws,hs);
        }
    }
    /** Media artwork is never cropped, regardless of thumbnail/poster availability. */
    static void artwork(android.widget.ImageView image){image.setScaleType(android.widget.ImageView.ScaleType.FIT_CENTER);image.setBackgroundColor(0xff09121a);}
    /** Long work names must not turn a queue item into a full page. */
    static final class QueueAdapter extends android.widget.ArrayAdapter<String> {
        QueueAdapter(Context context){super(context,android.R.layout.simple_list_item_single_choice,new java.util.ArrayList<>());}
        @Override public android.view.View getView(int position,android.view.View reuse,android.view.ViewGroup parent){
            android.widget.CheckedTextView title=(android.widget.CheckedTextView)super.getView(position,reuse,parent);
            title.setTextSize(14);title.setTextColor(TEXT);title.setSingleLine(false);title.setMaxLines(2);title.setEllipsize(android.text.TextUtils.TruncateAt.END);
            title.setLayoutParams(new android.widget.AbsListView.LayoutParams(-1,-2));title.setMinHeight(dp(getContext(),72));title.setPadding(dp(getContext(),16),dp(getContext(),8),dp(getContext(),16),dp(getContext(),8));
            title.setContentDescription(getItem(position));return title;
        }
    }
    static GradientDrawable surface(Context context,int color,int stroke,int radius){
        GradientDrawable drawable=new GradientDrawable();drawable.setColor(color);drawable.setCornerRadius(dp(context,radius));
        if(stroke!=0)drawable.setStroke(dp(context,1),stroke);return drawable;
    }
    static void button(Button view,boolean primary,boolean selected,boolean heart){styleAction(view,primary?1:0,selected);}
    static void danger(Button view){styleAction(view,2,view.isSelected());}
    private static boolean dark(Button view){return !(view instanceof NativeActionButton)||((NativeActionButton)view).isDarkTheme();}
    private static ColorStateList actionColors(boolean dark,int role,boolean foreground){
        int disabled=foreground?NativeActionTokens.disabledContent(dark):NativeActionTokens.disabledContainer(dark,role);
        int selected=foreground?NativeActionTokens.content(dark,role,true):NativeActionTokens.container(dark,role,true);
        int normal=foreground?NativeActionTokens.content(dark,role,false):NativeActionTokens.container(dark,role,false);
        return new ColorStateList(new int[][]{{-android.R.attr.state_enabled},{android.R.attr.state_selected},{}},new int[]{disabled,selected,normal});
    }
    private static ColorStateList rippleColors(boolean dark,int role){
        int base=NativeActionTokens.content(dark,role,false);return new ColorStateList(new int[][]{{-android.R.attr.state_enabled},{}},new int[]{Color.TRANSPARENT,(base&0x00ffffff)|0x1f000000});
    }
    private static void styleAction(Button view,int role,boolean selected){
        Context context=view.getContext();boolean dark=dark(view);int inset=dp(context,NativeActionTokens.insetDp());
        ColorStateList fill=actionColors(dark,role,false),foreground=actionColors(dark,role,true),ripple=rippleColors(dark,role);
        if(view instanceof MaterialButton){
            MaterialButton material=(MaterialButton)view;material.setInsetTop(inset);material.setInsetBottom(inset);material.setCornerRadius(dp(context,NativeActionTokens.cornerDp()));material.setStrokeWidth(0);
            material.setBackgroundTintList(fill);material.setRippleColor(ripple);material.setIconTint(foreground);material.setIconSize(dp(context,NativeActionTokens.iconDp()));material.setIconPadding(dp(context,NativeActionTokens.iconGapDp()));material.setIconGravity(MaterialButton.ICON_GRAVITY_TEXT_START);
        }else{
            MaterialShapeDrawable shape=new MaterialShapeDrawable(ShapeAppearanceModel.builder().setAllCornerSizes(dp(context,NativeActionTokens.cornerDp())).build());shape.setFillColor(fill);
            view.setBackgroundTintList(null);view.setBackground(new InsetDrawable(new RippleDrawable(ripple,shape,null),0,inset,0,inset));
        }
        view.setSelected(selected);view.setTextColor(foreground);view.setTextSize(NativeActionTokens.labelSp());view.setAllCaps(false);view.setIncludeFontPadding(false);view.setGravity(Gravity.CENTER);
        int horizontal=dp(context,NativeActionTokens.horizontalPaddingDp()),vertical=inset+dp(context,NativeActionTokens.verticalPaddingDp());view.setPaddingRelative(horizontal,vertical,horizontal,vertical);
        int touch=dp(context,NativeActionTokens.touchDp());view.setMinWidth(touch);view.setMinimumWidth(touch);view.setMinHeight(touch);view.setMinimumHeight(touch);view.setMaxLines(2);view.setEllipsize(android.text.TextUtils.TruncateAt.END);
        if(!(view instanceof MaterialButton))syncActionState(view.getBackground(),view.getDrawableState());
    }
    /** A newly installed nested shape must not keep its initial empty (disabled) state. */
    private static void syncActionState(Drawable background,int[] state){
        if(background==null)return;
        background.setState(state);
        if(background instanceof InsetDrawable)syncActionState(((InsetDrawable)background).getDrawable(),state);
        if(background instanceof android.graphics.drawable.LayerDrawable){
            android.graphics.drawable.LayerDrawable layers=(android.graphics.drawable.LayerDrawable)background;
            for(int i=0;i<layers.getNumberOfLayers();i++)syncActionState(layers.getDrawable(i),state);
        }
    }
    private static Drawable actionIcon(Context context,String name,boolean selected,int color){
        int asset;
        switch(name){
            case "home":asset=selected?R.drawable.design_system_home_filled:R.drawable.design_system_home;break;
            case "library":asset=selected?R.drawable.design_system_library_filled:R.drawable.design_system_library;break;
            case "discover":asset=selected?R.drawable.design_system_discover_filled:R.drawable.design_system_discover;break;
            case "user":asset=selected?R.drawable.design_system_mine_filled:R.drawable.design_system_mine;break;
            case "heart":asset=selected?R.drawable.design_system_favorite_filled:R.drawable.design_system_favorite;break;
            case "bookmark":asset=selected?R.drawable.design_system_watchlist_filled:R.drawable.design_system_watchlist;break;
            case "search":asset=R.drawable.design_system_search;break;
            case "filter":asset=R.drawable.design_system_filter;break;
            case "sort":asset=R.drawable.design_system_sort;break;
            case "more":asset=R.drawable.design_system_more;break;
            case "server":asset=R.drawable.design_system_connections;break;
            case "smart_playlist":asset=R.drawable.design_system_smart_playlist;break;
            case "statistics":asset=R.drawable.design_system_statistics;break;
            case "phone_queue":asset=R.drawable.design_system_phone_queue;break;
            case "remote":asset=R.drawable.design_system_remote;break;
            case "tasks":asset=R.drawable.design_system_tasks;break;
            case "shuffle":asset=R.drawable.design_system_shuffle;break;
            default:asset=0;
        }
        Drawable drawable=asset==0?new Symbol(name,color,selected):ContextCompat.getDrawable(context,asset).mutate();drawable.setBounds(0,0,dp(context,NativeActionTokens.iconDp()),dp(context,NativeActionTokens.iconDp()));return drawable;
    }
    static void icon(Button button,String name,boolean selected){
        boolean dark=dark(button);Drawable drawable=actionIcon(button.getContext(),name,selected,NativeActionTokens.content(dark,0,selected));
        if(button instanceof MaterialButton){MaterialButton material=(MaterialButton)button;material.setIcon(drawable);material.setIconGravity(MaterialButton.ICON_GRAVITY_TEXT_START);material.setIconSize(dp(button.getContext(),NativeActionTokens.iconDp()));material.setIconPadding(dp(button.getContext(),NativeActionTokens.iconGapDp()));}
        else {drawable.setTintList(button.getTextColors());button.setCompoundDrawables(drawable,null,null,null);button.setCompoundDrawablePadding(dp(button.getContext(),NativeActionTokens.iconGapDp()));}
    }
    static void field(android.widget.EditText view){
        Context context=view.getContext();view.setTextColor(TEXT);view.setHintTextColor(MUTED);view.setTextSize(14);
        view.setBackground(surface(context,0xff0d1821,BORDER,10));view.setPadding(dp(context,12),dp(context,8),dp(context,12),dp(context,8));view.setMinimumHeight(dp(context,48));
    }
    static void quiet(Button view,String symbol,String description){
        view.setText("");styleAction(view,3,false);icon(view,symbol,false);view.setContentDescription(description);
        if(!(view instanceof MaterialButton)){
            Drawable drawable=view.getCompoundDrawables()[0];view.setCompoundDrawables(null,null,null,null);
            int inset=dp(view.getContext(),NativeActionTokens.insetDp());MaterialShapeDrawable shape=new MaterialShapeDrawable(ShapeAppearanceModel.builder().setAllCornerSizes(dp(view.getContext(),NativeActionTokens.cornerDp())).build());shape.setFillColor(ColorStateList.valueOf(Color.TRANSPARENT));
            view.setBackground(new InsetDrawable(new RippleDrawable(rippleColors(dark(view),3),new android.graphics.drawable.LayerDrawable(new Drawable[]{shape,new CenterSymbol(drawable)}),null),0,inset,0,inset));
        }
    }
    static final class CenterSymbol extends Drawable {
        private final Drawable drawable;CenterSymbol(Drawable value){drawable=value;}
        public void draw(Canvas canvas){int size=dpSize();int x=getBounds().centerX()-size/2,y=getBounds().centerY()-size/2;drawable.setBounds(x,y,x+size,y+size);drawable.draw(canvas);}
        private int dpSize(){return Math.min(Math.min(getBounds().width(),getBounds().height()),Math.max(20,drawable.getIntrinsicWidth()>0?drawable.getIntrinsicWidth():drawable.getBounds().width()));}
        public void setAlpha(int value){drawable.setAlpha(value);}public void setColorFilter(ColorFilter filter){drawable.setColorFilter(filter);}public int getOpacity(){return PixelFormat.TRANSLUCENT;}
    }
    /** Style platform dialog actions without changing dialog position or callbacks. */
    static void dialogActions(android.app.AlertDialog dialog){
        java.util.Set<ViewGroup> parents=new java.util.HashSet<>();
        for(int which:new int[]{-1,-2,-3}){Button button=dialog.getButton(which);if(button!=null){button(button,which==-1,false,false);if(button.getParent() instanceof ViewGroup)parents.add((ViewGroup)button.getParent());}}
        int gap=dp(dialog.getContext(),NativeActionTokens.actionGapDp());
        for(ViewGroup parent:parents){boolean first=true;boolean vertical=parent instanceof android.widget.LinearLayout&&((android.widget.LinearLayout)parent).getOrientation()==android.widget.LinearLayout.VERTICAL;
            for(int i=0;i<parent.getChildCount();i++){View child=parent.getChildAt(i);if(!(child instanceof Button)||child.getVisibility()==View.GONE)continue;ViewGroup.LayoutParams params=child.getLayoutParams();if(params instanceof ViewGroup.MarginLayoutParams){ViewGroup.MarginLayoutParams margin=(ViewGroup.MarginLayoutParams)params;actionMargins(margin,vertical,first?0:gap,parent.getLayoutDirection());child.setLayoutParams(margin);}first=false;}
        }
    }
    static void sheet(android.app.AlertDialog dialog){
        if(dialog.getWindow()==null)return;android.view.Window window=dialog.getWindow();
        MaterialShapeDrawable background=new MaterialShapeDrawable(ShapeAppearanceModel.builder().setAllCornerSizes(dp(dialog.getContext(),NativeActionTokens.sheetCornerDp())).build());background.setFillColor(ColorStateList.valueOf(NativeActionTokens.surfaceContainer(true)));window.setBackgroundDrawable(background);
        window.setGravity(Gravity.BOTTOM);window.setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);window.setLayout(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT);dialogActions(dialog);
        View decor=window.getDecorView();final int[] previous={-1};final boolean[] capped={false};
        Runnable cap=()->{
            if(!dialog.isShowing())return;android.graphics.Rect visible=new android.graphics.Rect();decor.getWindowVisibleDisplayFrame(visible);int available=visible.height();
            if(available<=0)available=decor.getResources().getDisplayMetrics().heightPixels;
            if(available<=0)return;
            if(previous[0]!=available&&capped[0]){window.setLayout(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT);capped[0]=false;}
            previous[0]=available;
            if(decor.getHeight()>available&&window.getAttributes().height!=available){window.setLayout(ViewGroup.LayoutParams.MATCH_PARENT,available);capped[0]=true;}
        };
        android.view.ViewTreeObserver.OnGlobalLayoutListener listener=cap::run;decor.getViewTreeObserver().addOnGlobalLayoutListener(listener);
        decor.addOnAttachStateChangeListener(new View.OnAttachStateChangeListener(){public void onViewAttachedToWindow(View view){}public void onViewDetachedFromWindow(View view){view.getViewTreeObserver().removeOnGlobalLayoutListener(listener);view.removeOnAttachStateChangeListener(this);}});decor.post(cap);
    }
    static final class ArtworkPlaceholder extends Drawable {
        private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        public void draw(Canvas canvas){float w=getBounds().width(),h=getBounds().height();paint.setStyle(Paint.Style.FILL);paint.setShader(new android.graphics.LinearGradient(0,0,w,h,new int[]{0xff1d3949,0xff101f2b},null,android.graphics.Shader.TileMode.CLAMP));canvas.drawRect(getBounds(),paint);paint.setShader(null);paint.setColor(0xff587787);paint.setStrokeWidth(Math.max(1,w/200));paint.setStyle(Paint.Style.STROKE);Path peaks=new Path();peaks.moveTo(w*.12f,h*.72f);peaks.lineTo(w*.43f,h*.31f);peaks.lineTo(w*.65f,h*.61f);peaks.lineTo(w*.79f,h*.44f);peaks.lineTo(w*.94f,h*.72f);canvas.drawPath(peaks,paint);canvas.drawCircle(w*.73f,h*.26f,Math.min(w,h)*.055f,paint);}
        public void setAlpha(int value){paint.setAlpha(value);}public void setColorFilter(ColorFilter filter){paint.setColorFilter(filter);}public int getOpacity(){return PixelFormat.OPAQUE;}
    }
    static final class Symbol extends Drawable {
        final String name;final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);final boolean filled;
        Symbol(String name,int color,boolean filled){this.name=name;this.filled=filled;paint.setColor(color);paint.setStrokeWidth(1.8f);paint.setStrokeCap(Paint.Cap.ROUND);paint.setStrokeJoin(Paint.Join.ROUND);}
        @Override public void draw(Canvas canvas){
            canvas.save();canvas.translate(getBounds().left,getBounds().top);canvas.scale(getBounds().width()/24f,getBounds().height()/24f);
            Path path=new Path();paint.setStyle(Paint.Style.STROKE);
            switch(name){
                case "home":path.moveTo(3,10);path.lineTo(12,3);path.lineTo(21,10);path.lineTo(21,21);path.lineTo(15,21);path.lineTo(15,14);path.lineTo(9,14);path.lineTo(9,21);path.lineTo(3,21);path.close();break;
                case "library":canvas.drawRect(3,4,8,21,paint);canvas.drawRect(12,4,16,21,paint);path.moveTo(19,5);path.lineTo(22,20);break;
                case "discover":canvas.drawCircle(12,12,9,paint);path.moveTo(16,8);path.lineTo(14,14);path.lineTo(8,16);path.lineTo(10,10);path.close();break;
                case "user":canvas.drawCircle(12,7,4,paint);canvas.drawArc(4,13,20,29,180,180,false,paint);break;
                case "sort":path.moveTo(5,3);path.lineTo(5,21);path.moveTo(2,18);path.lineTo(5,21);path.lineTo(8,18);path.moveTo(12,5);path.lineTo(22,5);path.moveTo(12,12);path.lineTo(19,12);path.moveTo(12,19);path.lineTo(16,19);break;
                case "server":canvas.drawRoundRect(3,4,21,10,2,2,paint);canvas.drawRoundRect(3,14,21,20,2,2,paint);canvas.drawPoint(7,7,paint);canvas.drawPoint(7,17,paint);break;
                case "chevron":path.moveTo(9,5);path.lineTo(16,12);path.lineTo(9,19);break;
                case "heart":path.moveTo(12,21);path.lineTo(3.5f,12.5f);path.cubicTo(-2,7,5,0,10.5f,5.5f);path.lineTo(12,7);path.lineTo(13.5f,5.5f);path.cubicTo(19,0,26,7,20.5f,12.5f);path.close();break;
                case "bookmark":path.moveTo(6,3);path.lineTo(18,3);path.lineTo(18,21);path.lineTo(12,17);path.lineTo(6,21);path.close();break;
                case "star":for(int i=0;i<10;i++){double angle=-Math.PI/2+i*Math.PI/5;float radius=i%2==0?9:4.2f,x=12+(float)Math.cos(angle)*radius,y=12+(float)Math.sin(angle)*radius;if(i==0)path.moveTo(x,y);else path.lineTo(x,y);}path.close();break;
                case "back":path.moveTo(14,5);path.lineTo(7,12);path.lineTo(14,19);path.moveTo(7,12);path.lineTo(21,12);break;
                case "search":canvas.drawCircle(10,10,7,paint);path.moveTo(16,16);path.lineTo(21,21);break;
                case "filter":path.moveTo(4,6);path.lineTo(20,6);path.moveTo(7,12);path.lineTo(17,12);path.moveTo(10,18);path.lineTo(14,18);break;
                case "close":path.moveTo(6,6);path.lineTo(18,18);path.moveTo(18,6);path.lineTo(6,18);break;
                case "check":path.moveTo(5,12);path.lineTo(9,16);path.lineTo(19,6);break;
                case "ban":canvas.drawCircle(12,12,9,paint);path.moveTo(6,6);path.lineTo(18,18);break;
                case "previous":path.moveTo(6,5);path.lineTo(6,19);path.moveTo(18,5);path.lineTo(8,12);path.lineTo(18,19);path.close();break;
                case "next":path.moveTo(18,5);path.lineTo(18,19);path.moveTo(6,5);path.lineTo(16,12);path.lineTo(6,19);path.close();break;
                case "play":path.moveTo(8,5);path.lineTo(19,12);path.lineTo(8,19);path.close();break;
                default:for(int x=5;x<=19;x+=7)canvas.drawCircle(x,12,1,paint);break;
            }
            if(filled&&(name.equals("heart")||name.equals("bookmark")||name.equals("star")||name.equals("play")))paint.setStyle(Paint.Style.FILL_AND_STROKE);
            canvas.drawPath(path,paint);canvas.restore();
        }
        @Override public void setAlpha(int alpha){paint.setAlpha(alpha);invalidateSelf();}
        @Override public void setColorFilter(ColorFilter filter){paint.setColorFilter(filter);invalidateSelf();}
        @Override public int getOpacity(){return PixelFormat.TRANSLUCENT;}
    }
}
