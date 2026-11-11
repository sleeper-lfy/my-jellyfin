package net.lumen.media;

import android.content.Context;
import android.content.res.ColorStateList;
import android.view.ContextThemeWrapper;
import android.widget.AutoCompleteTextView;
import com.google.android.material.textfield.MaterialAutoCompleteTextView;
import com.google.android.material.textfield.TextInputLayout;
import net.lumen.media.ui.theme.NativeActionTokens;

/** Editable search field whose dropdown also opens before any text is entered. */
final class SearchDropdown extends MaterialAutoCompleteTextView {
    SearchDropdown(Context context){super(new ContextThemeWrapper(context,R.style.LumenNativeDropdown));setThreshold(1);}
    @Override public boolean enoughToFilter(){return true;}
    @Override public void setError(CharSequence error){
        TextInputLayout field=findContainer(this);if(field!=null)field.setError(error);else super.setError(error);
    }
    @Override public CharSequence getError(){TextInputLayout field=findContainer(this);return field!=null?field.getError():super.getError();}

    /** Official M3 editable exposed dropdown owns icon sizing, states and popup behavior. */
    static TextInputLayout row(AutoCompleteTextView input,String description){
        Context context=input.getContext();TextInputLayout field=new TextInputLayout(context);
        field.setHintEnabled(false);field.setBoxBackgroundMode(TextInputLayout.BOX_BACKGROUND_OUTLINE);
        float corner=MediaStyle.dp(context,NativeActionTokens.cardCornerDp());field.setBoxCornerRadii(corner,corner,corner,corner);
        field.setBoxStrokeColorStateList(new ColorStateList(new int[][]{{-android.R.attr.state_enabled},{android.R.attr.state_focused},{}},
            new int[]{NativeActionTokens.outlineVariant(true),NativeActionTokens.primary(true),NativeActionTokens.outlineVariant(true)}));
        field.setBoxStrokeErrorColor(ColorStateList.valueOf(NativeActionTokens.error(true)));
        field.setBoxBackgroundColor(NativeActionTokens.surface(true));
        field.setEndIconMode(TextInputLayout.END_ICON_DROPDOWN_MENU);
        field.setEndIconMinSize(MediaStyle.dp(context,NativeActionTokens.touchDp()));field.setEndIconContentDescription(description);
        field.setEndIconTintList(ColorStateList.valueOf(NativeActionTokens.onSurfaceVariant(true)));
        field.setErrorIconDrawable(null);
        input.setBackground(null);input.setTextAppearance(com.google.android.material.R.style.TextAppearance_Material3_BodyMedium);
        input.setTextColor(NativeActionTokens.onSurface(true));input.setHintTextColor(NativeActionTokens.onSurfaceVariant(true));
        if(input instanceof MaterialAutoCompleteTextView)((MaterialAutoCompleteTextView)input).setDropDownBackgroundTintList(ColorStateList.valueOf(NativeActionTokens.surfaceContainerHigh(true)));
        input.setMinHeight(MediaStyle.dp(context,NativeActionTokens.inputHeightDp()));
        field.addView(input,new android.widget.LinearLayout.LayoutParams(-1,-2));
        field.findViewById(com.google.android.material.R.id.text_input_end_icon).setTag("searchDropdownToggle");
        return field;
    }
    static TextInputLayout container(AutoCompleteTextView input){
        TextInputLayout field=findContainer(input);if(field!=null)return field;
        throw new IllegalStateException("Dropdown is not attached to its Material input container");
    }
    private static TextInputLayout findContainer(AutoCompleteTextView input){
        android.view.ViewParent parent=input.getParent();
        while(parent!=null){if(parent instanceof TextInputLayout)return (TextInputLayout)parent;parent=parent.getParent();}
        return null;
    }
}
