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
    private void waitFile(PlayerActivity activity,long id)throws Exception{long deadline=System.currentTimeMillis()+5000;while(System.currentTimeMillis()<deadline){shadowOf(Looper.getMainLooper()).idle();Object file=read(activity,"file");if(file!=null&&((JSONObject)file).optLong("id")==id)return;Thread.sleep(15);}fail("Adjacent episode did not load");}
}
