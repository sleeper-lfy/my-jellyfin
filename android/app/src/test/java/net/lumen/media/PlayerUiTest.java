package net.lumen.media;

import android.graphics.Insets;
import android.graphics.Rect;
import android.content.Intent;
import android.app.AlertDialog;
import android.view.InputDevice;
import android.view.MotionEvent;
import android.media.session.MediaSession;
import android.os.Looper;
import android.view.KeyEvent;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import org.robolectric.android.controller.ActivityController;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33)
public class PlayerUiTest {
    private Object field(Object object,String name)throws Exception{
        Field field=object.getClass().getDeclaredField(name);field.setAccessible(true);return field.get(object);
    }
    private void call(Object object,String name,Class<?> type,Object arg)throws Exception{
        Method method=object.getClass().getDeclaredMethod(name,type);method.setAccessible(true);method.invoke(object,arg);
    }
    @Test @Config(sdk={26,35}) public void portraitLandscapeAndVrKeepAllButtonsInsideSafeArea()throws Exception{
        // No saved connection: build the real UI without opening a decoder or network session.
        try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=lifecycle.get();
            call(activity,"buildPlayerUi",android.content.SharedPreferences.class,activity.getSharedPreferences("playback",0));
            FrameLayout root=(FrameLayout)field(activity,"root"),overlay=(FrameLayout)field(activity,"overlay");
            LinearLayout top=(LinearLayout)field(activity,"topBar"),bottom=(LinearLayout)field(activity,"bottomBar"),vr=(LinearLayout)field(activity,"vrBar");
            float density=activity.getResources().getDisplayMetrics().density;
            int left=Math.round(28*density),nav=Math.round(24*density),topInset=Math.round(12*density);
            WindowInsets safe=android.os.Build.VERSION.SDK_INT>=30
                ?new WindowInsets.Builder().setInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout(),Insets.of(left,topInset,0,nav)).build()
                :WindowInsets.class.getConstructor(Rect.class).newInstance(new Rect(left,topInset,0,nav));
            root.dispatchApplyWindowInsets(safe);
            for(int[] size:new int[][]{{360,800},{800,360},{640,280}}){
                for(boolean vrMode:new boolean[]{false,true}){
                    vr.setVisibility(vrMode?View.VISIBLE:View.GONE);
                    int width=Math.round(size[0]*density),height=Math.round(size[1]*density);
                    for(int pass=0;pass<3;pass++){
                        root.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(height,View.MeasureSpec.EXACTLY));
                        root.layout(0,0,width,height);
                    }
                    assertEquals("Controls must float above a full-size video",height,root.getChildAt(0).getHeight());
                    assertTrue("layout "+size[0]+"x"+size[1]+" vr="+vrMode+" top="+top.getBottom()+" bottom="+bottom.getTop()+" bottomHeight="+bottom.getHeight(),top.getBottom()<=bottom.getTop());
                    for(View row:new View[]{top,bottom}){
                        Rect rect=new Rect(0,0,row.getWidth(),row.getHeight());root.offsetDescendantRectToMyCoords(row,rect);
                        assertTrue(rect.left>=left);assertTrue(rect.top>=topInset);assertTrue(rect.right<=width);assertTrue(rect.bottom<=height-nav);
                    }
                    ArrayList<View> buttons=new ArrayList<>();bottom.addTouchables(buttons);
                    for(View button:buttons)if(button instanceof Button&&button.getVisibility()==View.VISIBLE){
                        assertTrue(button.getWidth()>0);assertTrue(button.getHeight()>=Math.round(48*density));
                    }
                }
            }
            call(activity,"showControls",boolean.class,false);assertEquals(View.GONE,bottom.getVisibility());
            root.getChildAt(1).performClick();assertEquals(View.VISIBLE,bottom.getVisibility());assertEquals(View.VISIBLE,top.getVisibility());
        }
    }
    @Test public void websiteLinksAlwaysOpenThePrivateViewer()throws Exception{
        try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=lifecycle.get();
            assertFalse(PrivateBrowserActivity.website(android.net.Uri.parse("javascript:alert(1)")));
            assertFalse(PrivateBrowserActivity.website(android.net.Uri.parse("https://user:secret@example.org")));
            PrivateBrowserActivity.open(activity,"https://example.org/detail");
            Intent intent=shadowOf(activity).getNextStartedActivity();
            assertEquals(PrivateBrowserActivity.class.getName(),intent.getComponent().getClassName());
            assertEquals("https://example.org/detail",intent.getDataString());
        }
    }
    @Test public void mediaSessionAndHidUseSavedMappingAndReleaseOnBackground()throws Exception{
        try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=lifecycle.get();
            activity.getSharedPreferences("controller_bindings",0).edit().clear().putString(":90","ZOOM_IN").apply();
            ArrayList<ControllerBindings.Action> actions=new ArrayList<>();
            PlayerController controller=new PlayerController(activity,new PlayerController.Host(){
                public void action(ControllerBindings.Action action){actions.add(action);}
                public void seek(long position){}
            });
            try{
                controller.active(true);
                assertTrue(controller.key(new KeyEvent(KeyEvent.ACTION_DOWN,KeyEvent.KEYCODE_DPAD_RIGHT)));
                assertEquals(ControllerBindings.Action.FORWARD,actions.get(0));
                // Holding a toggle must not repeatedly pause/play.
                controller.key(new KeyEvent(0,0,KeyEvent.ACTION_DOWN,KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE,0));
                controller.key(new KeyEvent(0,0,KeyEvent.ACTION_DOWN,KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE,1));
                assertEquals(2,actions.size());
                MediaSession session=(MediaSession)field(controller,"session");
                MediaSession.Callback transport=(MediaSession.Callback)field(controller,"transport");
                transport.onFastForward();
                assertEquals(ControllerBindings.Action.ZOOM_IN,actions.get(actions.size()-1));
                assertTrue(transport.onMediaButtonEvent(new Intent(Intent.ACTION_MEDIA_BUTTON).putExtra(Intent.EXTRA_KEY_EVENT,
                    new KeyEvent(KeyEvent.ACTION_DOWN,KeyEvent.KEYCODE_MEDIA_REWIND))));
                assertEquals(ControllerBindings.Action.BACKWARD,actions.get(actions.size()-1));
                // Learning a media key saves the action and routes subsequent presses through it.
                call(controller,"capture",ControllerBindings.Action.class,ControllerBindings.Action.RECENTER);
                AlertDialog capture=(AlertDialog)field(controller,"captureDialog");
                capture.dispatchKeyEvent(new KeyEvent(KeyEvent.ACTION_DOWN,KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE));
                assertEquals("RECENTER",activity.getSharedPreferences("controller_bindings",0).getString(":85",""));
                controller.key(new KeyEvent(KeyEvent.ACTION_DOWN,KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE));
                assertEquals(ControllerBindings.Action.RECENTER,actions.get(actions.size()-1));
                MotionEvent.PointerProperties pointer=new MotionEvent.PointerProperties();pointer.id=0;
                MotionEvent.PointerCoords coordinate=new MotionEvent.PointerCoords();coordinate.setAxisValue(MotionEvent.AXIS_X,.9f);
                MotionEvent motion=MotionEvent.obtain(0,0,MotionEvent.ACTION_MOVE,1,new MotionEvent.PointerProperties[]{pointer},
                    new MotionEvent.PointerCoords[]{coordinate},0,0,1,1,0,0,InputDevice.SOURCE_JOYSTICK,0);
                assertTrue(controller.motion(motion));motion.recycle();
                assertEquals(ControllerBindings.Action.FORWARD,actions.get(actions.size()-1));
                int count=actions.size();controller.clearHeld();
                shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofSeconds(1));
                assertEquals(count,actions.size());
                controller.active(false);assertFalse(controller.key(new KeyEvent(KeyEvent.ACTION_DOWN,KeyEvent.KEYCODE_DPAD_RIGHT)));
                assertFalse(session.isActive());
            }finally{controller.release();activity.getSharedPreferences("controller_bindings",0).edit().clear().apply();}
        }
    }
}
