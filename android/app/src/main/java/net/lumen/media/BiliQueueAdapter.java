package net.lumen.media;

import android.content.ClipData;
import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.drawable.Drawable;
import android.text.TextUtils;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.AbsListView;
import android.widget.ArrayAdapter;
import android.widget.CheckedTextView;
import java.util.ArrayList;
import java.util.function.IntConsumer;
import net.lumen.media.ui.theme.NativeActionTokens;

/** Two-line queue rows with an actual draggable handle and accessible move-button alternatives. */
final class BiliQueueAdapter extends ArrayAdapter<String> {
    private final IntConsumer select;
    BiliQueueAdapter(Context context,IntConsumer select){super(context,android.R.layout.simple_list_item_single_choice,new ArrayList<>());this.select=select;}
    @Override public View getView(int position,View reuse,ViewGroup parent){
        CheckedTextView row=(CheckedTextView)super.getView(position,reuse,parent);row.setLayoutParams(new AbsListView.LayoutParams(-1,-2));row.setSingleLine(false);row.setMaxLines(2);row.setEllipsize(TextUtils.TruncateAt.END);row.setTextSize(NativeActionTokens.bodyMediumSp());row.setMinHeight(MediaStyle.dp(getContext(),72));row.setPadding(MediaStyle.dp(getContext(),16),MediaStyle.dp(getContext(),8),MediaStyle.dp(getContext(),16),MediaStyle.dp(getContext(),8));row.setCheckMarkDrawable((Drawable)null);row.setTextColor(new ColorStateList(new int[][]{{android.R.attr.state_checked},{}},new int[]{NativeActionTokens.primary(true),NativeActionTokens.onSurface(true)}));
        Drawable handle=getContext().getDrawable(R.drawable.bili_drag_handle).mutate();handle.setTint(NativeActionTokens.onSurfaceVariant(true));handle.setBounds(0,0,MediaStyle.dp(getContext(),24),MediaStyle.dp(getContext(),24));row.setCompoundDrawablesRelative(null,null,handle,null);row.setCompoundDrawablePadding(MediaStyle.dp(getContext(),12));row.setContentDescription(getItem(position)+"，按住右侧把手拖动排序，也可使用上移和下移按钮");
        row.setOnTouchListener((view,event)->{boolean handleArea=view.getLayoutDirection()==View.LAYOUT_DIRECTION_RTL?event.getX()<MediaStyle.dp(getContext(),48):event.getX()>=view.getWidth()-MediaStyle.dp(getContext(),48);if(handleArea&&event.getActionMasked()==MotionEvent.ACTION_DOWN){select.accept(position);return view.startDragAndDrop(ClipData.newPlainText("queueIndex",Integer.toString(position)),new View.DragShadowBuilder(view),position,0);}return false;});return row;
    }
}
