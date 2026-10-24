package net.lumen.media;

import android.content.Context;
import android.graphics.Canvas;
import android.view.MotionEvent;
import android.view.ScaleGestureDetector;
import android.widget.ImageView;

/** Bounded image zoom; the parent loads only the current still. */
final class ZoomImage extends ImageView {
    private float zoom=1,panX=0,panY=0,lastX,lastY,startX;
    private boolean pinched=false;
    private final ScaleGestureDetector detector;
    interface Step {void move(int delta);}
    private final Step step;
    ZoomImage(Context context,Step step){
        super(context);this.step=step;setScaleType(ScaleType.FIT_CENTER);
        detector=new ScaleGestureDetector(context,new ScaleGestureDetector.SimpleOnScaleGestureListener(){
            @Override public boolean onScale(ScaleGestureDetector d){pinched=true;zoom=Math.max(1,Math.min(6,zoom*d.getScaleFactor()));invalidate();return true;}
        });
    }
    void resetZoom(){zoom=1;panX=panY=0;invalidate();}
    @Override protected void onDraw(Canvas canvas){int save=canvas.save();canvas.translate(panX,panY);canvas.scale(zoom,zoom,getWidth()/2f,getHeight()/2f);super.onDraw(canvas);canvas.restoreToCount(save);}
    @Override public boolean onTouchEvent(MotionEvent e){
        detector.onTouchEvent(e);
        if(e.getActionMasked()==MotionEvent.ACTION_DOWN){startX=lastX=e.getX();lastY=e.getY();pinched=false;return true;}
        if(e.getPointerCount()==1&&!detector.isInProgress()&&e.getActionMasked()==MotionEvent.ACTION_MOVE&&zoom>1){
            panX=Math.max(-getWidth()*(zoom-1)/2,Math.min(getWidth()*(zoom-1)/2,panX+e.getX()-lastX));panY=Math.max(-getHeight()*(zoom-1)/2,Math.min(getHeight()*(zoom-1)/2,panY+e.getY()-lastY));invalidate();
        }
        if(e.getActionMasked()==MotionEvent.ACTION_UP&&!pinched&&zoom==1&&Math.abs(e.getX()-startX)>getWidth()*.2f)step.move(e.getX()<startX?1:-1);
        lastX=e.getX();lastY=e.getY();return true;
    }
}
