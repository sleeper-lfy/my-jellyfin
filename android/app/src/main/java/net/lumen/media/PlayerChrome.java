package net.lumen.media;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.drawable.Drawable;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.core.graphics.ColorUtils;
import com.google.android.material.button.MaterialButton;
import com.google.android.material.materialswitch.MaterialSwitch;
import net.lumen.media.ui.theme.NativeActionTokens;

/** Lightweight controls and divided setting rows over the video; decoder-independent. */
final class PlayerChrome {
    private PlayerChrome(){}
    static int dp(Context context,float value){return MediaStyle.dp(context,value);}
    static int text(){return NativeActionTokens.onSurface(true);}
    static int muted(){return NativeActionTokens.onSurfaceVariant(true);}
    static int accent(){return NativeActionTokens.primary(true);}
    static int alpha(int color,int alpha){return ColorUtils.setAlphaComponent(color,alpha);}
    static void quiet(Button button,String symbol,boolean stacked){
        int foreground=button.isSelected()?accent():text();
        ColorStateList content=new ColorStateList(new int[][]{{-android.R.attr.state_enabled},{}},new int[]{NativeActionTokens.disabledContent(true),foreground});
        button.setTextColor(content);button.setTextSize(NativeActionTokens.labelMediumSp());button.setGravity(Gravity.CENTER);button.setMinWidth(dp(button.getContext(),48));button.setMinimumWidth(dp(button.getContext(),48));button.setMinHeight(dp(button.getContext(),48));button.setMinimumHeight(dp(button.getContext(),48));button.setPadding(dp(button.getContext(),4),dp(button.getContext(),4),dp(button.getContext(),4),dp(button.getContext(),4));button.setMaxLines(2);
        if(button instanceof MaterialButton){MaterialButton material=(MaterialButton)button;material.setInsetTop(0);material.setInsetBottom(0);material.setBackgroundTintList(ColorStateList.valueOf(android.graphics.Color.TRANSPARENT));material.setStrokeWidth(0);material.setRippleColor(ColorStateList.valueOf(alpha(accent(),36)));material.setIconTint(content);material.setIcon(symbol==null?null:new Glyph(symbol));material.setIconSize(dp(button.getContext(),24));material.setIconPadding(dp(button.getContext(),4));material.setIconGravity(stacked?MaterialButton.ICON_GRAVITY_TEXT_TOP:MaterialButton.ICON_GRAVITY_TEXT_START);}
    }
    static LinearLayout card(Context context){LinearLayout card=new LinearLayout(context);card.setOrientation(LinearLayout.VERTICAL);card.setPadding(dp(context,4),0,dp(context,4),0);card.setBackground(MediaStyle.surface(context,NativeActionTokens.surfaceContainerHigh(true),0,12));return card;}
    static final class SettingRow extends FrameLayout {
        final Button action;private final TextView value,arrow;private boolean hasToggle;
        SettingRow(Context context,Button control,String symbol,String summary,boolean chevron){
            super(context);action=control;setTag("playerSetting:"+control.getText());quiet(control,symbol,false);control.setGravity(Gravity.START|Gravity.CENTER_VERTICAL);control.setTextSize(NativeActionTokens.bodyLargeSp());control.setPaddingRelative(dp(context,12),dp(context,8),dp(context,summary.isEmpty()?32:132),dp(context,8));control.setMinHeight(dp(context,56));control.setMinimumHeight(dp(context,56));addView(control,new LayoutParams(-1,-2));
            value=new TextView(context);value.setText(summary);value.setTextColor(muted());value.setTextSize(NativeActionTokens.bodyMediumSp());value.setSingleLine(true);value.setEllipsize(android.text.TextUtils.TruncateAt.END);value.setGravity(Gravity.END|Gravity.CENTER_VERTICAL);LayoutParams detail=new LayoutParams(dp(context,108),-1,Gravity.END);detail.rightMargin=dp(context,28);addView(value,detail);
            arrow=new TextView(context);arrow.setText(chevron?"›":"");arrow.setTextColor(muted());arrow.setTextSize(24);arrow.setGravity(Gravity.CENTER);addView(arrow,new LayoutParams(dp(context,28),-1,Gravity.END));
        }
        @Override protected void onMeasure(int ws,int hs){
            boolean large=getResources().getConfiguration().fontScale>1.35f;
            value.setVisibility(large||hasToggle?GONE:VISIBLE);action.setPaddingRelative(dp(getContext(),12),dp(getContext(),8),dp(getContext(),hasToggle?80:large||value.getText().length()==0?32:132),dp(getContext(),8));int rowHeight=large?(getResources().getConfiguration().fontScale>1.6f?104:80):56;action.setMinHeight(dp(getContext(),rowHeight));action.setMinimumHeight(dp(getContext(),rowHeight));super.onMeasure(ws,hs);
        }
    }
    static void row(LinearLayout card,Button button,String symbol,String value,boolean chevron){
        if(card.getChildCount()>0){View line=new View(card.getContext());line.setBackgroundColor(alpha(NativeActionTokens.outlineVariant(true),160));LinearLayout.LayoutParams divider=new LinearLayout.LayoutParams(-1,dp(card.getContext(),1));divider.leftMargin=dp(card.getContext(),48);divider.rightMargin=dp(card.getContext(),12);card.addView(line,divider);}
        card.addView(new SettingRow(card.getContext(),button,symbol,value,chevron),new LinearLayout.LayoutParams(-1,-2));
    }
    static MaterialSwitch toggleRow(LinearLayout card,Button button,boolean checked,java.util.function.Consumer<Boolean> changed){
        row(card,button,"auto","",false);SettingRow row=(SettingRow)card.getChildAt(card.getChildCount()-1);row.hasToggle=true;row.value.setVisibility(View.GONE);row.arrow.setVisibility(View.GONE);
        MaterialSwitch toggle=new MaterialSwitch(button.getContext());toggle.setTag("playerAutoNextSwitch");toggle.setContentDescription("自动播放下一集");toggle.setChecked(checked);toggle.setMinimumWidth(dp(card.getContext(),48));toggle.setMinimumHeight(dp(card.getContext(),48));
        int disabledTrack=alpha(NativeActionTokens.onSurface(true),31),disabledThumb=alpha(NativeActionTokens.onSurface(true),97);
        toggle.setTrackTintList(switchColors(accent(),NativeActionTokens.surfaceContainerHighest(true),disabledTrack));
        toggle.setThumbTintList(switchColors(NativeActionTokens.content(true,1,false),muted(),disabledThumb));
        toggle.setThumbIconTintList(switchColors(accent(),NativeActionTokens.surfaceContainerHighest(true),disabledThumb));
        toggle.setTrackDecorationTintList(switchColors(accent(),NativeActionTokens.outlineVariant(true),disabledTrack));
        FrameLayout.LayoutParams position=new FrameLayout.LayoutParams(dp(card.getContext(),64),dp(card.getContext(),48),Gravity.END|Gravity.CENTER_VERTICAL);position.rightMargin=dp(card.getContext(),12);row.addView(toggle,position);
        button.setContentDescription("自动播放下一集，"+(checked?"已开启":"关闭"));toggle.setOnCheckedChangeListener((view,value)->{button.setContentDescription("自动播放下一集，"+(value?"已开启":"关闭"));changed.accept(value);});return toggle;
    }
    private static ColorStateList switchColors(int checked,int unchecked,int disabled){return new ColorStateList(new int[][]{{-android.R.attr.state_enabled},{android.R.attr.state_checked},{}},new int[]{disabled,checked,unchecked});}
    static FrameLayout tab(Button button,boolean selected){
        FrameLayout cell=new FrameLayout(button.getContext());quiet(button,null,false);cell.addView(button,new FrameLayout.LayoutParams(-1,dp(button.getContext(),48)));
        View underline=new View(button.getContext());FrameLayout.LayoutParams line=new FrameLayout.LayoutParams(dp(button.getContext(),28),dp(button.getContext(),3),Gravity.BOTTOM|Gravity.CENTER_HORIZONTAL);cell.addView(underline,line);tabSelected(cell,selected);return cell;
    }
    static void tabSelected(FrameLayout cell,boolean selected){Button action=(Button)cell.getChildAt(0);action.setSelected(selected);action.setTextColor(selected?accent():muted());cell.getChildAt(1).setBackgroundColor(selected?accent():android.graphics.Color.TRANSPARENT);}
    static final class Glyph extends Drawable {
        private final String name;private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        Glyph(String value){name=value;paint.setColor(text());paint.setStrokeWidth(1.7f);paint.setStyle(Paint.Style.STROKE);paint.setStrokeCap(Paint.Cap.ROUND);paint.setStrokeJoin(Paint.Join.ROUND);}
        public void draw(Canvas canvas){canvas.save();canvas.translate(getBounds().left,getBounds().top);canvas.scale(getBounds().width()/24f,getBounds().height()/24f);Path path=new Path();
            switch(name){
                case "audio":for(int x=4;x<=20;x+=4){float h=x==12?8:x==8||x==16?5:2;canvas.drawLine(x,12-h,x,12+h,paint);}break;
                case "subtitle":canvas.drawRoundRect(3,4,21,18,3,3,paint);path.moveTo(7,18);path.lineTo(7,22);path.lineTo(12,18);for(int x=7;x<=17;x+=5)canvas.drawPoint(x,11,paint);break;
                case "speed":canvas.drawArc(3,3,21,21,130,280,false,paint);path.moveTo(12,12);path.lineTo(17,7);canvas.drawCircle(12,12,1,paint);break;
                case "files":for(int y=6;y<=18;y+=6){canvas.drawPoint(4,y,paint);canvas.drawLine(9,y,21,y,paint);}break;
                case "heart":path.moveTo(12,21);path.lineTo(4,13);path.cubicTo(-1,8,5,1,10,6);path.lineTo(12,8);path.lineTo(14,6);path.cubicTo(19,1,25,8,20,13);path.close();break;
                case "star":for(int i=0;i<10;i++){double a=-Math.PI/2+i*Math.PI/5;float r=i%2==0?10:4.4f,x=12+(float)Math.cos(a)*r,y=12+(float)Math.sin(a)*r;if(i==0)path.moveTo(x,y);else path.lineTo(x,y);}path.close();break;
                case "bookmark":path.moveTo(6,3);path.lineTo(18,3);path.lineTo(18,22);path.lineTo(12,17);path.lineTo(6,22);path.close();break;
                case "ban":canvas.drawCircle(12,12,9,paint);path.moveTo(6,6);path.lineTo(18,18);break;
                case "next":case "previous":case "auto":path.moveTo(5,5);path.lineTo(15,12);path.lineTo(5,19);path.close();path.moveTo(19,5);path.lineTo(19,19);break;
                case "recenter":canvas.drawCircle(12,12,6,paint);canvas.drawLine(12,2,12,7,paint);canvas.drawLine(12,17,12,22,paint);canvas.drawLine(2,12,7,12,paint);canvas.drawLine(17,12,22,12,paint);break;
                case "zoom-out":case "zoom-in":canvas.drawCircle(12,12,9,paint);canvas.drawLine(7,12,17,12,paint);if(name.equals("zoom-in"))canvas.drawLine(12,7,12,17,paint);break;
                case "projection":canvas.drawRoundRect(3,5,21,19,2,2,paint);break;
                case "eyes":canvas.drawRoundRect(2,6,22,18,4,4,paint);canvas.drawCircle(7,12,2,paint);canvas.drawCircle(17,12,2,paint);break;
                case "settings":canvas.drawCircle(12,12,7,paint);canvas.drawCircle(12,12,2,paint);for(int i=0;i<8;i++){double a=i*Math.PI/4;canvas.drawLine(12+(float)Math.cos(a)*7,12+(float)Math.sin(a)*7,12+(float)Math.cos(a)*10,12+(float)Math.sin(a)*10,paint);}break;
                case "more":for(int x=4;x<=20;x+=8)canvas.drawCircle(x,12,1,paint);break;
                default:canvas.drawRoundRect(4,4,20,20,3,3,paint);canvas.drawLine(8,9,16,9,paint);canvas.drawLine(8,15,16,15,paint);break;
            }
            canvas.drawPath(path,paint);canvas.restore();
        }
        public void setAlpha(int value){paint.setAlpha(value);}public void setColorFilter(ColorFilter filter){paint.setColorFilter(filter);}public int getOpacity(){return PixelFormat.TRANSLUCENT;}
        public int getIntrinsicWidth(){return 24;}public int getIntrinsicHeight(){return 24;}
    }
}
