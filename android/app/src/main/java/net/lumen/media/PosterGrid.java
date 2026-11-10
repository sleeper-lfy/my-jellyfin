package net.lumen.media;

import android.content.Context;
import android.view.View;
import android.view.ViewGroup;

/** Poster dimensions follow the window, including split-screen and large-font layouts. */
final class PosterGrid extends ViewGroup {
    private final int gap;
    private int columns=2;
    PosterGrid(Context context){super(context);gap=MediaStyle.dp(context,12);}
    @Override protected void onMeasure(int ws,int hs){
        int width=MeasureSpec.getSize(ws),available=Math.max(0,width-getPaddingLeft()-getPaddingRight());
        columns=Math.max(2,Math.min(5,available/MediaStyle.dp(getContext(),165)));
        int cell=Math.max(0,(available-(columns-1)*gap)/columns),height=getPaddingTop()+getPaddingBottom(),row=0,count=0;
        for(int i=0;i<getChildCount();i++){
            View child=getChildAt(i);if(child.getVisibility()==GONE)continue;
            if(child instanceof ViewGroup){ViewGroup card=(ViewGroup)child;if(card.getChildCount()>0){View art=card.getChildAt(0);ViewGroup.LayoutParams lp=art.getLayoutParams();int target=Math.round((cell-card.getPaddingLeft()-card.getPaddingRight())*1.5f);if(lp.height!=target){lp.height=target;art.setLayoutParams(lp);}}}
            child.measure(MeasureSpec.makeMeasureSpec(cell,MeasureSpec.EXACTLY),MeasureSpec.makeMeasureSpec(0,MeasureSpec.UNSPECIFIED));
            row=Math.max(row,child.getMeasuredHeight());count++;
            if(count%columns==0){height+=row+gap;row=0;}
        }
        if(count%columns!=0)height+=row;else if(count>0)height-=gap;
        setMeasuredDimension(resolveSize(width,ws),resolveSize(height,hs));
    }
    @Override protected void onLayout(boolean changed,int l,int t,int r,int b){
        int x=getPaddingLeft(),y=getPaddingTop(),row=0,column=0;
        for(int i=0;i<getChildCount();i++){View child=getChildAt(i);if(child.getVisibility()==GONE)continue;
            child.layout(x,y,x+child.getMeasuredWidth(),y+child.getMeasuredHeight());row=Math.max(row,child.getMeasuredHeight());
            if(++column==columns){x=getPaddingLeft();y+=row+gap;row=0;column=0;}else x+=child.getMeasuredWidth()+gap;
        }
    }
    @Override protected LayoutParams generateDefaultLayoutParams(){return new LayoutParams(LayoutParams.WRAP_CONTENT,LayoutParams.WRAP_CONTENT);}
}
