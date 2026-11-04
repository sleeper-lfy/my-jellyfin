package net.lumen.media;

import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Insets;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.GraphicsMode;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w360dp-h800dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
public class PlayerResponsiveLayoutTest {
    private static Field field(Class<?> type,String name)throws Exception{Field f=type.getDeclaredField(name);f.setAccessible(true);return f;}
    private static Object field(Object value,String name)throws Exception{return field(value.getClass(),name).get(value);}
    private static void call(Object value,String name)throws Exception{Method method=value.getClass().getDeclaredMethod(name);method.setAccessible(true);method.invoke(value);}
    private static void font(android.app.Activity activity,float scale){Configuration cfg=new Configuration(activity.getResources().getConfiguration());cfg.fontScale=scale;activity.getResources().updateConfiguration(cfg,activity.getResources().getDisplayMetrics());}
    private static void layout(View root,int width,int height){for(int pass=0;pass<3;pass++){root.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(height,View.MeasureSpec.EXACTLY));root.layout(0,0,width,height);}}
    private static boolean visible(View view){
        while(view!=null){if(view.getVisibility()!=View.VISIBLE)return false;view=view.getParent() instanceof View?(View)view.getParent():null;}return true;
    }
    private static void readable(View view){
        if(view.getVisibility()!=View.VISIBLE)return;
        if(view instanceof TextView){
            TextView text=(TextView)view;
            if(text.getText().length()>0&&text.getLayout()!=null){
                int available=text.getHeight()-text.getCompoundPaddingTop()-text.getCompoundPaddingBottom();
                assertTrue("裁字："+text.getText()+"，文字高 "+text.getLayout().getHeight()+"，可用 "+available,text.getLayout().getHeight()<=available);
                for(int line=0;line<text.getLayout().getLineCount();line++)assertEquals("常用操作不应省略文字："+text.getText(),0,text.getLayout().getEllipsisCount(line));
            }
        }
        if(view instanceof ViewGroup){ViewGroup parent=(ViewGroup)view;for(int i=0;i<parent.getChildCount();i++)readable(parent.getChildAt(i));}
    }
    private static void snapshot(View root,String name)throws Exception{
        String directory=System.getenv("LUMEN_UI_SCREENSHOTS");if(directory==null||directory.isEmpty())return;
        File path=new File(directory,name);assertTrue(path.getParentFile().isDirectory()||path.getParentFile().mkdirs());
        Bitmap image=Bitmap.createBitmap(root.getWidth(),root.getHeight(),Bitmap.Config.ARGB_8888);root.draw(new Canvas(image));
        try(FileOutputStream stream=new FileOutputStream(path)){assertTrue(image.compress(Bitmap.CompressFormat.PNG,100,stream));}image.recycle();
    }
    @Test public void narrowPlayersKeepReadableTextAndFullTouchTargetsAtLargeFontSizes()throws Exception{
        for(int width:new int[]{320,360})for(float scale:new float[]{1f,1.5f,2f}){
            RuntimeEnvironment.setQualifiers("w"+width+"dp-h800dp-mdpi");
            try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
                PlayerActivity activity=lifecycle.get();font(activity,scale);
                Method build=PlayerActivity.class.getDeclaredMethod("buildPlayerUi",android.content.SharedPreferences.class);build.setAccessible(true);build.invoke(activity,activity.getSharedPreferences("playback",0));
                field(PlayerActivity.class,"work").set(activity,new JSONObject().put("id",7).put("title","布局示例").put("rating",10).put("favorite",1).put("disliked",0));
                field(PlayerActivity.class,"file").set(activity,new JSONObject().put("id",70));call(activity,"refreshPersonal");
                View root=(View)field(activity,"root");LinearLayout top=(LinearLayout)field(activity,"topBar"),bottom=(LinearLayout)field(activity,"bottomBar"),playback=(LinearLayout)field(activity,"playbackRow"),vr=(LinearLayout)field(activity,"vrBar");
                layout(root,width,800);assertEquals(5,playback.getChildCount());assertTrue(top.getBottom()<=bottom.getTop());
                assertTrue(((View)field(activity,"seek")).getHeight()>=48);readable(bottom);
                ArrayList<View> targets=new ArrayList<>();top.addTouchables(targets);bottom.addTouchables(targets);
                for(View target:targets)if(target instanceof Button&&visible(target)){assertTrue("按钮宽度小于48dp："+target.getContentDescription(),target.getWidth()>=48);assertTrue(target.getHeight()>=48);}
                for(int i=0;i<playback.getChildCount();i++){Button button=(Button)playback.getChildAt(i);assertEquals("",button.getText().toString());assertNotNull(button.getContentDescription());}
                if(width==360&&scale==1.5f)snapshot(root,"player-360-font150.png");
                if(width==320&&scale==1f)snapshot(root,"player-320.png");
                vr.setVisibility(View.VISIBLE);layout(root,640,280);assertTrue("低高度VR控制不应覆盖顶栏",top.getBottom()<=bottom.getTop());readable(bottom);
                assertEquals(LinearLayout.HORIZONTAL,((LinearLayout)field(activity,"transportControls")).getOrientation());
                // A 360dp landscape window also becomes compact after reserving system bars/cutouts.
                root.dispatchApplyWindowInsets(new WindowInsets.Builder().setInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout(),Insets.of(28,12,0,24)).build());
                layout(root,800,360);assertTrue("安全区减少可用高度后，VR控制不应覆盖顶栏",top.getBottom()<=bottom.getTop());readable(bottom);
                assertEquals(LinearLayout.HORIZONTAL,((LinearLayout)field(activity,"transportControls")).getOrientation());
                assertTrue(top.getTop()>=12);assertTrue(bottom.getBottom()<=336);
                if(width==360&&scale==1.5f)snapshot(root,"player-vr-landscape-safe.png");
            }
        }
    }
    @Test public void remoteTransportButtonsKeepTheSameHeightWithLargeFonts()throws Exception{
        for(int width:new int[]{320,360}){
            RuntimeEnvironment.setQualifiers("w"+width+"dp-h800dp-mdpi");
            try(ActivityController<RemoteActivity> lifecycle=Robolectric.buildActivity(RemoteActivity.class).create()){
                RemoteActivity activity=lifecycle.get();font(activity,2f);call(activity,"buildUi");
                View root=((ViewGroup)activity.findViewById(android.R.id.content)).getChildAt(0);layout(root,width,800);
                PlaybackIconButton toggle=(PlaybackIconButton)field(activity,"togglePlayback");LinearLayout row=(LinearLayout)toggle.getParent();assertEquals(3,row.getChildCount());
                for(int i=0;i<row.getChildCount();i++){View button=row.getChildAt(i);assertEquals(56,button.getHeight());assertTrue(button.getWidth()>=48);assertNotNull(button.getContentDescription());}
                assertTrue(((View)field(activity,"seek")).getHeight()>=48);assertTrue(((View)field(activity,"volume")).getHeight()>=48);
            }
        }
    }
}
