package net.lumen.media;

import android.content.Context;
import android.view.View;
import android.view.ViewGroup;

/** Wrapping chips avoid horizontal scrolling when browsing with one hand. */
final class ChipLayout extends ViewGroup {
    final int gap;
    ChipLayout(Context context){super(context);gap=MediaStyle.dp(context,6);}
    @Override protected void onMeasure(int widthSpec,int heightSpec){
        int width=MeasureSpec.getSize(widthSpec),available=Math.max(0,width-getPaddingLeft()-getPaddingRight()),x=0,y=0,rowHeight=0;
        for(int i=0;i<getChildCount();i++){
            View child=getChildAt(i);if(child.getVisibility()==GONE)continue;
            int requested=child.getLayoutParams().width;
            child.measure(MeasureSpec.makeMeasureSpec(requested>=0?Math.min(requested,available):available,requested>=0?MeasureSpec.EXACTLY:MeasureSpec.AT_MOST),MeasureSpec.makeMeasureSpec(0,MeasureSpec.UNSPECIFIED));
            if(x>0&&x+child.getMeasuredWidth()>available){x=0;y+=rowHeight+gap;rowHeight=0;}
            x+=child.getMeasuredWidth()+gap;rowHeight=Math.max(rowHeight,child.getMeasuredHeight());
        }
        setMeasuredDimension(resolveSize(width,widthSpec),resolveSize(y+rowHeight+getPaddingTop()+getPaddingBottom(),heightSpec));
    }
    @Override protected void onLayout(boolean changed,int left,int top,int right,int bottom){
        int x=getPaddingLeft(),y=getPaddingTop(),rowHeight=0,limit=right-left-getPaddingRight();
        for(int i=0;i<getChildCount();i++){
            View child=getChildAt(i);if(child.getVisibility()==GONE)continue;int width=child.getMeasuredWidth(),height=child.getMeasuredHeight();
            if(x>getPaddingLeft()&&x+width>limit){x=getPaddingLeft();y+=rowHeight+gap;rowHeight=0;}
            child.layout(x,y,x+width,y+height);x+=width+gap;rowHeight=Math.max(rowHeight,height);
        }
    }
    @Override protected LayoutParams generateDefaultLayoutParams(){return new LayoutParams(LayoutParams.WRAP_CONTENT,LayoutParams.WRAP_CONTENT);}
}
