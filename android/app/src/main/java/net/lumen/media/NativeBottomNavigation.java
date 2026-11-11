package net.lumen.media;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.drawable.StateListDrawable;
import android.view.ContextThemeWrapper;
import android.view.MenuItem;
import android.view.View;
import androidx.core.content.ContextCompat;
import androidx.core.graphics.ColorUtils;
import com.google.android.material.bottomnavigation.BottomNavigationView;
import com.google.android.material.navigation.NavigationBarView;
import java.util.function.Consumer;
import net.lumen.media.ui.theme.NativeActionTokens;

/** Official Material navigation for the Java pages, sharing the established theme roles. */
final class NativeBottomNavigation {
    private static final String[] PAGES={"home","library","discover","mine"};
    private static final int[] LABELS={R.string.design_system_nav_home,R.string.design_system_nav_library,
        R.string.design_system_nav_discover,R.string.design_system_nav_mine};
    private static final int[] OUTLINED={R.drawable.design_system_home,R.drawable.design_system_library,
        R.drawable.design_system_discover,R.drawable.design_system_mine};
    private static final int[] FILLED={R.drawable.design_system_home_filled,R.drawable.design_system_library_filled,
        R.drawable.design_system_discover_filled,R.drawable.design_system_mine_filled};

    static BottomNavigationView create(Context context,String active,Consumer<String> onSelect){
        Context themed=new ContextThemeWrapper(context,R.style.LumenNativeActionsDark);
        BottomNavigationView navigation=new BottomNavigationView(themed);
        navigation.setTag("primaryNavigation");
        navigation.setLabelVisibilityMode(NavigationBarView.LABEL_VISIBILITY_LABELED);
        navigation.setItemHorizontalTranslationEnabled(false);
        navigation.setItemActiveIndicatorEnabled(true);
        navigation.setBackgroundColor(NativeActionTokens.surfaceContainer(true));
        navigation.setItemActiveIndicatorColor(ColorStateList.valueOf(NativeActionTokens.container(true,0,false)));
        ColorStateList tint=new ColorStateList(new int[][]{{android.R.attr.state_checked},{}},
            new int[]{NativeActionTokens.primary(true),NativeActionTokens.onSurfaceVariant(true)});
        navigation.setItemIconTintList(tint);navigation.setItemTextColor(tint);
        navigation.setItemRippleColor(ColorStateList.valueOf(ColorUtils.setAlphaComponent(NativeActionTokens.primary(true),31)));
        int[] ids=new int[PAGES.length];int selected=0;
        for(int i=0;i<PAGES.length;i++){
            ids[i]=View.generateViewId();
            StateListDrawable icon=new StateListDrawable();
            icon.addState(new int[]{android.R.attr.state_checked},ContextCompat.getDrawable(themed,FILLED[i]));
            icon.addState(new int[]{},ContextCompat.getDrawable(themed,OUTLINED[i]));
            navigation.getMenu().add(0,ids[i],i,context.getString(LABELS[i])).setIcon(icon).setCheckable(true);
            if(PAGES[i].equals(active))selected=i;
        }
        navigation.setSelectedItemId(ids[selected]);
        for(int i=0;i<PAGES.length;i++)navigation.findViewById(ids[i]).setTag("nav:"+PAGES[i]);
        navigation.setOnItemSelectedListener(item->{select(item,ids,onSelect);return true;});
        navigation.setOnItemReselectedListener(item->select(item,ids,onSelect));
        return navigation;
    }
    private static void select(MenuItem item,int[] ids,Consumer<String> onSelect){
        for(int i=0;i<ids.length;i++)if(ids[i]==item.getItemId()){onSelect.accept(PAGES[i]);return;}
    }
}
