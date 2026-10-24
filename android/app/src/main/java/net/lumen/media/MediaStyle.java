package net.lumen.media;

import android.content.Context;
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
    static final int ACCENT=Color.rgb(0,164,220), HEART=Color.rgb(244,119,155), SURFACE=Color.rgb(32,32,38);
    static int dp(Context context,float value){return Math.round(value*context.getResources().getDisplayMetrics().density);}
    static GradientDrawable surface(Context context,int color,int stroke,int radius){
        GradientDrawable drawable=new GradientDrawable();drawable.setColor(color);drawable.setCornerRadius(dp(context,radius));
        if(stroke!=0)drawable.setStroke(dp(context,1),stroke);return drawable;
    }
    static void button(Button view,boolean primary,boolean selected,boolean heart){
        Context context=view.getContext();int color=primary?ACCENT:selected?Color.rgb(25,53,64):SURFACE;
        if(selected&&heart)color=Color.rgb(63,31,43);
        int border=selected?(heart?Color.rgb(147,72,96):Color.rgb(43,111,134)):Color.rgb(58,58,68);
        view.setBackgroundTintList(null);view.setBackground(new RippleDrawable(ColorStateList.valueOf(0x25ffffff),surface(context,color,primary?0:border,8),null));
        view.setSelected(selected);view.setTextColor(selected?(heart?0xffffb5cc:0xffa5e5f5):Color.WHITE);
        view.setPadding(dp(context,12),dp(context,6),dp(context,12),dp(context,6));view.setMinWidth(0);view.setMinimumHeight(dp(context,48));
    }
    static void icon(Button button,String name,boolean selected){
        Symbol icon=new Symbol(name,name.equals("play")?Color.WHITE:selected?(name.equals("heart")?HEART:name.equals("star")?0xffe7c567:name.equals("ban")?0xffef8b87:ACCENT):0xffddddE5,selected);
        icon.setBounds(0,0,dp(button.getContext(),20),dp(button.getContext(),20));
        button.setCompoundDrawables(icon,null,null,null);button.setCompoundDrawablePadding(dp(button.getContext(),7));
    }
    static final class Symbol extends Drawable {
        final String name;final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);final boolean filled;
        Symbol(String name,int color,boolean filled){this.name=name;this.filled=filled;paint.setColor(color);paint.setStrokeWidth(1.8f);paint.setStrokeCap(Paint.Cap.ROUND);paint.setStrokeJoin(Paint.Join.ROUND);}
        @Override public void draw(Canvas canvas){
            canvas.save();canvas.translate(getBounds().left,getBounds().top);canvas.scale(getBounds().width()/24f,getBounds().height()/24f);
            Path path=new Path();paint.setStyle(Paint.Style.STROKE);
            switch(name){
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
