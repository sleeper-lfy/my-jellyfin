package net.lumen.media;

import android.app.AlertDialog;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.widget.EditText;
import android.widget.SeekBar;
import android.widget.TextView;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import org.robolectric.android.controller.ActivityController;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.RecordedRequest;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.BooleanSupplier;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

@RunWith(RobolectricTestRunner.class) @Config(sdk=33)
public class MediaToolsTest {
    private Object read(Object object,String name)throws Exception{Field field=object.getClass().getDeclaredField(name);field.setAccessible(true);return field.get(object);}
    private void field(Object object,String name,Object value)throws Exception{Field field=object.getClass().getDeclaredField(name);field.setAccessible(true);field.set(object,value);}
    private Object call(Object object,String name,Class<?>[] types,Object... args)throws Exception{Method method=object.getClass().getDeclaredMethod(name,types);method.setAccessible(true);return method.invoke(object,args);}
    private void call(Object object,String name)throws Exception{call(object,name,new Class<?>[]{});}
    private void waitMain(BooleanSupplier ready)throws Exception{long deadline=System.currentTimeMillis()+6000;while(!ready.getAsBoolean()&&System.currentTimeMillis()<deadline){Thread.sleep(15);shadowOf(Looper.getMainLooper()).idle();}assertTrue(ready.getAsBoolean());}
    private ArrayList<EditText> inputs(View view){ArrayList<EditText> values=new ArrayList<>();if(view instanceof EditText)values.add((EditText)view);if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++)values.addAll(inputs(((ViewGroup)view).getChildAt(i)));return values;}
    private void build(PlayerActivity activity,MockWebServer server)throws Exception{
        call(activity,"buildPlayerUi",new Class<?>[]{android.content.SharedPreferences.class},activity.getSharedPreferences("playback",0));
        field(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));
        field(activity,"file",new JSONObject().put("id",7).put("duration",30));
    }
    @Test public void vrProjectionZoomAndViewOffsetsAreSavedAndRestoredPerVideo()throws Exception{
        AtomicReference<String> body=new AtomicReference<>();
        try(MockWebServer server=new MockWebServer();ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){assertEquals("Bearer abcdefghijklmnopqrstuvwxyz123456",request.getHeader("Authorization"));assertEquals("/api/files/7/preferences",request.getPath());body.set(request.getBody().readUtf8());return new MockResponse().setBody("{}");}});server.start();
            PlayerActivity activity=lifecycle.get();build(activity,server);
            JSONObject first=new JSONObject().put("vr",new JSONObject().put("fish",true).put("fov",65).put("yaw",20).put("pitch",10).put("swap",true).put("tracking_sensitivity",.5).put("tracking_smoothing",60).put("tracking_invert_pitch",true));field(activity,"filePreferences",first);call(activity,"applyFilePreferences");
            VrVideoView view=(VrVideoView)read(activity,"vrVideo");assertEquals(65,view.getFov(),.01);assertEquals(20,view.getViewYaw(),.01);
            view.setFov(73);call(activity,"saveFov",new Class<?>[]{float.class},73f);call(activity,"flushPreferences");waitMain(()->body.get()!=null);
            JSONObject saved=new JSONObject(body.get());assertEquals(73,saved.getJSONObject("vr").getInt("fov"));assertTrue(saved.getJSONObject("vr").getBoolean("fish"));assertEquals(20,saved.getJSONObject("vr").getInt("yaw"));
            assertEquals(.5,saved.getJSONObject("vr").getDouble("tracking_sensitivity"),.001);assertEquals(60,saved.getJSONObject("vr").getInt("tracking_smoothing"));assertTrue(saved.getJSONObject("vr").getBoolean("tracking_invert_pitch"));
            field(activity,"file",new JSONObject().put("id",8));field(activity,"filePreferences",new JSONObject().put("vr",new JSONObject().put("fish",false).put("fov",100)));call(activity,"applyFilePreferences");assertEquals(100,view.getFov(),.01);assertEquals(0,view.getViewYaw(),.01);
            field(activity,"file",new JSONObject().put("id",7));field(activity,"filePreferences",saved);call(activity,"applyFilePreferences");assertEquals(73,view.getFov(),.01);assertEquals(20,view.getViewYaw(),.01);assertTrue((boolean)read(activity,"vrFish"));
        }
    }
    @Test public void subtitleInputsRejectInvalidValuesAndSynchronizeValidFileSettings()throws Exception{
        AtomicReference<String> body=new AtomicReference<>();
        try(MockWebServer server=new MockWebServer();ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){body.set(request.getBody().readUtf8());return new MockResponse().setBody("{}");}});server.start();
            PlayerActivity activity=lifecycle.get();build(activity,server);call(activity,"subtitleSettings");AlertDialog dialog=org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog();
            ArrayList<EditText> inputs=inputs(dialog.getWindow().getDecorView());assertEquals(3,inputs.size());inputs.get(1).setText("0");dialog.getButton(AlertDialog.BUTTON_POSITIVE).performClick();assertTrue(dialog.isShowing());assertNull(body.get());
            inputs.get(0).setText("-1.5");inputs.get(1).setText("28");inputs.get(2).setText("85");dialog.getButton(AlertDialog.BUTTON_POSITIVE).performClick();assertFalse(dialog.isShowing());call(activity,"flushPreferences");waitMain(()->body.get()!=null);
            JSONObject saved=new JSONObject(body.get());assertEquals(-1.5,saved.getDouble("subtitle_delay"),.001);assertEquals(28,saved.getInt("subtitle_size"));assertEquals(85,saved.getInt("subtitle_position"));
        }
    }
    @Test public void remoteUsesAuthenticatedCommandsAndDisplaysPcStateWithoutStartingDecoder()throws Exception{
        AtomicReference<String> body=new AtomicReference<>();
        try(MockWebServer server=new MockWebServer();ActivityController<RemoteActivity> lifecycle=Robolectric.buildActivity(RemoteActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){assertEquals("Bearer abcdefghijklmnopqrstuvwxyz123456",request.getHeader("Authorization"));assertEquals("/api/remote",request.getPath());if(request.getMethod().equals("POST")){body.set(request.getBody().readUtf8());return new MockResponse().setBody("{\"command_id\":\"request1\"}");}return new MockResponse().setBody("{\"active\":true,\"title\":\"PC movie\",\"position\":8,\"duration\":20,\"playing\":false,\"volume\":23,\"last_command\":{\"id\":\"request1\",\"ok\":true}}");}});server.start();
            RemoteActivity activity=lifecycle.get();call(activity,"buildUi");field(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));field(activity,"active",true);call(activity,"poll");
            TextView title=(TextView)read(activity,"title");waitMain(()->title.getText().toString().equals("PC movie"));assertEquals(4000,((SeekBar)read(activity,"seek")).getProgress());assertEquals(23,((SeekBar)read(activity,"volume")).getProgress());
            call(activity,"send",new Class<?>[]{String.class,Object.class},"jump",-10);waitMain(()->body.get()!=null);assertEquals("jump",new JSONObject(body.get()).getString("action"));assertEquals(-10,new JSONObject(body.get()).getInt("value"));
        }
    }
}
