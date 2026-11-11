package net.lumen.media;

import android.app.AlertDialog;
import android.content.Intent;
import android.os.Looper;
import android.view.View;
import android.widget.TextView;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.shadows.ShadowAlertDialog;
import org.robolectric.shadows.ShadowToast;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BooleanSupplier;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

/** Exercises the live entry points and the independent, authenticated queue request. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w393dp-h852dp-mdpi")
public class GlobalShuffleTest {
    private static final String TOKEN="abcdefghijklmnopqrstuvwxyz123456";
    private static final class Fixture implements AutoCloseable {
        final MockWebServer server=new MockWebServer();
        final BlockingQueue<RecordedRequest> posts=new LinkedBlockingQueue<>();
        final ActivityController<MainActivity> life;
        final MainActivity page;
        volatile int status=200;
        volatile String response="{\"ids\":[42]}";
        volatile boolean holdFirst;
        final CountDownLatch firstReceived=new CountDownLatch(1),releaseFirst=new CountDownLatch(1);
        final AtomicInteger postCount=new AtomicInteger();
        Fixture()throws Exception{
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request)throws InterruptedException{
                if("POST".equals(request.getMethod())){
                    int sequence=postCount.incrementAndGet(),code=status;String body=response;posts.add(request);
                    if(holdFirst&&sequence==1){firstReceived.countDown();if(!releaseFirst.await(6,TimeUnit.SECONDS))return new MockResponse().setResponseCode(504);}
                    return new MockResponse().setResponseCode(code).setBody(body);
                }
                return new MockResponse().setBody("{\"items\":[],\"total\":0,\"tags\":[],\"actors\":[],\"years\":[]}");
            }});server.start();life=Robolectric.buildActivity(MainActivity.class).create();page=life.get();
            page.api=new Api(new Connection(server.url("/").toString(),TOKEN));
        }
        @Override public void close()throws Exception{releaseFirst.countDown();life.destroy();server.shutdown();}
    }
    private Object read(MainActivity page,String name)throws Exception{Field field=MainActivity.class.getDeclaredField(name);field.setAccessible(true);return field.get(page);}
    private void set(MainActivity page,String name,Object value)throws Exception{Field field=MainActivity.class.getDeclaredField(name);field.setAccessible(true);field.set(page,value);}
    private void call(MainActivity page,String name)throws Exception{Method method=MainActivity.class.getDeclaredMethod(name);method.setAccessible(true);method.invoke(page);}
    private View root(MainActivity page)throws Exception{return (View)read(page,"root");}
    private void waitFor(BooleanSupplier ready)throws Exception{
        long deadline=System.currentTimeMillis()+6000;
        while(!ready.getAsBoolean()&&System.currentTimeMillis()<deadline){Thread.sleep(10);shadowOf(Looper.getMainLooper()).idle();}
        assertTrue("The real asynchronous queue request did not complete",ready.getAsBoolean());
    }
    private AlertDialog open(MainActivity page)throws Exception{call(page,"showGlobalShuffle");AlertDialog dialog=ShadowAlertDialog.getLatestAlertDialog();assertNotNull(dialog);assertTrue(dialog.isShowing());return dialog;}
    private void choose(AlertDialog dialog,int index){dialog.getListView().performItemClick(null,index,index);}
    // Platform dialog listeners are delivered through the main Handler.
    private void confirm(AlertDialog dialog){dialog.getButton(AlertDialog.BUTTON_POSITIVE).performClick();shadowOf(Looper.getMainLooper()).idle();}
    private void assertRequest(Fixture fixture,String path)throws Exception{
        RecordedRequest request=fixture.posts.poll(6,TimeUnit.SECONDS);assertNotNull("Missing queue POST",request);
        assertEquals("/api/queue/from-browse",request.getPath());assertEquals("Bearer "+TOKEN,request.getHeader("Authorization"));
        JSONObject body=new JSONObject(request.getBody().readUtf8());assertEquals(1,body.length());assertEquals(path,body.getString("browse_path"));
    }
    private Intent awaitPlayer(MainActivity page)throws Exception{
        waitFor(()->shadowOf(page).peekNextStartedActivity()!=null);Intent intent=shadowOf(page).getNextStartedActivity();
        assertEquals(PlayerActivity.class.getName(),intent.getComponent().getClassName());assertTrue(intent.getBooleanExtra("queue",false));return intent;
    }
    private void conditions(MainActivity page)throws Exception{
        page.kind="vr";page.query="当前片名";page.savedList="只看这份片单";page.tagFilter="标签";page.actorFilter="演员";
        page.yearMinFilter="2020";page.yearMaxFilter="2025";page.ratingMinFilter="8";page.tagsAllFilter="全部A,全部B";
        page.tagsAnyFilter="任一";page.tagsNotFilter="排除";page.watchFilter="progress";page.offset=90;
        page.favorites=true;page.watchlistOnly=true;page.dislikedOnly=true;page.recommended=true;page.discovery=true;
        page.discoveryOnline=true;page.discoveryResultIds=new JSONArray().put(7).put(8);page.discoveryResultTag="本次结果";
    }
    private String conditionsSnapshot(MainActivity page)throws Exception{
        return page.listPath()+"|"+page.discoveryResultIds+"|"+page.discoveryResultTag+"|"+page.recommended+"|"+page.offset+"|"+read(page,"mainPage");
    }

    @Test public void homeAndMineExposeTheSameScopeDialogAndCancellationSendsNothing()throws Exception{
        try(Fixture fixture=new Fixture()){
            MainActivity page=fixture.page;page.showLibrary();View home=root(page);View entry=home.findViewWithTag("globalShuffle");assertNotNull(entry);
            assertEquals(page.getString(R.string.global_shuffle_action),((TextView)entry).getText().toString());entry.performClick();
            AlertDialog scope=ShadowAlertDialog.getLatestAlertDialog();assertEquals(0,scope.getListView().getCheckedItemPosition());
            assertEquals(6,scope.getListView().getAdapter().getCount());assertTrue(scope.getListView().getAdapter().getItem(0).toString().contains("VR"));
            TextView hint=scope.getWindow().getDecorView().findViewWithTag("globalShuffleHint");assertNotNull(hint);assertTrue(hint.getText().toString().contains("自动进入 VR"));
            choose(scope,3);scope.getButton(AlertDialog.BUTTON_NEGATIVE).performClick();assertEquals("",page.getSharedPreferences("global_shuffle",0).getString("scope",""));
            call(page,"showMine");View mine=root(page);assertNotNull(mine.findViewWithTag("globalShuffle"));mine.findViewWithTag("globalShuffle").performClick();
            scope=ShadowAlertDialog.getLatestAlertDialog();assertEquals(0,scope.getListView().getCheckedItemPosition());scope.getButton(AlertDialog.BUTTON_NEGATIVE).performClick();
            assertTrue(fixture.posts.isEmpty());assertNull(shadowOf(page).getNextStartedActivity());
        }
    }

    @Test public void allMediaIgnoresEveryCurrentScopeAndPersistsTheCompleteUnpaginatedQueue()throws Exception{
        try(Fixture fixture=new Fixture()){
            MainActivity page=fixture.page;page.showLibrary();View original=root(page);conditions(page);String before=conditionsSnapshot(page);
            JSONArray ids=new JSONArray();for(int index=0;index<75;index++)ids.put(1000+index);fixture.response=new JSONObject().put("ids",ids).toString();
            page.getSharedPreferences("queue",0).edit().putString("ids","[9]").putInt("index",1).putInt("repeat",2).commit();
            original.findViewWithTag("globalShuffle").performClick();confirm(ShadowAlertDialog.getLatestAlertDialog());assertRequest(fixture,"/api/works");
            Intent player=awaitPlayer(page);assertEquals(1000,player.getLongExtra("work_id",0));assertFalse(player.hasExtra("browse_path"));
            assertEquals(ids.toString(),page.getSharedPreferences("queue",0).getString("ids",""));assertEquals(0,page.getSharedPreferences("queue",0).getInt("index",-1));assertEquals(2,page.getSharedPreferences("queue",0).getInt("repeat",-1));
            assertSame(original,root(page));assertEquals(before,conditionsSnapshot(page));assertEquals("",page.getSharedPreferences("global_shuffle",0).getString("scope","missing"));assertTrue(fixture.posts.isEmpty());
        }
    }

    @Test public void eachExplicitKindUsesOnlyItsIndependentPathAndVrSelectionSurvivesReopening()throws Exception{
        try(Fixture fixture=new Fixture()){
            MainActivity page=fixture.page;conditions(page);String before=conditionsSnapshot(page);String[] kinds={"","movie","series","vr","fans","other"};
            for(int index=0;index<kinds.length;index++){
                AlertDialog scope=open(page);choose(scope,index);confirm(scope);assertRequest(fixture,"/api/works"+(index==0?"":"?kind="+kinds[index]));assertEquals(42,awaitPlayer(page).getLongExtra("work_id",0));
                assertEquals(kinds[index],page.getSharedPreferences("global_shuffle",0).getString("scope","missing"));assertEquals(before,conditionsSnapshot(page));
            }
            AlertDialog scope=open(page);choose(scope,3);confirm(scope);assertRequest(fixture,"/api/works?kind=vr");awaitPlayer(page);
            scope=open(page);assertEquals(3,scope.getListView().getCheckedItemPosition());assertTrue(scope.getListView().getAdapter().getItem(3).toString().contains("VR"));choose(scope,1);scope.getButton(AlertDialog.BUTTON_NEGATIVE).performClick();
            try(ActivityController<MainActivity> next=Robolectric.buildActivity(MainActivity.class).create()){
                MainActivity reopened=next.get();reopened.api=new Api(new Connection(fixture.server.url("/").toString(),TOKEN));AlertDialog remembered=open(reopened);assertEquals(3,remembered.getListView().getCheckedItemPosition());remembered.dismiss();
            }
            assertEquals(before,conditionsSnapshot(page));assertTrue(fixture.posts.isEmpty());
        }
    }

    @Test public void emptyUnsupportedAndFailedGlobalRequestsKeepTheExistingQueueAndNeverLaunch()throws Exception{
        try(Fixture fixture=new Fixture()){
            MainActivity page=fixture.page;page.getSharedPreferences("queue",0).edit().putString("ids","[9,11]").putInt("index",1).putInt("repeat",2).commit();
            int[] statuses={200,404,503,200};String[] replies={"{\"ids\":[]}","{}","{}","{\"ids\":[0]}"};
            for(int index=0;index<statuses.length;index++){
                fixture.status=statuses[index];fixture.response=replies[index];AlertDialog scope=open(page);confirm(scope);assertRequest(fixture,"/api/works");
                if(index==0)waitFor(()->page.getString(R.string.global_shuffle_empty).equals(ShadowToast.getTextOfLatestToast()));
                else{
                    waitFor(()->{AlertDialog failure=ShadowAlertDialog.getLatestAlertDialog();return failure!=null&&failure!=scope&&failure.isShowing();});
                    AlertDialog failure=ShadowAlertDialog.getLatestAlertDialog();assertEquals(page.getString(R.string.global_shuffle_failed_title),shadowOf(failure).getTitle().toString());
                    if(statuses[index]==404){TextView message=failure.findViewById(android.R.id.message);assertEquals(page.getString(R.string.global_shuffle_update_required),message.getText().toString());assertFalse(message.getText().toString().contains("当前列表"));}
                    failure.getButton(AlertDialog.BUTTON_POSITIVE).performClick();
                }
                assertEquals("[9,11]",page.getSharedPreferences("queue",0).getString("ids",""));assertEquals(1,page.getSharedPreferences("queue",0).getInt("index",-1));assertEquals(2,page.getSharedPreferences("queue",0).getInt("repeat",-1));assertNull(shadowOf(page).getNextStartedActivity());assertTrue(fixture.posts.isEmpty());
            }
        }
    }

    @Test public void existingCurrentListShuffleRetainsItsFullBrowsePathAndDoesNotChangeGlobalScope()throws Exception{
        try(Fixture fixture=new Fixture()){
            MainActivity page=fixture.page;conditions(page);page.getSharedPreferences("global_shuffle",0).edit().putString("scope","series").commit();String current=page.listPath();
            page.shuffle();assertRequest(fixture,current);assertEquals(42,awaitPlayer(page).getLongExtra("work_id",0));assertEquals("series",page.getSharedPreferences("global_shuffle",0).getString("scope",""));
            assertTrue(current.contains("offset=90"));assertTrue(current.contains("list="));assertEquals(current,page.listPath());assertTrue(fixture.posts.isEmpty());
        }
    }

    @Test public void aLateResponseCannotReplaceTheNewerGlobalOrCurrentListQueue()throws Exception{
        for(boolean globalFirst:new boolean[]{true,false})try(Fixture fixture=new Fixture()){
            MainActivity page=fixture.page;conditions(page);String current=page.listPath();fixture.holdFirst=true;fixture.response="{\"ids\":[61]}";
            if(globalFirst)confirm(open(page));else page.shuffle();
            assertTrue("The first HTTP request must be in flight",fixture.firstReceived.await(6,TimeUnit.SECONDS));assertRequest(fixture,globalFirst?"/api/works":current);
            fixture.response="{\"ids\":[42]}";if(globalFirst)page.shuffle();else confirm(open(page));assertRequest(fixture,globalFirst?current:"/api/works");
            assertEquals(42,awaitPlayer(page).getLongExtra("work_id",0));fixture.releaseFirst.countDown();
            // Finish the real HTTP workers before draining their UI callbacks, rather than relying on a sleep.
            page.network.shutdown();assertTrue(page.network.awaitTermination(6,TimeUnit.SECONDS));shadowOf(Looper.getMainLooper()).idle();
            assertEquals("[42]",page.getSharedPreferences("queue",0).getString("ids",""));assertEquals(0,page.getSharedPreferences("queue",0).getInt("index",-1));assertNull("The stale request must not open a second player",shadowOf(page).getNextStartedActivity());
        }
    }
}
