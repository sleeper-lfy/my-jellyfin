package net.lumen.media;

import android.app.AlertDialog;
import android.os.Looper;
import android.widget.Button;
import okhttp3.mockwebserver.*;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

@RunWith(RobolectricTestRunner.class) @Config(sdk=33)
public class PlayerPersonalTest {
    private Object get(Object object,String name)throws Exception{Field f=object.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(object);}
    private void put(Object object,String name,Object value)throws Exception{Field f=object.getClass().getDeclaredField(name);f.setAccessible(true);f.set(object,value);}
    private void call(Object object,String name)throws Exception{Method m=object.getClass().getDeclaredMethod(name);m.setAccessible(true);m.invoke(object);}
    private void waitFor(BooleanSupplier ready)throws Exception{long end=System.currentTimeMillis()+6000;while(!ready.getAsBoolean()&&System.currentTimeMillis()<end){Thread.sleep(15);shadowOf(Looper.getMainLooper()).idle();}assertTrue(ready.getAsBoolean());}
    private JSONObject build(PlayerActivity activity,MockWebServer server)throws Exception{
        Method method=PlayerActivity.class.getDeclaredMethod("buildPlayerUi",android.content.SharedPreferences.class);method.setAccessible(true);method.invoke(activity,activity.getSharedPreferences("playback",0));
        JSONObject work=new JSONObject("{\"id\":7,\"title\":\"Playing work\",\"kind\":\"series\",\"favorite\":0,\"liked\":0,\"disliked\":0,\"rating\":null}");
        put(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));put(activity,"work",work);put(activity,"file",new JSONObject().put("id",70));put(activity,"session","keep-session");put(activity,"resumeMs",45000L);call(activity,"refreshPersonal");return work;
    }
    @Test public void allPersonalActionsPersistWithoutChangingVideoOrSession()throws Exception{
        JSONObject canonical=new JSONObject("{\"favorite\":0,\"liked\":0,\"disliked\":0,\"rating\":null,\"watchlist\":0}");
        try(MockWebServer server=new MockWebServer();ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){try{
                assertEquals("/api/works/7/personal",request.getPath());assertEquals("Bearer abcdefghijklmnopqrstuvwxyz123456",request.getHeader("Authorization"));JSONObject fields=new JSONObject(request.getBody().readUtf8());java.util.Iterator<String> keys=fields.keys();while(keys.hasNext()){String key=keys.next();Object value=fields.get(key);canonical.put(key,value instanceof Boolean?((Boolean)value?1:0):value);}if(fields.optBoolean("liked"))canonical.put("disliked",0);if(fields.optBoolean("disliked"))canonical.put("liked",0);
                return new MockResponse().setBody(new JSONObject().put("ok",true).put("personal",canonical).toString());
            }catch(Exception e){return new MockResponse().setResponseCode(500);}}});server.start();PlayerActivity activity=lifecycle.get();JSONObject work=build(activity,server);Object file=get(activity,"file");
            ((Button)get(activity,"personalFavorite")).performClick();waitFor(()->work.optInt("favorite")==1);
            ((Button)get(activity,"personalLiked")).performClick();waitFor(()->work.optInt("liked")==1);
            ((Button)get(activity,"personalDisliked")).performClick();waitFor(()->work.optInt("disliked")==1);assertEquals(0,work.optInt("liked"));assertEquals(1,work.optInt("favorite"));
            ((Button)get(activity,"personalRating")).performClick();AlertDialog score=org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog();score.getListView().performItemClick(null,9,9);waitFor(()->work.optInt("rating")==9);
            ((Button)get(activity,"personalRating")).performClick();score=org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog();score.getListView().performItemClick(null,0,0);waitFor(()->work.isNull("rating"));
            assertSame(file,get(activity,"file"));assertEquals("keep-session",get(activity,"session"));assertEquals(45000L,get(activity,"resumeMs"));assertNull(get(activity,"player"));
        }
    }
    @Test public void failedSaveKeepsOldStateAndAllowsRetry()throws Exception{
        try(MockWebServer server=new MockWebServer();ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            server.enqueue(new MockResponse().setResponseCode(500));server.start();PlayerActivity activity=lifecycle.get();JSONObject work=build(activity,server);Button favorite=(Button)get(activity,"personalFavorite");favorite.performClick();assertFalse(favorite.isEnabled());waitFor(favorite::isEnabled);assertEquals(0,work.optInt("favorite"));assertTrue(org.robolectric.shadows.ShadowToast.getTextOfLatestToast().contains("未保存"));assertEquals("keep-session",get(activity,"session"));
        }
    }
    @Test public void delayedSaveTargetsOriginalWorkAfterVideoChanges()throws Exception{
        CountDownLatch entered=new CountDownLatch(1),release=new CountDownLatch(1);
        try(MockWebServer server=new MockWebServer();ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){assertEquals("/api/works/7/personal",request.getPath());entered.countDown();try{release.await(4,TimeUnit.SECONDS);}catch(InterruptedException e){Thread.currentThread().interrupt();}return new MockResponse().setBody("{\"ok\":true,\"personal\":{\"favorite\":1,\"liked\":0,\"disliked\":0,\"rating\":null,\"watchlist\":0}}");}});server.start();PlayerActivity activity=lifecycle.get();JSONObject old=build(activity,server);((Button)get(activity,"personalFavorite")).performClick();assertTrue(entered.await(3,TimeUnit.SECONDS));
            JSONObject next=new JSONObject().put("id",8).put("title","Next").put("favorite",0);put(activity,"work",next);put(activity,"file",new JSONObject().put("id",80));call(activity,"refreshPersonal");release.countDown();waitFor(()->old.optInt("favorite")==1);assertEquals(0,next.optInt("favorite"));assertEquals("收藏",((Button)get(activity,"personalFavorite")).getText().toString());
        }finally{release.countDown();}
    }
}
