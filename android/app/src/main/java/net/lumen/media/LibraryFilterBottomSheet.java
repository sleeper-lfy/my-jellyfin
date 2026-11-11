package net.lumen.media;

import android.app.AlertDialog;
import android.content.Context;
import android.content.res.ColorStateList;
import android.os.Build;
import android.view.ContextThemeWrapper;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;
import androidx.core.widget.NestedScrollView;
import com.google.android.material.bottomsheet.BottomSheetBehavior;
import com.google.android.material.bottomsheet.BottomSheetDialog;
import com.google.android.material.button.MaterialButton;
import com.google.android.material.chip.Chip;
import com.google.android.material.chip.ChipGroup;
import com.google.android.material.shape.MaterialShapeDrawable;
import net.lumen.media.ui.theme.NativeActionTokens;

/** Official Material 3 sheet with a scrolling form and persistent accessible actions. */
final class LibraryFilterBottomSheet extends BottomSheetDialog {
    private final MaterialButton reset,cancel,apply;
    private final LinearLayout footer;

    LibraryFilterBottomSheet(Context context,LinearLayout form){
        super(new ContextThemeWrapper(context,R.style.LumenNativeActionsDark),R.style.LumenLibraryFilterSheet);
        Context themed=getContext();
        SheetColumn content=new SheetColumn(themed);content.setTag("libraryFilterSheet");
        TextView title=new TextView(themed);title.setText(R.string.library_filter_title);title.setTextAppearance(com.google.android.material.R.style.TextAppearance_Material3_TitleLarge);title.setTextColor(NativeActionTokens.onSurface(true));title.setPadding(dp(NativeActionTokens.pageDp()),dp(NativeActionTokens.spaceLgDp()),dp(NativeActionTokens.pageDp()),dp(NativeActionTokens.spaceSmDp()));content.addView(title,new LinearLayout.LayoutParams(-1,-2));
        NestedScrollView scroll=new NestedScrollView(themed);scroll.setTag("libraryFilterScroll");scroll.setFillViewport(true);scroll.setClipToPadding(false);scroll.addView(form,new NestedScrollView.LayoutParams(-1,-2));content.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        footer=MediaStyle.actionRow(themed);footer.setTag("filterFooter");footer.setPadding(dp(NativeActionTokens.pageDp()),dp(NativeActionTokens.spaceSmDp()),dp(NativeActionTokens.pageDp()),dp(NativeActionTokens.spaceSmDp()));
        reset=action(R.string.discovery_filter_reset,"filterReset",false);cancel=action(R.string.library_filter_cancel,"filterCancel",false);apply=action(R.string.discovery_filter_apply,"filterApply",true);
        footer.addView(reset,new LinearLayout.LayoutParams(0,-2,1));footer.addView(cancel,new LinearLayout.LayoutParams(0,-2,1));footer.addView(apply,new LinearLayout.LayoutParams(0,-2,1));content.addView(footer,new LinearLayout.LayoutParams(-1,-2));
        setContentView(content);
        // Edge-to-edge uses explicit IME insets on modern Android. Older windows
        // resize instead, so their keyboard height must not be added a second time.
        getWindow().setSoftInputMode((Build.VERSION.SDK_INT>=30?WindowManager.LayoutParams.SOFT_INPUT_ADJUST_NOTHING:WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)|WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN);
        ViewCompat.setOnApplyWindowInsetsListener(content,(view,insets)->{
            Insets bars=insets.getInsets(WindowInsetsCompat.Type.systemBars());
            int bottom=Build.VERSION.SDK_INT>=30?Math.max(bars.bottom,insets.getInsets(WindowInsetsCompat.Type.ime()).bottom):bars.bottom;
            content.safeTop=bars.top;content.setPadding(bars.left,0,bars.right,0);
            footer.setPadding(dp(NativeActionTokens.pageDp()),dp(NativeActionTokens.spaceSmDp()),dp(NativeActionTokens.pageDp()),dp(NativeActionTokens.spaceSmDp())+bottom);
            content.requestLayout();
            return insets;
        });
        cancel.setOnClickListener(view->dismiss());
    }
    private int dp(float value){return MediaStyle.dp(getContext(),value);}
    private MaterialButton action(int label,String tag,boolean primary){
        MaterialButton button=(MaterialButton)MediaStyle.action(getContext());button.setText(label);button.setTag(tag);MediaStyle.button(button,primary,false,false);if(!primary)BiliAuxiliaryUi.textAction(button,false);return button;
    }
    MaterialButton getButton(int which){
        if(which==AlertDialog.BUTTON_POSITIVE)return apply;if(which==AlertDialog.BUTTON_NEGATIVE)return cancel;if(which==AlertDialog.BUTTON_NEUTRAL)return reset;throw new IllegalArgumentException("Unknown sheet action");
    }
    static ChipGroup choices(Context context,String tag){
        ChipGroup group=new ChipGroup(new ContextThemeWrapper(context,R.style.LumenNativeActionsDark));group.setTag(tag);group.setChipSpacingHorizontal(MediaStyle.dp(context,NativeActionTokens.spaceSmDp()));group.setChipSpacingVertical(MediaStyle.dp(context,NativeActionTokens.spaceSmDp()));return group;
    }
    static Chip choice(Context context,int label,String tag,boolean checked){
        Context themed=new ContextThemeWrapper(context,R.style.LumenNativeActionsDark);
        Chip chip=(Chip)android.view.LayoutInflater.from(themed).inflate(R.layout.library_filter_chip,null,false);chip.setId(View.generateViewId());chip.setText(label);chip.setTag(tag);chip.setChecked(checked);
        chip.setTextColor(new ColorStateList(new int[][]{{android.R.attr.state_checked},{}},new int[]{NativeActionTokens.onPrimaryContainer(true),NativeActionTokens.onSurface(true)}));
        chip.setChipBackgroundColor(new ColorStateList(new int[][]{{android.R.attr.state_checked},{}},new int[]{NativeActionTokens.primaryContainer(true),NativeActionTokens.surfaceContainerHigh(true)}));
        chip.setChipStrokeColor(ColorStateList.valueOf(NativeActionTokens.outlineVariant(true)));chip.setCheckedIconTint(ColorStateList.valueOf(NativeActionTokens.primary(true)));chip.setRippleColor(ColorStateList.valueOf((NativeActionTokens.primary(true)&0x00ffffff)|0x1f000000));chip.setEnsureMinTouchTargetSize(true);chip.ensureAccessibleTouchTarget(MediaStyle.dp(context,NativeActionTokens.touchDp()));return chip;
    }
    static TextView section(Context context,int label){
        TextView title=new TextView(context);title.setText(label);title.setTextAppearance(com.google.android.material.R.style.TextAppearance_Material3_TitleSmall);title.setTextColor(NativeActionTokens.onSurface(true));title.setPadding(0,MediaStyle.dp(context,NativeActionTokens.spaceSmDp()),0,MediaStyle.dp(context,NativeActionTokens.spaceSmDp()));return title;
    }
    @Override protected void onStart(){
        super.onStart();new WindowInsetsControllerCompat(getWindow(),getWindow().getDecorView()).setAppearanceLightNavigationBars(false);View sheet=findViewById(com.google.android.material.R.id.design_bottom_sheet);
        if(sheet!=null){sheet.setBackgroundTintList(ColorStateList.valueOf(NativeActionTokens.surfaceContainer(true)));if(sheet.getBackground() instanceof MaterialShapeDrawable){MaterialShapeDrawable shape=(MaterialShapeDrawable)sheet.getBackground();shape.setShapeAppearanceModel(shape.getShapeAppearanceModel().toBuilder().setTopLeftCornerSize(dp(NativeActionTokens.sheetCornerDp())).setTopRightCornerSize(dp(NativeActionTokens.sheetCornerDp())).build());}}
        getBehavior().setSkipCollapsed(true);getBehavior().setState(BottomSheetBehavior.STATE_EXPANDED);
    }
    private static final class SheetColumn extends LinearLayout {
        int safeTop;
        SheetColumn(Context context){super(context);setOrientation(VERTICAL);}
        @Override protected void onMeasure(int widthSpec,int heightSpec){
            if(MeasureSpec.getMode(heightSpec)==MeasureSpec.EXACTLY){super.onMeasure(widthSpec,heightSpec);return;}
            int available=MeasureSpec.getMode(heightSpec)==MeasureSpec.UNSPECIFIED?getResources().getDisplayMetrics().heightPixels:MeasureSpec.getSize(heightSpec);
            int height=Math.max(1,Math.min(Math.round(available*.92f),available-safeTop));super.onMeasure(widthSpec,MeasureSpec.makeMeasureSpec(height,MeasureSpec.EXACTLY));
        }
    }
}
