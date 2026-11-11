package net.lumen.media;

import android.app.Activity;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.os.Looper;
import android.view.View;
import android.widget.ArrayAdapter;
import com.google.android.material.textfield.TextInputLayout;
import com.google.android.material.textfield.MaterialAutoCompleteTextView;
import android.widget.ImageButton;
import java.time.Duration;
import java.io.File;
import java.io.FileOutputStream;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.Shadows;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.GraphicsMode;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w393dp-h852dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
public class SearchDropdownLayoutTest {
    private void layout(View row,int width){
        for(int pass=0;pass<3;pass++){
            row.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(0,View.MeasureSpec.UNSPECIFIED));
            row.layout(0,0,width,row.getMeasuredHeight());
            Shadows.shadowOf(Looper.getMainLooper()).idle();
        }
    }
    private void snapshot(View view,String name)throws Exception{
        String directory=System.getenv("LUMEN_UI_SCREENSHOTS");if(directory==null)return;
        File path=new File(directory,name+".png");path.getParentFile().mkdirs();
        Bitmap bitmap=Bitmap.createBitmap(view.getWidth(),view.getHeight(),Bitmap.Config.ARGB_8888);
        view.draw(new Canvas(bitmap));try(FileOutputStream stream=new FileOutputStream(path)){bitmap.compress(Bitmap.CompressFormat.PNG,100,stream);}bitmap.recycle();
    }
    @Test public void vectorToggleStaysCenteredAndReachableInNarrowLargeTypeAndRtl()throws Exception{
        try(ActivityController<Activity> life=Robolectric.buildActivity(Activity.class).setup()){
            Activity activity=life.get();
            for(float scale:new float[]{1f,1.5f}){
                Configuration config=new Configuration(activity.getResources().getConfiguration());config.fontScale=scale;
                activity.getResources().updateConfiguration(config,activity.getResources().getDisplayMetrics());
                for(int direction:new int[]{View.LAYOUT_DIRECTION_LTR,View.LAYOUT_DIRECTION_RTL}){
                    SearchDropdown input=new SearchDropdown(activity);input.setSingleLine(true);input.setHint("搜索标签");
                    TextInputLayout row=SearchDropdown.row(input,activity.getString(R.string.search_dropdown_options,"标签"));
                    row.setLayoutDirection(direction);activity.setContentView(row);layout(row,288);
                    ImageButton toggle=row.findViewWithTag("searchDropdownToggle");
                    assertTrue(input instanceof MaterialAutoCompleteTextView);
                    assertEquals(TextInputLayout.END_ICON_DROPDOWN_MENU,row.getEndIconMode());
                    assertNotNull(toggle.getDrawable());assertEquals(24,toggle.getDrawable().getIntrinsicWidth());
                    assertTrue(toggle.getWidth()>=48);assertTrue(toggle.getHeight()>=48);
                    assertTrue(toggle.getContentDescription().toString().contains("标签"));
                    assertTrue(input.getWidth()>0);assertTrue(input.getHeight()>=56);
                    android.graphics.Rect fieldBounds=new android.graphics.Rect(0,0,input.getWidth(),input.getHeight()),iconBounds=new android.graphics.Rect(0,0,toggle.getWidth(),toggle.getHeight());
                    row.offsetDescendantRectToMyCoords(input,fieldBounds);row.offsetDescendantRectToMyCoords(toggle,iconBounds);
                    assertEquals(fieldBounds.centerY(),iconBounds.centerY(),1);
                    assertTrue(iconBounds.left>=0&&iconBounds.right<=row.getWidth());
                    int textLeft=fieldBounds.left+input.getCompoundPaddingLeft(),textRight=fieldBounds.right-input.getCompoundPaddingRight();
                    assertTrue("Text must not overlap the end icon: direction="+direction+", text="+textLeft+".."+textRight+", icon="+iconBounds,
                        direction==View.LAYOUT_DIRECTION_LTR?textRight<=iconBounds.left:textLeft>=iconBounds.right);
                    assertTrue("Official outlined input retains its start inset",input.getPaddingStart()>=16);
                    snapshot(row,"dropdown-"+direction+"-font"+(int)(scale*100));
                }
            }
        }
    }
    @Test public void toggleOpensEmptySuggestionsAndKeepsEditableTextAndSelection(){
        try(ActivityController<Activity> life=Robolectric.buildActivity(Activity.class).setup()){
            Activity activity=life.get();SearchDropdown input=new SearchDropdown(activity);input.setSingleLine(true);
            ArrayAdapter<String> choices=new ArrayAdapter<>(activity,android.R.layout.simple_dropdown_item_1line,new String[]{"剧情","纪录"});input.setAdapter(choices);
            TextInputLayout row=SearchDropdown.row(input,activity.getString(R.string.search_dropdown_options,"标签"));activity.setContentView(row);layout(row,288);
            ImageButton toggle=row.findViewWithTag("searchDropdownToggle");assertTrue(input.enoughToFilter());toggle.performClick();assertTrue(input.isPopupShowing());
            Shadows.shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(350));toggle.performClick();assertFalse(input.isPopupShowing());input.setText("自定义标签",false);Shadows.shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(350));toggle.performClick();
            assertEquals("自定义标签",input.getText().toString());assertTrue(input.isPopupShowing());input.dismissDropDown();
            input.setText(choices.getItem(1),false);assertEquals("纪录",input.getText().toString());
        }
    }
}
