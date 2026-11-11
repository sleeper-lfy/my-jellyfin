package net.lumen.media;

import android.os.Looper;
import android.view.InputDevice;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.TextView;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.Shadows;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.Implementation;
import org.robolectric.annotation.Implements;
import org.robolectric.annotation.LooperMode;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.shadow.api.Shadow;
import org.videolan.libvlc.MediaPlayer;
import org.videolan.libvlc.interfaces.ILibVLC;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.time.Duration;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w393dp-h852dp-mdpi",shadows=HoldGestureUiTest.DecoderShadow.class,instrumentedPackages="org.videolan.libvlc")
@LooperMode(LooperMode.Mode.PAUSED)
public class HoldGestureUiTest {
    @Implements(value=MediaPlayer.class,isInAndroidSdk=false)
    public static class DecoderShadow {
        float speed=1.25f;boolean playing=true,rejectRestore;
        @Implementation protected void __constructor__(ILibVLC ignored){}
        @Implementation protected boolean isPlaying(){return playing;}
        @Implementation protected float getRate(){return speed;}
        @Implementation protected void setRate(float next){if(!rejectRestore||next!=1.25f)speed=next;}
        @Implementation protected void pause(){playing=false;}
    }
    private Object get(Object target,String name)throws Exception{Field field=target.getClass().getDeclaredField(name);field.setAccessible(true);return field.get(target);}
    private void set(Object target,String name,Object value)throws Exception{Field field=target.getClass().getDeclaredField(name);field.setAccessible(true);field.set(target,value);}
    private FrameLayout build(PlayerActivity activity)throws Exception{
        Method build=PlayerActivity.class.getDeclaredMethod("buildPlayerUi",android.content.SharedPreferences.class);build.setAccessible(true);build.invoke(activity,activity.getSharedPreferences("playback",0));FrameLayout root=(FrameLayout)get(activity,"root");
        for(int pass=0;pass<3;pass++){root.measure(View.MeasureSpec.makeMeasureSpec(393,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(852,View.MeasureSpec.EXACTLY));root.layout(0,0,393,852);}return root;
    }
    private long gesture(View root,int action,long down,float x,float y){long now=android.os.SystemClock.uptimeMillis();MotionEvent event=MotionEvent.obtain(down,now,action,x,y,0);root.dispatchTouchEvent(event);event.recycle();return now;}
    private void noSpeedPopup(View view){
        if(view.getVisibility()!=View.VISIBLE)return;
        if(view instanceof TextView){String text=((TextView)view).getText().toString();assertFalse(text.contains("倍速播放中"));assertFalse(text.contains("松手恢复"));assertFalse("No visible speed text during an active hold",text.contains("×"));}
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++)noSpeedPopup(((ViewGroup)view).getChildAt(i));
    }
    @Test public void rootLongPressWaitsFourHundredMillisThenSpeedsUpWithoutAnyPopup()throws Exception{
        try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=lifecycle.get();FrameLayout root=build(activity);activity.getSharedPreferences("player",0).edit().putFloat("speed",1.25f).apply();MediaPlayer decoder=new MediaPlayer((ILibVLC)null);DecoderShadow engine=Shadow.extract(decoder);set(activity,"player",decoder);
            try{
                long down=gesture(root,MotionEvent.ACTION_DOWN,android.os.SystemClock.uptimeMillis(),80,240);Shadows.shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(399));assertEquals(1.25f,engine.speed,0);
                Shadows.shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(1));assertEquals(2f,engine.speed,0);assertTrue(((HoldSpeed)get(activity,"holdSpeed")).active());assertEquals(false,get(activity,"controlsVisible"));noSpeedPopup((View)get(activity,"overlay"));assertEquals(1.25f,activity.getSharedPreferences("player",0).getFloat("speed",0),0);
                gesture(root,MotionEvent.ACTION_UP,down,80,240);assertEquals(1.25f,engine.speed,0);assertFalse(((HoldSpeed)get(activity,"holdSpeed")).active());assertEquals(true,get(activity,"controlsVisible"));
            }finally{set(activity,"player",null);}
        }
    }
    @Test public void cancellingMovingLosingFocusPausingAndMultitouchRestoreRateAndPriorVisibility()throws Exception{
        for(String ending:new String[]{"cancel","move","focus","pause","multitouch"})try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=lifecycle.get();FrameLayout root=build(activity);boolean visible=!ending.equals("focus");if(!visible)root.findViewWithTag("videoGestures").performClick();MediaPlayer decoder=new MediaPlayer((ILibVLC)null);DecoderShadow engine=Shadow.extract(decoder);set(activity,"player",decoder);
            try{
                long down=gesture(root,MotionEvent.ACTION_DOWN,android.os.SystemClock.uptimeMillis(),80,240);Shadows.shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(400));assertEquals(ending,2f,engine.speed,0);noSpeedPopup((View)get(activity,"overlay"));
                switch(ending){
                    case "cancel":gesture(root,MotionEvent.ACTION_CANCEL,down,80,240);break;
                    case "move":gesture(root,MotionEvent.ACTION_MOVE,down,160,240);break;
                    case "focus":activity.onWindowFocusChanged(false);break;
                    case "pause":activity.onPause();break;
                    default:
                        MotionEvent.PointerProperties first=new MotionEvent.PointerProperties(),second=new MotionEvent.PointerProperties();first.id=0;second.id=1;first.toolType=second.toolType=MotionEvent.TOOL_TYPE_FINGER;
                        MotionEvent.PointerCoords a=new MotionEvent.PointerCoords(),b=new MotionEvent.PointerCoords();a.x=80;a.y=240;b.x=120;b.y=250;
                        MotionEvent multiple=MotionEvent.obtain(down,android.os.SystemClock.uptimeMillis(),MotionEvent.ACTION_POINTER_DOWN|(1<<MotionEvent.ACTION_POINTER_INDEX_SHIFT),2,new MotionEvent.PointerProperties[]{first,second},new MotionEvent.PointerCoords[]{a,b},0,0,1,1,0,0,InputDevice.SOURCE_TOUCHSCREEN,0);root.dispatchTouchEvent(multiple);multiple.recycle();
                }
                assertEquals(ending,1.25f,engine.speed,0);assertFalse(((HoldSpeed)get(activity,"holdSpeed")).active());assertEquals(ending,visible,get(activity,"controlsVisible"));
            }finally{set(activity,"player",null);}
        }
    }
    @Test public void failureToRestoreStillShowsTheActionablePlaybackWarning()throws Exception{
        try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=lifecycle.get();FrameLayout root=build(activity);MediaPlayer decoder=new MediaPlayer((ILibVLC)null);DecoderShadow engine=Shadow.extract(decoder);set(activity,"player",decoder);
            try{long down=gesture(root,MotionEvent.ACTION_DOWN,android.os.SystemClock.uptimeMillis(),80,240);Shadows.shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(400));assertEquals(2f,engine.speed,0);engine.rejectRestore=true;gesture(root,MotionEvent.ACTION_UP,down,80,240);TextView status=(TextView)get(activity,"status");assertEquals(View.VISIBLE,status.getVisibility());assertTrue(status.getText().toString().contains("恢复原速失败"));assertFalse(((HoldSpeed)get(activity,"holdSpeed")).active());}
            finally{set(activity,"player",null);}
        }
    }
}
