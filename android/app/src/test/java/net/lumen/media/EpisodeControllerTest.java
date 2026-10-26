package net.lumen.media;
import android.app.Activity;
import android.media.session.MediaSession;
import android.os.Looper;
import org.json.JSONArray;
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
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

@RunWith(RobolectricTestRunner.class) @Config(sdk=33)
public class EpisodeControllerTest {
    private Object read(Object object,String name)throws Exception{Field field=object.getClass().getDeclaredField(name);field.setAccessible(true);return field.get(object);}
    private void write(Object object,String name,Object value)throws Exception{Field field=object.getClass().getDeclaredField(name);field.setAccessible(true);field.set(object,value);}
    private Object call(Object object,String name,Class<?>[] types,Object... values)throws Exception{Method method=object.getClass().getDeclaredMethod(name,types);method.setAccessible(true);return method.invoke(object,values);}
    @Test public void bluetoothTransportSkipsEpisodesAndRetainsUserMappings()throws Exception{
        try(ActivityController<Activity> lifecycle=Robolectric.buildActivity(Activity.class).create()){
            Activity activity=lifecycle.get();ArrayList<ControllerBindings.Action> actions=new ArrayList<>();PlayerController.Host host=new PlayerController.Host(){public void action(ControllerBindings.Action action){actions.add(action);}public void seek(long position){}};
            PlayerController controller=new PlayerController(activity,host);controller.active(true);MediaSession.Callback transport=(MediaSession.Callback)read(controller,"transport");transport.onSkipToNext();transport.onSkipToPrevious();assertEquals(ControllerBindings.Action.NEXT_EPISODE,actions.get(0));assertEquals(ControllerBindings.Action.PREVIOUS_EPISODE,actions.get(1));controller.release();
            activity.getSharedPreferences("controller_bindings",0).edit().putString(":87","FORWARD").apply();controller=new PlayerController(activity,host);controller.active(true);((MediaSession.Callback)read(controller,"transport")).onSkipToNext();assertEquals(ControllerBindings.Action.FORWARD,actions.get(2));controller.release();
        }
    }
    @Test public void episodeActionsLoadAdjacentFilesAndStopAtSeriesBoundaries()throws Exception{
        JSONArray files=new JSONArray();for(int i=1;i<=3;i++)files.put(new JSONObject().put("id",i).put("duration",30).put("position",0));
        JSONObject work=new JSONObject().put("id",9).put("kind","series").put("title","Series").put("files",files);
        try(MockWebServer server=new MockWebServer();ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){return new MockResponse().setBody(request.getPath().startsWith("/api/works/")?work.toString():request.getPath().endsWith("subtitles")?"{\"items\":[]}":"{}");}});server.start();
            PlayerActivity activity=lifecycle.get();call(activity,"buildPlayerUi",new Class<?>[]{android.content.SharedPreferences.class},activity.getSharedPreferences("playback",0));write(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));write(activity,"work",work);write(activity,"file",files.getJSONObject(1));
            call(activity,"performAction",new Class<?>[]{ControllerBindings.Action.class},ControllerBindings.Action.NEXT_EPISODE);assertEquals(3L,read(activity,"desiredFile"));waitFile(activity,3);
            call(activity,"performAction",new Class<?>[]{ControllerBindings.Action.class},ControllerBindings.Action.NEXT_EPISODE);assertEquals(3L,read(activity,"desiredFile"));
            call(activity,"performAction",new Class<?>[]{ControllerBindings.Action.class},ControllerBindings.Action.PREVIOUS_EPISODE);waitFile(activity,2);assertEquals(2L,read(activity,"desiredFile"));
            call(activity,"performAction",new Class<?>[]{ControllerBindings.Action.class},ControllerBindings.Action.PREVIOUS_EPISODE);waitFile(activity,1);
            call(activity,"performAction",new Class<?>[]{ControllerBindings.Action.class},ControllerBindings.Action.PREVIOUS_EPISODE);assertEquals(1L,read(activity,"desiredFile"));
        }
    }
    private JSONObject vrWork(long id,long... ids)throws Exception{
        JSONArray files=new JSONArray();for(long file:ids)files.put(new JSONObject().put("id",file).put("duration",30).put("position",0));
        return new JSONObject().put("id",id).put("kind","vr").put("title","VR "+id).put("files",files).put("resume_file_id",ids[0]);
    }
    private void build(PlayerActivity activity,MockWebServer server,JSONObject work)throws Exception{
        call(activity,"buildPlayerUi",new Class<?>[]{android.content.SharedPreferences.class},activity.getSharedPreferences("playback",0));
        write(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));write(activity,"work",work);write(activity,"file",work.getJSONArray("files").getJSONObject(0));write(activity,"vrEnabled",true);
    }
    @Test public void visibleButtonsAndBluetoothSwitchVrFilesAndThenAdjacentVrWorks()throws Exception{
        JSONObject first=vrWork(30,301,302),second=vrWork(20,201),third=vrWork(10,101);
        JSONArray catalog=new JSONArray().put(new JSONObject().put("id",30)).put(new JSONObject().put("id",20)).put(new JSONObject().put("id",10));
        try(MockWebServer server=new MockWebServer();ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){String path=request.getPath();
                assertEquals("Bearer abcdefghijklmnopqrstuvwxyz123456",request.getHeader("Authorization"));
                if(path.startsWith("/api/works?")){assertTrue(path.contains("kind=vr"));int offset=Integer.parseInt(request.getRequestUrl().queryParameter("offset")),limit=Integer.parseInt(request.getRequestUrl().queryParameter("limit"));JSONArray items=new JSONArray();for(int i=offset;i<Math.min(catalog.length(),offset+limit);i++)items.put(catalog.optJSONObject(i));return new MockResponse().setBody("{\"total\":3,\"items\":"+items+"}");}
                return new MockResponse().setBody(path.equals("/api/works/30")?first.toString():path.equals("/api/works/20")?second.toString():path.equals("/api/works/10")?third.toString():path.endsWith("subtitles")?"{\"items\":[]}":"{}");}});server.start();
            PlayerActivity activity=lifecycle.get();build(activity,server,first);
            android.widget.Button next=(android.widget.Button)read(activity,"nextVideo"),previous=(android.widget.Button)read(activity,"previousVideo");
            assertEquals("下个视频",next.getContentDescription());assertEquals("上个视频",previous.getContentDescription());assertEquals(android.view.View.VISIBLE,next.getVisibility());
            next.performClick();assertFalse(next.isEnabled());waitFile(activity,302);assertTrue(next.isEnabled());
            next.performClick();waitFile(activity,201);assertTrue((boolean)read(activity,"vrEnabled"));
            call(activity,"performAction",new Class<?>[]{ControllerBindings.Action.class},ControllerBindings.Action.NEXT_EPISODE);waitFile(activity,101);assertTrue((boolean)read(activity,"vrEnabled"));
            previous.performClick();waitFile(activity,201);previous.performClick();waitFile(activity,302);
        }
    }
    @Test public void manuallyEnabledVrRemainsEnabledWhenChangingEpisodesInSameSeries()throws Exception{
        JSONObject work=vrWork(30,301,302).put("kind","series");
        try(MockWebServer server=new MockWebServer();ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){return new MockResponse().setBody(request.getPath().equals("/api/works/30")?work.toString():request.getPath().endsWith("subtitles")?"{\"items\":[]}":"{}");}});server.start();
            PlayerActivity activity=lifecycle.get();build(activity,server,work);
            call(activity,"performAction",new Class<?>[]{ControllerBindings.Action.class},ControllerBindings.Action.NEXT_EPISODE);waitFile(activity,302);assertTrue((boolean)read(activity,"vrEnabled"));
        }
    }
    @Test public void randomVrQueueSupportsPreviousAndNextAndDoesNotWrap()throws Exception{
        JSONObject first=vrWork(30,301),second=vrWork(20,201);
        try(MockWebServer server=new MockWebServer();ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){String path=request.getPath();return new MockResponse().setBody(path.equals("/api/works/30")?first.toString():path.equals("/api/works/20")?second.toString():path.endsWith("subtitles")?"{\"items\":[]}":"{}");}});server.start();
            PlayerActivity activity=lifecycle.get();build(activity,server,first);write(activity,"queueMode",true);
            activity.getSharedPreferences("queue",0).edit().putString("ids","[30,20]").putInt("index",0).apply();
            call(activity,"performAction",new Class<?>[]{ControllerBindings.Action.class},ControllerBindings.Action.NEXT_EPISODE);waitFile(activity,201);
            call(activity,"performAction",new Class<?>[]{ControllerBindings.Action.class},ControllerBindings.Action.NEXT_EPISODE);assertEquals(201L,((JSONObject)read(activity,"file")).getLong("id"));
            call(activity,"performAction",new Class<?>[]{ControllerBindings.Action.class},ControllerBindings.Action.PREVIOUS_EPISODE);waitFile(activity,301);
            call(activity,"performAction",new Class<?>[]{ControllerBindings.Action.class},ControllerBindings.Action.PREVIOUS_EPISODE);assertEquals(301L,((JSONObject)read(activity,"file")).getLong("id"));
        }
    }
    @Test public void fansControlsAndAutomaticPlaybackFinishAuthorFilesBeforeQueueAndRespectAutoNext()throws Exception{
        JSONObject first=vrWork(30,301,302).put("kind","fans"),second=vrWork(20,201,202).put("kind","fans");
        try(MockWebServer server=new MockWebServer();ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){String path=request.getPath();return new MockResponse().setBody(path.equals("/api/works/30")?first.toString():path.equals("/api/works/20")?second.toString():path.endsWith("subtitles")?"{\"items\":[]}":"{}");}});server.start();
            PlayerActivity activity=lifecycle.get();build(activity,server,first);write(activity,"vrEnabled",false);write(activity,"queueMode",true);
            activity.getSharedPreferences("queue",0).edit().putString("ids","[30,20]").putInt("index",0).apply();
            ((android.widget.Button)read(activity,"nextVideo")).performClick();waitFile(activity,302);assertEquals(30,((JSONObject)read(activity,"work")).optLong("id"));
            call(activity,"performAction",new Class<?>[]{ControllerBindings.Action.class},ControllerBindings.Action.PREVIOUS_EPISODE);waitFile(activity,301);
            call(activity,"onPlaybackEnded",new Class<?>[]{});waitFile(activity,302);assertEquals(0,activity.getSharedPreferences("queue",0).getInt("index",-1));
            call(activity,"onPlaybackEnded",new Class<?>[]{});waitFile(activity,201);assertEquals(1,activity.getSharedPreferences("queue",0).getInt("index",-1));assertFalse((boolean)read(activity,"vrEnabled"));
            ((android.widget.Button)read(activity,"previousVideo")).performClick();waitFile(activity,302);assertEquals(30,((JSONObject)read(activity,"work")).optLong("id"));
            activity.getSharedPreferences("player",0).edit().putBoolean("auto_next",false).apply();
            call(activity,"onPlaybackEnded",new Class<?>[]{});assertEquals(302,((JSONObject)read(activity,"file")).optLong("id"));assertEquals(0,activity.getSharedPreferences("queue",0).getInt("index",-1));
            call(activity,"performAction",new Class<?>[]{ControllerBindings.Action.class},ControllerBindings.Action.NEXT_EPISODE);waitFile(activity,201);
        }
    }
    @Test public void lookupFailureKeepsCurrentVideoAndAllowsRetry()throws Exception{
        JSONObject current=vrWork(20,201);
        try(MockWebServer server=new MockWebServer();ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            server.enqueue(new MockResponse().setResponseCode(500));server.enqueue(new MockResponse().setBody("{\"total\":1,\"items\":[{\"id\":20}]}"));server.start();
            PlayerActivity activity=lifecycle.get();build(activity,server,current);android.widget.Button next=(android.widget.Button)read(activity,"nextVideo");next.performClick();
            long deadline=System.currentTimeMillis()+5000;while(!next.isEnabled()&&System.currentTimeMillis()<deadline){Thread.sleep(15);shadowOf(Looper.getMainLooper()).idle();}
            assertTrue(next.isEnabled());assertEquals(201L,((JSONObject)read(activity,"file")).getLong("id"));next.performClick();
            deadline=System.currentTimeMillis()+5000;while(!next.isEnabled()&&System.currentTimeMillis()<deadline){Thread.sleep(15);shadowOf(Looper.getMainLooper()).idle();}
            assertTrue(next.isEnabled());assertEquals(201L,((JSONObject)read(activity,"file")).getLong("id"));
        }
    }
    private void waitFile(PlayerActivity activity,long id)throws Exception{long deadline=System.currentTimeMillis()+5000;while(System.currentTimeMillis()<deadline){shadowOf(Looper.getMainLooper()).idle();Object file=read(activity,"file");if(file!=null&&((JSONObject)file).optLong("id")==id)return;Thread.sleep(15);}fail("Adjacent episode did not load");}
}
