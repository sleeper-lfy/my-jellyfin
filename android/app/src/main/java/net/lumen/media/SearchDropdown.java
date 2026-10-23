package net.lumen.media;

import android.content.Context;
import android.widget.AutoCompleteTextView;

/** Editable search field whose dropdown also opens before any text is entered. */
final class SearchDropdown extends AutoCompleteTextView {
    SearchDropdown(Context context){super(context);setThreshold(1);}
    @Override public boolean enoughToFilter(){return true;}
}
