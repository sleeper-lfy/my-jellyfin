package net.lumen.media;

import android.app.AlertDialog;
import android.content.Intent;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.view.inputmethod.EditorInfo;
import android.widget.EditText;
import android.widget.Spinner;
import android.widget.TextView;
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
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.BooleanSupplier;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33)
public class BrowseScopeTest {
    private void set(Object target,String name,Object value)throws Exception{Field field=target.getClass().getDeclaredField(name);field.setAccessible(true);field.set(target,value);}
    private Object read(Object target,String name)throws Exception{Field field=target.getClass().getDeclaredField(name);field.setAccessible(true);return field.get(target);}
    private Object call(Object target,String name)throws Exception{Method method=target.getClass().getDeclaredMethod(name);method.setAccessible(true);return method.invoke(target);}
    private void waitFor(BooleanSupplier condition)throws Exception{long deadline=System.currentTimeMillis()+5000;while(!condition.getAsBoolean()&&System.currentTimeMillis()<deadline){Thread.sleep(15);shadowOf(Looper.getMainLooper()).idle();}assertTrue(condition.getAsBoolean());}
    private EditText search(View view){if(view instanceof EditText)return (EditText)view;if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){EditText result=search(((ViewGroup)view).getChildAt(i));if(result!=null)return result;}return null;}
    private Spinner spinner(View view){if(view instanceof Spinner)return (Spinner)view;if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){Spinner result=spinner(((ViewGroup)view).getChildAt(i));if(result!=null)return result;}return null;}
    private void connect(MainActivity activity,MockWebServer server)throws Exception{set(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));}
    private MockResponse empty(){return new MockResponse().setBody("{\"items\":[],\"total\":0,\"tags\":[],\"actors\":[],\"years\":[]}");}
    @Test public void smartListKeepsIdentityWhileSortingSearchingAndFiltering()throws Exception{
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){if(request.getPath().equals("/api/lists"))return new MockResponse().setBody("{\"items\":[{\"name\":\"Saved favorites\",\"filters\":{\"favorite\":true,\"sort\":\"year\",\"descending\":false}}]}");return empty();}});server.start();MainActivity activity=lifecycle.get();connect(activity,server);call(activity,"showLibrary");call(activity,"smartLists");
            waitFor(()->org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog()!=null);AlertDialog lists=org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog();lists.getListView().performItemClick(null,0,0);
            assertEquals("Saved favorites",read(activity,"savedList"));assertEquals("year",read(activity,"sortField"));assertEquals(false,read(activity,"sortDescending"));
            call(activity,"sorting");AlertDialog sorting=org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog();sorting.getListView().performItemClick(null,1,1);assertEquals("Saved favorites",read(activity,"savedList"));String path=(String)call(activity,"listPath");assertTrue(path.contains("list=Saved%20favorites"));assertTrue(path.contains("sort=title"));
            EditText search=search((View)read(activity,"root"));search.setText("Coast");search.onEditorAction(EditorInfo.IME_ACTION_SEARCH);assertEquals("Saved favorites",read(activity,"savedList"));assertTrue(((String)call(activity,"listPath")).contains("q=Coast"));
            call(activity,"showFilters");AlertDialog filters=org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog();spinner(filters.getWindow().getDecorView()).setSelection(2);filters.getButton(AlertDialog.BUTTON_POSITIVE).performClick();path=(String)call(activity,"listPath");assertTrue(path.contains("list=Saved%20favorites"));assertTrue(path.contains("watch_state=progress"));
        }
    }
    @Test public void shuffleSendsTheCompleteBrowseScopeIncludingPagingListsAndDiscoveryResults()throws Exception{
        AtomicReference<String> received=new AtomicReference<>();AtomicInteger legacy=new AtomicInteger();
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){
                if(request.getPath().equals("/api/queue"))legacy.incrementAndGet();
                if(request.getPath().equals("/api/queue/from-browse")){try{received.set(new JSONObject(request.getBody().readUtf8()).getString("browse_path"));}catch(Exception error){throw new AssertionError(error);}return new MockResponse().setBody("{\"ids\":[42]}");}return empty();
            }});server.start();MainActivity activity=lifecycle.get();connect(activity,server);
            for(int scenario=0;scenario<4;scenario++){
                call(activity,"resetBrowseFilters");set(activity,"offset",90);set(activity,"watchFilter","progress");
                if(scenario==0){set(activity,"savedList","Saved favorites");set(activity,"query","Coast");}
                if(scenario==1){set(activity,"kind","vr");set(activity,"watchlistOnly",true);set(activity,"actorFilter","Actor");}
                if(scenario==2){set(activity,"discovery",true);set(activity,"discoveryOnline",true);set(activity,"discoveryResultIds",new JSONArray().put(7).put(8));set(activity,"discoveryResultTag","Travel");}
                if(scenario==3)set(activity,"recommended",true);
                String expected=(String)call(activity,"listPath");received.set(null);call(activity,"shuffle");waitFor(()->received.get()!=null);assertEquals(expected,received.get());assertTrue(received.get().contains("offset=90"));assertTrue(received.get().contains("watch_state=progress"));
                waitFor(()->shadowOf(activity).peekNextStartedActivity()!=null);Intent launch=shadowOf(activity).getNextStartedActivity();assertEquals(42,launch.getLongExtra("work_id",0));assertTrue(launch.getBooleanExtra("queue",false));
            }
            assertEquals(0,legacy.get());
        }
    }
    @Test public void olderServerCannotSilentlyExpandShuffleOrReplacePhoneQueue()throws Exception{
        AtomicInteger posts=new AtomicInteger();
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){if(request.getMethod().equals("POST")){posts.incrementAndGet();assertEquals("/api/queue/from-browse",request.getPath());return new MockResponse().setResponseCode(404).setBody("{}");}return empty();}});server.start();MainActivity activity=lifecycle.get();connect(activity,server);activity.getSharedPreferences("queue",0).edit().putString("ids","[9]").commit();set(activity,"savedList","Only one film");call(activity,"shuffle");
            waitFor(()->org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog()!=null);AlertDialog failure=org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog();TextView message=failure.findViewById(android.R.id.message);assertTrue(message.getText().toString().contains("更新电脑端"));assertEquals("[9]",activity.getSharedPreferences("queue",0).getString("ids",""));assertEquals(1,posts.get());assertNull(shadowOf(activity).getNextStartedActivity());failure.dismiss();
        }
    }
}
