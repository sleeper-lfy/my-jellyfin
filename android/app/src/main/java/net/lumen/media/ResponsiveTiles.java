package net.lumen.media;

import android.content.Context;
import android.view.View;
import android.view.ViewGroup;

/** Equal-width category tiles, reflowing to the actual available width. */
final class ResponsiveTiles extends ViewGroup {
    private final int gap;
    private int columns=2;
    ResponsiveTiles(Context context){super(context);gap=MediaStyle.dp(context,8);}
    @Override protected void onMeasure(int widthSpec,int heightSpec){
        int width=MeasureSpec.getSize(widthSpec),available=Math.max(0,width-getPaddingLeft()-getPaddingRight());
        columns=available>=MediaStyle.dp(getContext(),560)?3:2;
        int cell=Math.max(0,(available-(columns-1)*gap)/columns),height=getPaddingTop()+getPaddingBottom(),rowHeight=0,count=0;
        for(int i=0;i<getChildCount();i++){
            View child=getChildAt(i);if(child.getVisibility()==GONE)continue;
            child.measure(MeasureSpec.makeMeasureSpec(cell,MeasureSpec.EXACTLY),MeasureSpec.makeMeasureSpec(0,MeasureSpec.UNSPECIFIED));rowHeight=Math.max(rowHeight,child.getMeasuredHeight());count++;
            if(count%columns==0){height+=rowHeight+gap;rowHeight=0;}
        }
        if(count%columns!=0)height+=rowHeight;else if(count>0)height-=gap;
        setMeasuredDimension(resolveSize(width,widthSpec),resolveSize(height,heightSpec));
    }
    @Override protected void onLayout(boolean changed,int left,int top,int right,int bottom){
        int x=getPaddingLeft(),y=getPaddingTop(),rowHeight=0,column=0;
        for(int i=0;i<getChildCount();i++){
            View child=getChildAt(i);if(child.getVisibility()==GONE)continue;
            child.layout(x,y,x+child.getMeasuredWidth(),y+child.getMeasuredHeight());rowHeight=Math.max(rowHeight,child.getMeasuredHeight());column++;
            if(column==columns){x=getPaddingLeft();y+=rowHeight+gap;rowHeight=0;column=0;}else x+=child.getMeasuredWidth()+gap;
        }
    }
    @Override protected LayoutParams generateDefaultLayoutParams(){return new LayoutParams(LayoutParams.WRAP_CONTENT,LayoutParams.WRAP_CONTENT);}
}
