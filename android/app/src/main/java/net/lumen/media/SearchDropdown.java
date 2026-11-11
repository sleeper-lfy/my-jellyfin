package net.lumen.media;

import android.content.Context;
import androidx.appcompat.widget.AppCompatAutoCompleteTextView;

/** Editable search field whose dropdown also opens before any text is entered. */
final class SearchDropdown extends AppCompatAutoCompleteTextView {
    SearchDropdown(Context context){super(context);setThreshold(1);}
    @Override public boolean enoughToFilter(){return true;}
}
