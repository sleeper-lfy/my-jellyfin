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
    static final int BG=0xff0b1117, SURFACE=0xff15212c, PANEL=0xff131e28, BORDER=0xff2c414f, TEXT=0xffeef3f5, MUTED=0xff91a9b8, ACCENT=0xff79d8ec, HEART=0xfff3a4b8;
    static int dp(Context context,float value){return Math.round(value*context.getResources().getDisplayMetrics().density);}
    static GradientDrawable surface(Context context,int color,int stroke,int radius){
        GradientDrawable drawable=new GradientDrawable();drawable.setColor(color);drawable.setCornerRadius(dp(context,radius));
        if(stroke!=0)drawable.setStroke(dp(context,1),stroke);return drawable;
    }
    static void button(Button view,boolean primary,boolean selected,boolean heart){
        Context context=view.getContext();int color=primary?ACCENT:selected?0xff203e4b:SURFACE;
        if(selected&&heart)color=0xff3b2b30;
        int border=selected?(heart?0xff81575e:0xff427082):BORDER;
        view.setBackgroundTintList(null);view.setBackground(new RippleDrawable(ColorStateList.valueOf(0x25ffffff),surface(context,color,primary?0:border,12),null));
        view.setSelected(selected);view.setTextColor(selected?(heart?0xffffb5cc:0xffa5e5f5):primary?0xff102a35:TEXT);
        view.setPadding(dp(context,12),dp(context,6),dp(context,12),dp(context,6));view.setMinWidth(0);view.setMinimumWidth(0);view.setMinimumHeight(dp(context,48));view.setMinHeight(dp(context,48));view.setAllCaps(false);
    }
    static void icon(Button button,String name,boolean selected){
        Symbol icon=new Symbol(name,name.equals("play")?0xff102a35:selected?(name.equals("heart")?HEART:name.equals("star")?0xffe7c567:name.equals("ban")?0xffef8b87:ACCENT):0xffddddE5,selected);
        icon.setBounds(0,0,dp(button.getContext(),20),dp(button.getContext(),20));
        button.setCompoundDrawables(icon,null,null,null);button.setCompoundDrawablePadding(dp(button.getContext(),7));
    }
    static void field(android.widget.EditText view){
        Context context=view.getContext();view.setTextColor(TEXT);view.setHintTextColor(MUTED);view.setTextSize(14);
        view.setBackground(surface(context,0xff0d1821,BORDER,10));view.setPadding(dp(context,12),dp(context,8),dp(context,12),dp(context,8));view.setMinimumHeight(dp(context,48));
    }
    static void quiet(Button view,String symbol,String description){
        view.setText("");button(view,false,false,false);view.setBackground(surface(view.getContext(),Color.TRANSPARENT,0,10));
        icon(view,symbol,false);Drawable drawable=view.getCompoundDrawables()[0];view.setCompoundDrawables(null,null,null,null);view.setBackground(new RippleDrawable(ColorStateList.valueOf(0x2579d8ec),new android.graphics.drawable.LayerDrawable(new Drawable[]{surface(view.getContext(),Color.TRANSPARENT,0,10),new CenterSymbol(drawable)}),null));view.setContentDescription(description);
    }
    static final class CenterSymbol extends Drawable {
        private final Drawable drawable;CenterSymbol(Drawable value){drawable=value;}
        public void draw(Canvas canvas){int size=dpSize();int x=getBounds().centerX()-size/2,y=getBounds().centerY()-size/2;drawable.setBounds(x,y,x+size,y+size);drawable.draw(canvas);}
        private int dpSize(){return Math.min(Math.min(getBounds().width(),getBounds().height()),Math.max(20,drawable.getIntrinsicWidth()>0?drawable.getIntrinsicWidth():drawable.getBounds().width()));}
        public void setAlpha(int value){drawable.setAlpha(value);}public void setColorFilter(ColorFilter filter){drawable.setColorFilter(filter);}public int getOpacity(){return PixelFormat.TRANSLUCENT;}
    }
    static Button navigation(Context context,String title,String symbol,boolean selected){
        Button view=new Button(context);button(view,false,selected,false);view.setText(title);view.setTextSize(11);view.setMaxLines(1);view.setEllipsize(android.text.TextUtils.TruncateAt.END);
        Symbol icon=new Symbol(symbol,selected?ACCENT:MUTED,false);icon.setBounds(0,0,dp(context,22),dp(context,22));view.setCompoundDrawables(null,icon,null,null);view.setCompoundDrawablePadding(dp(context,5));view.setPadding(dp(context,2),dp(context,8),dp(context,2),dp(context,8));view.setBackground(surface(context,selected?0xff183542:Color.TRANSPARENT,0,14));view.setMinHeight(dp(context,60));return view;
    }
    static void sheet(android.app.AlertDialog dialog){
        if(dialog.getWindow()==null)return;android.view.Window window=dialog.getWindow();window.setBackgroundDrawable(surface(dialog.getContext(),PANEL,BORDER,20));
        window.setGravity(android.view.Gravity.BOTTOM);window.setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        window.setLayout(android.view.ViewGroup.LayoutParams.MATCH_PARENT,android.view.ViewGroup.LayoutParams.WRAP_CONTENT);
        for(int which:new int[]{-1,-2,-3}){Button b=dialog.getButton(which);if(b!=null)button(b,which==-1,false,false);}
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
