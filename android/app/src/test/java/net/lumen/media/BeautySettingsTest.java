package net.lumen.media;

import android.app.AlertDialog;
import android.widget.CheckBox;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.shadows.ShadowAlertDialog;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class) @Config(sdk=33)
public class BeautySettingsTest {
    private static void set(Object target,String name,Object value)throws Exception{Field f=target.getClass().getDeclaredField(name);f.setAccessible(true);f.set(target,value);}
    private static Object get(Object target,String name)throws Exception{Field f=target.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(target);}
    private static void call(Object target,String name)throws Exception{Method m=target.getClass().getDeclaredMethod(name);m.setAccessible(true);m.invoke(target);}
    @Test public void defaultsAndBounds()throws Exception{
        BeautySettings defaults=new BeautySettings(null);assertFalse(defaults.enabled);assertEquals(.35f,defaults.smoothing,.001);
        BeautySettings value=new BeautySettings(new JSONObject().put("enabled",true).put("smoothing",200).put("brighten",-5));
        assertTrue(value.enabled);assertEquals(1,value.smoothing,0);assertEquals(0,value.brighten,0);
    }
    @Test public void realSettingsDialogSwitchesFlatRenderAndSavesPerFileWithoutChangingVr()throws Exception{
        try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=lifecycle.get();
            Method build=PlayerActivity.class.getDeclaredMethod("buildPlayerUi",android.content.SharedPreferences.class);build.setAccessible(true);build.invoke(activity,activity.getSharedPreferences("playback",0));
            set(activity,"api",new Api(new Connection("http://127.0.0.1:8097","test-token-0123456789012345")));
            set(activity,"file",new JSONObject().put("id",88));
            call(activity,"beautySettings");AlertDialog dialog=ShadowAlertDialog.getLatestAlertDialog();
            java.util.ArrayList<android.view.View> controls=new java.util.ArrayList<>();collect(dialog.getWindow().getDecorView(),controls);
            CheckBox enabled=(CheckBox)controls.stream().filter(v->v instanceof CheckBox).findFirst().get();
            SeekBar smoothing=(SeekBar)controls.stream().filter(v->v instanceof SeekBar&&"磨皮强度".contentEquals(v.getContentDescription())).findFirst().get();
            enabled.setChecked(true);smoothing.setProgress(75);dialog.getButton(AlertDialog.BUTTON_POSITIVE).performClick();
            org.robolectric.Shadows.shadowOf(android.os.Looper.getMainLooper()).idle();
            JSONObject saved=(JSONObject)get(activity,"filePreferences");assertTrue(saved.getJSONObject("beauty").getBoolean("enabled"));assertEquals(75,saved.getJSONObject("beauty").getInt("smoothing"));
            Method gl=PlayerActivity.class.getDeclaredMethod("usesGlVideo");gl.setAccessible(true);assertEquals(true,gl.invoke(activity));assertEquals(false,get(activity,"vrEnabled"));
            String shader=VrProjection.FRAGMENT.replace("BEAUTY_CORE",BeautySettings.shader(activity));
            assertFalse(shader.contains("BEAUTY_CORE"));assertTrue(shader.contains("sampleBounds"));assertTrue(shader.contains("flatVideo"));
            // Prevent a mock network preference flush when the activity is destroyed.
            set(activity,"preferencesDirty",false);set(activity,"file",null);
        }
    }
    private static void collect(android.view.View view,java.util.List<android.view.View> result){result.add(view);if(view instanceof android.view.ViewGroup){android.view.ViewGroup group=(android.view.ViewGroup)view;for(int i=0;i<group.getChildCount();i++)collect(group.getChildAt(i),result);}}
}
