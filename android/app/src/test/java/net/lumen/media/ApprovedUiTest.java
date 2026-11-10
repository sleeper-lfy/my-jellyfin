package net.lumen.media;

import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.view.MotionEvent;
import android.widget.*;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.Shadows;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.GraphicsMode;
import org.robolectric.android.controller.ActivityController;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import okhttp3.mockwebserver.*;
import static org.junit.Assert.*;

@RunWith(org.robolectric.RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w393dp-h852dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
public class ApprovedUiTest {
    private Object get(Object target,String name)throws Exception{Field f=target.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(target);}
    private void set(Object target,String name,Object value)throws Exception{Field f=target.getClass().getDeclaredField(name);f.setAccessible(true);f.set(target,value);}
    private void call(Object target,String name)throws Exception{Method m=target.getClass().getDeclaredMethod(name);m.setAccessible(true);m.invoke(target);}
    private void layout(View root,int width,int height){for(int i=0;i<3;i++){root.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(height,View.MeasureSpec.EXACTLY));root.layout(0,0,width,height);}}
    private void snapshot(View root,String name)throws Exception{String dir=System.getenv("LUMEN_UI_SCREENSHOTS");if(dir==null)return;File output=new File(dir,name);output.getParentFile().mkdirs();Bitmap image=Bitmap.createBitmap(root.getWidth(),root.getHeight(),Bitmap.Config.ARGB_8888);root.draw(new Canvas(image));try(FileOutputStream file=new FileOutputStream(output)){image.compress(Bitmap.CompressFormat.PNG,100,file);}image.recycle();}
    @Test public void realHomeKeepsExactResumeFileAndIndependentTimesAndBottomNavigation()throws Exception{
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){return new MockResponse().setBody(request.getPath().startsWith("/api/continue")?"{\"items\":[{\"id\":7,\"title\":\"海岸纪行：沿着海风，走向群岛深处\",\"resume\":{\"file_id\":70,\"name\":\"S02E03 · Coast.Journal.2160p.HEVC.mkv\",\"position\":2308,\"duration\":3600,\"label\":\"S02E03 · 海岛来信\"}}]}":"{\"items\":[],\"total\":0}");}});server.start();
            MainActivity activity=lifecycle.get();set(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));call(activity,"showLibrary");View root=(View)get(activity,"root");
            long until=System.currentTimeMillis()+5000;while(root.findViewWithTag("continueTime:70")==null&&System.currentTimeMillis()<until){Thread.sleep(15);Shadows.shadowOf(Looper.getMainLooper()).idle();}
            TextView time=root.findViewWithTag("continueTime:70"),identity=root.findViewWithTag("continueIdentity:70");assertNotNull(time);assertNotNull(identity);assertTrue(time.getText().toString().contains("0:38:28"));assertTrue(time.getText().toString().contains("0:21:32"));assertTrue(identity.getText().toString().contains("S02E03"));
            for(int width:new int[]{320,360,393,440}){layout(root,width,852);LinearLayout nav=root.findViewWithTag("primaryNavigation");assertEquals(LinearLayout.HORIZONTAL,nav.getOrientation());for(int i=0;i<4;i++){View tab=nav.getChildAt(i);assertEquals(nav.getChildAt(0).getTop(),tab.getTop());assertTrue(tab.getRight()<=nav.getWidth());assertTrue(tab.getWidth()>=48);}assertTrue(time.getLayout().getHeight()<=time.getHeight());}
            layout(root,393,852);snapshot(root,"approved-android-home.png");root.findViewWithTag("nav:mine").performClick();root=(View)get(activity,"root");layout(root,393,852);snapshot(root,"approved-android-mine.png");
        }
    }
    @Test public void videoTapTogglesOnlyControlsAndCancelRestoresTheOriginalRate()throws Exception{
        try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=lifecycle.get();Method build=PlayerActivity.class.getDeclaredMethod("buildPlayerUi",android.content.SharedPreferences.class);build.setAccessible(true);build.invoke(activity,activity.getSharedPreferences("playback",0));View root=(View)get(activity,"root");layout(root,393,852);View touch=root.findViewWithTag("videoGestures");
            touch.performClick();assertEquals(false,get(activity,"controlsVisible"));assertEquals(View.GONE,((View)get(activity,"personalRow")).getVisibility());
            Method render=PlayerActivity.class.getDeclaredMethod("renderPlaybackState",boolean.class);render.setAccessible(true);render.invoke(activity,false);assertEquals(false,get(activity,"controlsVisible"));assertEquals(View.GONE,((View)get(activity,"transportControls")).getVisibility());render.invoke(activity,true);assertEquals(false,get(activity,"controlsVisible"));
            touch.performClick();assertEquals(true,get(activity,"controlsVisible"));assertNull(get(activity,"player"));
            HoldSpeed hold=(HoldSpeed)get(activity,"holdSpeed");HoldSpeedTest.Fake decoder=new HoldSpeedTest.Fake(1.5f);assertTrue(hold.begin(decoder));set(activity,"holdActivated",true);
            Method gesture=PlayerActivity.class.getDeclaredMethod("playbackTouch",View.class,MotionEvent.class);gesture.setAccessible(true);MotionEvent cancel=MotionEvent.obtain(0,1,MotionEvent.ACTION_CANCEL,120,200,0);gesture.invoke(activity,touch,cancel);cancel.recycle();assertEquals(1.5f,decoder.value,0);assertFalse(hold.active());
            set(activity,"work",new org.json.JSONObject().put("id",7).put("title","海岸纪行：沿着海风，走向群岛深处").put("favorite",1));set(activity,"file",new org.json.JSONObject().put("id",70).put("name","S02E03 · 海岛来信"));call(activity,"refreshPersonal");layout(root,393,852);snapshot(root,"approved-android-player-portrait.png");layout(root,852,393);snapshot(root,"approved-android-player-landscape.png");call(activity,"playbackSettings");android.app.AlertDialog dialog=org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog();View panel=dialog.getWindow().getDecorView();layout(panel,340,393);snapshot(panel,"approved-android-player-settings.png");dialog.dismiss();
        }
    }
    @Test public void posterGridRemeasuresWithoutReloadingTheCards(){
        android.content.Context context=org.robolectric.RuntimeEnvironment.getApplication();PosterGrid grid=new PosterGrid(context);
        for(int i=0;i<5;i++){LinearLayout card=new LinearLayout(context);card.setOrientation(LinearLayout.VERTICAL);card.addView(new FrameLayout(context),new LinearLayout.LayoutParams(-1,100));TextView title=new TextView(context);title.setText("A long title "+i);card.addView(title);grid.addView(card);}
        for(int width:new int[]{680,320,440}){layout(grid,width,1500);for(int i=0;i<grid.getChildCount();i++){ViewGroup card=(ViewGroup)grid.getChildAt(i);View cover=card.getChildAt(0);assertEquals(Math.round(cover.getWidth()*1.5f),cover.getHeight());assertTrue(card.getRight()<=width);}assertEquals(grid.getChildAt(0).getWidth(),grid.getChildAt(1).getWidth());}
    }
}
