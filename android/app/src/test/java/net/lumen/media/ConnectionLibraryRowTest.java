package net.lumen.media;

import android.app.Activity;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Rect;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.io.File;
import java.io.FileOutputStream;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.GraphicsMode;
import net.lumen.media.ui.theme.NativeActionTokens;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w393dp-h852dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
public class ConnectionLibraryRowTest {
    @SuppressWarnings("deprecation") private void font(Activity activity,float scale){
        Configuration configuration=new Configuration(activity.getResources().getConfiguration());configuration.fontScale=scale;
        activity.getResources().getDisplayMetrics().scaledDensity=activity.getResources().getDisplayMetrics().density*scale;
        activity.getResources().updateConfiguration(configuration,activity.getResources().getDisplayMetrics());
    }
    private void layout(View root,int width){
        for(int pass=0;pass<2;pass++){root.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(0,View.MeasureSpec.UNSPECIFIED));root.layout(0,0,width,root.getMeasuredHeight());}
    }
    private Rect bounds(ViewGroup parent,View child){Rect bounds=new Rect(0,0,child.getWidth(),child.getHeight());parent.offsetDescendantRectToMyCoords(child,bounds);return bounds;}
    private void snapshot(View view,String name)throws Exception{
        String directory=System.getenv("LUMEN_UI_SCREENSHOTS");if(directory==null)return;File target=new File(directory,name+".png");target.getParentFile().mkdirs();Bitmap bitmap=Bitmap.createBitmap(view.getWidth(),view.getHeight(),Bitmap.Config.ARGB_8888);view.draw(new Canvas(bitmap));try(FileOutputStream stream=new FileOutputStream(target)){bitmap.compress(Bitmap.CompressFormat.PNG,100,stream);}bitmap.recycle();
    }
    @Test public void savedAndDiscoveredLibrariesKeepOneInsetTextColumnAtNarrowWidthsAndLargeFonts()throws Exception{
        try(ActivityController<Activity> life=Robolectric.buildActivity(Activity.class).create()){
            Activity activity=life.get();String address="http://media-library-with-a-long-name.local:8097";
            for(float scale:new float[]{1f,1.5f}){
                font(activity,scale);LinearLayout rows=new LinearLayout(activity);rows.setOrientation(LinearLayout.VERTICAL);
                ConnectionLibraryRow saved=new ConnectionLibraryRow(activity,"当前保存的媒体库",address,R.drawable.design_system_connections,()->{});
                ConnectionLibraryRow discovered=new ConnectionLibraryRow(activity,"客厅电脑 · 家庭影片与纪录片媒体库",address,R.drawable.design_system_remote,()->{});
                rows.addView(saved,new LinearLayout.LayoutParams(-1,-2));rows.addView(discovered,new LinearLayout.LayoutParams(-1,-2));
                for(int width:new int[]{393,320}){
                    layout(rows,width);
                    for(ConnectionLibraryRow row:new ConnectionLibraryRow[]{saved,discovered}){
                        TextView title=row.findViewWithTag("connectionLibraryName"),location=row.findViewWithTag("connectionLibraryAddress");
                        Rect titleBounds=bounds(row,title),addressBounds=bounds(row,location),iconBounds=bounds(row,row.findViewWithTag("connectionLibraryIcon")),arrowBounds=bounds(row,row.findViewWithTag("connectionLibraryArrow"));
                        assertEquals("Title and address must use the same start inset",titleBounds.left,addressBounds.left);assertEquals(titleBounds.right,addressBounds.right);
                        assertTrue(titleBounds.left-iconBounds.right>=MediaStyle.dp(activity,NativeActionTokens.spaceMdDp()));assertTrue(arrowBounds.left-titleBounds.right>=MediaStyle.dp(activity,NativeActionTokens.spaceSmDp()));
                        assertTrue(iconBounds.left>=MediaStyle.dp(activity,NativeActionTokens.spaceLgDp()));assertTrue(arrowBounds.right<=row.getWidth()-MediaStyle.dp(activity,NativeActionTokens.spaceLgDp()));
                        assertTrue(titleBounds.top>=MediaStyle.dp(activity,NativeActionTokens.spaceSmDp()));assertTrue(addressBounds.top-titleBounds.bottom>=MediaStyle.dp(activity,NativeActionTokens.spaceXsDp()));
                        assertTrue(addressBounds.bottom<=row.getHeight()-MediaStyle.dp(activity,NativeActionTokens.spaceSmDp()));assertTrue(row.getHeight()>=MediaStyle.dp(activity,48));
                        assertTrue(title.getLayout().getHeight()<=title.getHeight());assertTrue(location.getLayout().getHeight()<=location.getHeight());assertTrue(title.getLayout().getLineCount()<=2);assertTrue(location.getLayout().getLineCount()<=2);
                        assertEquals(address,location.getText().toString());assertEquals(View.TEXT_DIRECTION_LTR,location.getTextDirection());
                    }
                    snapshot(rows,"connection-libraries-"+width+"-font"+Math.round(scale*100));
                }
            }
        }
    }
    @Test public void wholeRowIsOneAccessibleActionAndAnEmptyAddressDoesNotLeaveAnEmptyLine(){
        try(ActivityController<Activity> life=Robolectric.buildActivity(Activity.class).create()){
            Activity activity=life.get();AtomicInteger selected=new AtomicInteger();
            ConnectionLibraryRow row=new ConnectionLibraryRow(activity,"连接你的家庭媒体库","",R.drawable.design_system_connections,selected::incrementAndGet);
            layout(row,320);assertTrue(row.isClickable());assertTrue(row.isFocusable());assertTrue(row.performClick());assertEquals(1,selected.get());assertEquals("连接你的家庭媒体库",row.getContentDescription());assertNull(row.findViewWithTag("connectionLibraryAddress"));
            assertTrue(row.getHeight()>=MediaStyle.dp(activity,48));assertEquals(View.IMPORTANT_FOR_ACCESSIBILITY_NO,row.findViewWithTag("connectionLibraryName").getImportantForAccessibility());assertEquals(View.IMPORTANT_FOR_ACCESSIBILITY_NO,row.findViewWithTag("connectionLibraryIcon").getImportantForAccessibility());
        }
    }
}
