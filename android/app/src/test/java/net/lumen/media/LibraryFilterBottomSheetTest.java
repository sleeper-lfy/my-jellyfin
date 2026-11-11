package net.lumen.media;

import android.app.AlertDialog;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.AutoCompleteTextView;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.widget.NestedScrollView;
import com.google.android.material.chip.Chip;
import com.google.android.material.chip.ChipGroup;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.GraphicsMode;
import org.robolectric.shadows.ShadowDialog;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w393dp-h852dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
public class LibraryFilterBottomSheetTest {
    private void layout(View view,int width,int height){for(int i=0;i<3;i++){view.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(height,View.MeasureSpec.AT_MOST));view.layout(0,0,width,view.getMeasuredHeight());}}
    private void field(Object object,String name,Object value)throws Exception{Field field=object.getClass().getDeclaredField(name);field.setAccessible(true);field.set(object,value);}
    private Object read(Object object,String name)throws Exception{Field field=object.getClass().getDeclaredField(name);field.setAccessible(true);return field.get(object);}
    private void call(Object object,String name)throws Exception{Method method=object.getClass().getDeclaredMethod(name);method.setAccessible(true);method.invoke(object);}
    private List<AutoCompleteTextView> inputs(View view){List<AutoCompleteTextView> result=new ArrayList<>();if(view instanceof AutoCompleteTextView)result.add((AutoCompleteTextView)view);if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++)result.addAll(inputs(((ViewGroup)view).getChildAt(i)));return result;}
    private LibraryFilterBottomSheet longSheet(MainActivity activity){
        LinearLayout form=new LinearLayout(activity);form.setOrientation(LinearLayout.VERTICAL);for(int i=0;i<24;i++){TextView field=new TextView(activity);field.setText("筛选条件 "+i);field.setPadding(16,12,16,12);form.addView(field);}LibraryFilterBottomSheet sheet=new LibraryFilterBottomSheet(activity,form);sheet.show();return sheet;
    }
    private void insets(View content,int ime){ViewCompat.dispatchApplyWindowInsets(content,new WindowInsetsCompat.Builder().setInsets(WindowInsetsCompat.Type.systemBars(),Insets.of(0,24,0,24)).setInsets(WindowInsetsCompat.Type.ime(),Insets.of(0,0,0,ime)).setVisible(WindowInsetsCompat.Type.ime(),true).build());}
    @Test public void modernImeKeepsEveryFooterActionAboveKeyboardWhileFormStillScrolls(){
        try(ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            LibraryFilterBottomSheet sheet=longSheet(life.get());try{
                View content=sheet.findViewById(com.google.android.material.R.id.design_bottom_sheet).findViewWithTag("libraryFilterSheet");insets(content,260);layout(content,320,720);ViewGroup footer=content.findViewWithTag("filterFooter");NestedScrollView scroll=content.findViewWithTag("libraryFilterScroll");
                assertEquals(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_NOTHING,sheet.getWindow().getAttributes().softInputMode&WindowManager.LayoutParams.SOFT_INPUT_MASK_ADJUST);assertEquals(268,footer.getPaddingBottom());assertTrue(scroll.getHeight()>48);
                for(int which:new int[]{AlertDialog.BUTTON_NEUTRAL,AlertDialog.BUTTON_NEGATIVE,AlertDialog.BUTTON_POSITIVE}){View button=sheet.getButton(which);assertTrue(button.getHeight()>=48);assertTrue(footer.getTop()+button.getBottom()<=content.getHeight()-260);}
                int footerTop=footer.getTop();scroll.fullScroll(View.FOCUS_DOWN);assertTrue(scroll.getScrollY()>0);assertEquals(footerTop,footer.getTop());assertTrue(content.getHeight()<=720-24);
            }finally{sheet.dismiss();}
        }
    }
    @Test @Config(sdk=26) public void legacyResizeDoesNotAddKeyboardHeightTwice(){
        try(ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            LibraryFilterBottomSheet sheet=longSheet(life.get());try{View content=sheet.findViewById(com.google.android.material.R.id.design_bottom_sheet).findViewWithTag("libraryFilterSheet");insets(content,260);layout(content,320,460);View footer=content.findViewWithTag("filterFooter");assertEquals(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE,sheet.getWindow().getAttributes().softInputMode&WindowManager.LayoutParams.SOFT_INPUT_MASK_ADJUST);assertEquals(32,footer.getPaddingBottom());assertTrue(sheet.getButton(AlertDialog.BUTTON_POSITIVE).getHeight()>=48);}finally{sheet.dismiss();}
        }
    }
    @Test public void resetClearsEveryDraftFieldAndOnlyCommitsWhenApplied()throws Exception{
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            for(int i=0;i<8;i++)server.enqueue(new MockResponse().setBody("{\"items\":[],\"total\":0,\"tags\":[],\"actors\":[],\"years\":[]}"));server.start();MainActivity activity=life.get();field(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));
            String[] fields={"tagFilter","actorFilter","yearMinFilter","yearMaxFilter","ratingMinFilter","tagsAllFilter","tagsAnyFilter","tagsNotFilter","watchFilter"};String[] values={"自然","林夏","2000","2026","8","旅行","海岸","恐怖","progress"};for(int i=0;i<fields.length;i++)field(activity,fields[i],values[i]);field(activity,"favorites",true);field(activity,"watchlistOnly",true);call(activity,"showFilters");
            LibraryFilterBottomSheet sheet=(LibraryFilterBottomSheet)ShadowDialog.getLatestDialog();View content=sheet.getWindow().getDecorView();List<AutoCompleteTextView> inputs=inputs(content);assertEquals(8,inputs.size());AutoCompleteTextView rating=inputs.stream().filter(input->input.getText().toString().equals("8")).findFirst().get();assertEquals(11,rating.getAdapter().getCount());
            sheet.getButton(AlertDialog.BUTTON_NEUTRAL).performClick();assertTrue(sheet.isShowing());assertEquals("自然",read(activity,"tagFilter"));for(AutoCompleteTextView input:inputs)assertEquals("",input.getText().toString());
            ChipGroup preferences=content.findViewWithTag("filterPreferences");for(int i=0;i<preferences.getChildCount();i++)assertFalse(((Chip)preferences.getChildAt(i)).isChecked());ChipGroup watches=content.findViewWithTag("watchSegments");assertTrue(((Chip)watches.getChildAt(0)).isChecked());
            sheet.getButton(AlertDialog.BUTTON_POSITIVE).performClick();assertFalse(sheet.isShowing());for(String name:fields)assertEquals(name,"",read(activity,name));for(String name:new String[]{"favorites","watchlistOnly","dislikedOnly"})assertEquals(false,read(activity,name));
        }
    }
}
