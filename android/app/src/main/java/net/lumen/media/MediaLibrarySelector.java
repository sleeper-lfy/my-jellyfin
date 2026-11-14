package net.lumen.media;

import android.content.Context;
import android.view.ContextThemeWrapper;
import android.view.View;
import android.widget.HorizontalScrollView;
import com.google.android.material.chip.Chip;
import com.google.android.material.chip.ChipGroup;
import net.lumen.media.ui.theme.NativeActionTokens;
import org.json.JSONArray;
import org.json.JSONObject;

/** Read-only named libraries; configuration belongs to the computer. */
final class MediaLibrarySelector {
    interface Selection {void select(long id,String name,String kind);}
    static View create(Context context,JSONArray items,long selected,Selection action,Runnable refresh){
        HorizontalScrollView scroll=new HorizontalScrollView(context);scroll.setTag("mediaLibrarySelector");scroll.setHorizontalScrollBarEnabled(false);
        scroll.setPadding(MediaStyle.dp(context,NativeActionTokens.pageDp()),0,MediaStyle.dp(context,NativeActionTokens.pageDp()),0);
        ChipGroup group=new ChipGroup(new ContextThemeWrapper(context,R.style.LumenNativeActionsDark));group.setSingleLine(true);group.setSingleSelection(true);group.setSelectionRequired(true);group.setChipSpacingHorizontal(MediaStyle.dp(context,NativeActionTokens.spaceSmDp()));
        Chip all=chip(context,context.getString(R.string.media_libraries_all),selected==0);all.setTag("mediaLibrary:0");all.setOnClickListener(v->action.select(0,"",""));group.addView(all);
        for(int i=0;i<items.length();i++){
            JSONObject item=items.optJSONObject(i);if(item==null||item.optLong("id")<=0||item.optString("name").isEmpty())continue;
            long id=item.optLong("id");String name=item.optString("name"),kind=item.optString("kind");
            Chip choice=chip(context,name,id==selected);choice.setTag("mediaLibrary:"+id);choice.setContentDescription(context.getString(R.string.media_libraries_description,name,item.optInt("count")));choice.setOnClickListener(v->action.select(id,name,kind));group.addView(choice);
        }
        Chip reload=chip(context,context.getString(R.string.media_libraries_refresh),false);reload.setCheckable(false);reload.setOnClickListener(v->refresh.run());group.addView(reload);
        scroll.addView(group);return scroll;
    }
    private static Chip chip(Context context,String label,boolean checked){
        Chip chip=LibraryFilterBottomSheet.choice(context,R.string.media_libraries_all,"",checked);chip.setText(label);chip.setMaxWidth(MediaStyle.dp(context,220));chip.setEllipsize(android.text.TextUtils.TruncateAt.END);return chip;
    }
}
