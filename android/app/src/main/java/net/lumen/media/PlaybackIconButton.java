package net.lumen.media;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import androidx.appcompat.widget.AppCompatButton;

/** Playback symbols keep their touch target independent from the user's text size. */
final class PlaybackIconButton extends AppCompatButton {
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private String symbol;
    PlaybackIconButton(Context context,String symbol,String description){
        super(context);setText("");setTextColor(Color.WHITE);setAllCaps(false);
        setMinWidth(0);setMinimumWidth(0);setMinHeight(MediaStyle.dp(context,48));setMinimumHeight(MediaStyle.dp(context,48));
        setPadding(0,0,0,0);setBackgroundColor(Color.TRANSPARENT);setSymbol(symbol,description);
    }
    void setSymbol(String value,String description){symbol=value;setContentDescription(description);setTooltipText(description);invalidate();}
    String symbol(){return symbol;}
    @Override protected void onDraw(Canvas canvas){
        super.onDraw(canvas);canvas.save();float size=MediaStyle.dp(getContext(),26);
        canvas.translate((getWidth()-size)/2,(getHeight()-size)/2);canvas.scale(size/24,size/24);
        paint.setColor(getCurrentTextColor());paint.setAlpha(isEnabled()?255:90);paint.setStrokeWidth(1.8f);
        paint.setStrokeCap(Paint.Cap.ROUND);paint.setStrokeJoin(Paint.Join.ROUND);paint.setStyle(Paint.Style.STROKE);
        Path path=new Path();
        switch(symbol){
            case "play":path.moveTo(8,5);path.lineTo(19,12);path.lineTo(8,19);path.close();paint.setStyle(Paint.Style.FILL);break;
            case "pause":canvas.drawLine(8,5,8,19,paint);canvas.drawLine(16,5,16,19,paint);break;
            case "previous":case "next":
                if(symbol.equals("previous")){canvas.translate(24,0);canvas.scale(-1,1);}
                path.moveTo(6,5);path.lineTo(16,12);path.lineTo(6,19);path.close();canvas.drawLine(19,5,19,19,paint);break;
            case "backward":case "forward":
                canvas.save();if(symbol.equals("backward")){canvas.translate(24,0);canvas.scale(-1,1);}
                canvas.drawArc(3,3,21,21,-65,285,false,paint);path.moveTo(16,2);path.lineTo(20,5);path.lineTo(16,8);canvas.drawPath(path,paint);path.reset();canvas.restore();
                paint.setStyle(Paint.Style.FILL);paint.setTextAlign(Paint.Align.CENTER);paint.setTextSize(9);paint.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);canvas.drawText("10",12,15,paint);break;
            case "back":path.moveTo(14,5);path.lineTo(7,12);path.lineTo(14,19);path.moveTo(7,12);path.lineTo(21,12);break;
            case "fullscreen":
                path.moveTo(4,9);path.lineTo(4,4);path.lineTo(9,4);path.moveTo(15,4);path.lineTo(20,4);path.lineTo(20,9);
                path.moveTo(20,15);path.lineTo(20,20);path.lineTo(15,20);path.moveTo(9,20);path.lineTo(4,20);path.lineTo(4,15);break;
            case "bookmark":path.moveTo(6,3);path.lineTo(18,3);path.lineTo(18,21);path.lineTo(12,17);path.lineTo(6,21);path.close();break;
            case "recenter":canvas.drawCircle(12,12,6,paint);canvas.drawLine(12,2,12,7,paint);canvas.drawLine(12,17,12,22,paint);canvas.drawLine(2,12,7,12,paint);canvas.drawLine(17,12,22,12,paint);break;
            case "zoom-in":case "zoom-out":canvas.drawCircle(10,10,7,paint);canvas.drawLine(15,15,21,21,paint);canvas.drawLine(6,10,14,10,paint);if(symbol.equals("zoom-in"))canvas.drawLine(10,6,10,14,paint);break;
            default:canvas.drawLine(4,6,20,6,paint);canvas.drawLine(4,12,20,12,paint);canvas.drawLine(4,18,20,18,paint);canvas.drawCircle(9,6,2,paint);canvas.drawCircle(15,12,2,paint);canvas.drawCircle(8,18,2,paint);break;
        }
        canvas.drawPath(path,paint);canvas.restore();
    }
}
