package net.lumen.media;

import android.app.AlertDialog;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.widget.AutoCompleteTextView;
import android.widget.ArrayAdapter;
import android.widget.ScrollView;
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
import java.util.List;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33)
public class BrowseUiTest {
    private void call(Object object,String name)throws Exception{Method method=object.getClass().getDeclaredMethod(name);method.setAccessible(true);method.invoke(object);}
    private void field(Object object,String name,Object value)throws Exception{Field field=object.getClass().getDeclaredField(name);field.setAccessible(true);field.set(object,value);}
    private List<AutoCompleteTextView> inputs(View view){
        List<AutoCompleteTextView> result=new ArrayList<>();
        if(view instanceof AutoCompleteTextView)result.add((AutoCompleteTextView)view);
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++)result.addAll(inputs(((ViewGroup)view).getChildAt(i)));
        return result;
    }
    @Test public void connectionOffersEditableDiscoveredServerDropdownInsideScroll()throws Exception{
        try(ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            MainActivity activity=lifecycle.get();View content=activity.findViewById(android.R.id.content);
            List<AutoCompleteTextView> fields=inputs(content);
            assertEquals(1,fields.size());AutoCompleteTextView address=fields.get(0);
            assertNotNull(address.getAdapter());assertTrue(address.enoughToFilter());
            @SuppressWarnings("unchecked") ArrayAdapter<ServerDiscovery.Server> servers=(ArrayAdapter<ServerDiscovery.Server>)address.getAdapter();
            servers.add(new ServerDiscovery.Server("http://192.168.1.30:18097","Media PC"));
            address.getOnItemClickListener().onItemClick(null,null,0,0);
            assertEquals("http://192.168.1.30:18097",address.getText().toString());
            address.setText("http://192.168.1.55:8097",false);
            assertEquals("http://192.168.1.55:8097",address.getText().toString());
            View parent=address;
            while(parent.getParent() instanceof View&&!(parent instanceof ScrollView))parent=(View)parent.getParent();
            assertTrue("Connect fields must remain reachable on small displays",parent instanceof ScrollView);
        }
    }
    @Test public void tagActorAndYearDropdownsUseAuthenticatedFullLibraryFacetsAndApplyTogether()throws Exception{
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){
                assertEquals("Bearer abcdefghijklmnopqrstuvwxyz123456",request.getHeader("Authorization"));
                return new MockResponse().setHeader("Content-Type","application/json").setBody(request.getPath().startsWith("/api/filters")
                    ?"{\"tags\":[\"Drama\",\"Travel\"],\"actors\":[\"Example actor\"],\"years\":[2024,2020]}"
                    :"{\"items\":[],\"total\":0}");
            }});server.start();MainActivity activity=lifecycle.get();
            field(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));
            call(activity,"showLibrary");call(activity,"showFilters");
            AlertDialog dialog=org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog();
            List<AutoCompleteTextView> fields=inputs(dialog.getWindow().getDecorView());assertEquals(3,fields.size());
            long deadline=System.currentTimeMillis()+6000;
            while(fields.get(0).getAdapter()==null&&System.currentTimeMillis()<deadline){Thread.sleep(20);shadowOf(Looper.getMainLooper()).idle();}
            assertNotNull(fields.get(0).getAdapter());assertEquals(2,fields.get(0).getAdapter().getCount());
            assertEquals("Example actor",fields.get(1).getAdapter().getItem(0));
            assertEquals("2024",fields.get(2).getAdapter().getItem(0));
            fields.get(0).setText("Drama",false);fields.get(1).setText("Example actor",false);fields.get(2).setText("bad",false);
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).performClick();assertTrue(dialog.isShowing());assertNotNull(fields.get(2).getError());
            fields.get(2).setText("2024",false);dialog.getButton(AlertDialog.BUTTON_POSITIVE).performClick();assertFalse(dialog.isShowing());
            Method path=MainActivity.class.getDeclaredMethod("listPath");path.setAccessible(true);String query=(String)path.invoke(activity);
            assertTrue(query.contains("tag=Drama"));assertTrue(query.contains("actor=Example%20actor"));assertTrue(query.contains("year=2024"));
            call(activity,"showFilters");AlertDialog clear=org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog();clear.getButton(AlertDialog.BUTTON_NEUTRAL).performClick();assertTrue(clear.isShowing());clear.getButton(AlertDialog.BUTTON_POSITIVE).performClick();shadowOf(Looper.getMainLooper()).idle();
            assertTrue(((String)path.invoke(activity)).contains("&tag=&actor=&year=&"));
        }
    }
    private View findText(View view,String wanted){
        if(view instanceof android.widget.TextView&&((android.widget.TextView)view).getText().toString().equals(wanted))return view;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){
            View found=findText(((ViewGroup)view).getChildAt(i),wanted);if(found!=null)return found;
        }
        return null;
    }
    @Test public void downloadClickUsesServerQueueAndSavedDirectoryInsteadOfDownloadingOnPhone()throws Exception{
        java.util.concurrent.atomic.AtomicReference<RecordedRequest> submitted=new java.util.concurrent.atomic.AtomicReference<>();
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){
                assertEquals("Bearer abcdefghijklmnopqrstuvwxyz123456",request.getHeader("Authorization"));
                if(request.getMethod().equals("POST")&&request.getPath().equals("/api/works/42/downloads")){
                    submitted.set(request);return new MockResponse().setResponseCode(202).setBody("{\"task_id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"}");
                }
                return new MockResponse().setBody("{\"status\":\"running\",\"payload\":{\"message\":\"Downloading on server\"}}");
            }});server.start();MainActivity activity=lifecycle.get();
            field(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));
            org.json.JSONObject work=new org.json.JSONObject("{\"id\":42,\"title\":\"Chosen movie\",\"kind\":\"movie\",\"year\":2024,\"file_count\":0,\"files\":[],\"download_directory\":\"D:/Media/Movies/Chosen movie\",\"download_url\":[{\"url\":\"https://example.org/video.mp4\",\"method\":\"direct\",\"description\":\"Download sample\"}]}");
            Method render=MainActivity.class.getDeclaredMethod("renderDetail",org.json.JSONObject.class);render.setAccessible(true);render.invoke(activity,work);
            View root=activity.findViewById(android.R.id.content);
            assertNotNull(findText(root,"保存到电脑：D:/Media/Movies/Chosen movie"));
            View download=findText(root,"Download sample");assertNotNull(download);download.performClick();
            long deadline=System.currentTimeMillis()+6000;
            while(activity.getSharedPreferences("download-tasks",0).getString("42","").isEmpty()&&System.currentTimeMillis()<deadline){Thread.sleep(20);shadowOf(Looper.getMainLooper()).idle();}
            assertNotNull(submitted.get());assertEquals("{\"index\":0}",submitted.get().getBody().readUtf8());
            assertEquals("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",activity.getSharedPreferences("download-tasks",0).getString("42",""));
        }
    }

    @Test public void sortingPersistsAndReturningFromDetailKeepsLibraryView()throws Exception{
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){return new MockResponse().setHeader("Content-Type","application/json").setBody("{\"items\":[],\"total\":0}");}});server.start();
            MainActivity activity=lifecycle.get();field(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));
            call(activity,"showLibrary");call(activity,"sorting");AlertDialog menu=org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog();
            menu.getListView().performItemClick(menu.getListView().getChildAt(1),1,1);
            Method path=MainActivity.class.getDeclaredMethod("listPath");path.setAccessible(true);assertTrue(((String)path.invoke(activity)).contains("sort=title"));
            assertEquals("title",activity.getSharedPreferences("catalog",0).getString("sort",""));
            Field root=MainActivity.class.getDeclaredField("root");root.setAccessible(true);Object original=root.get(activity);field(activity,"browseRoot",original);field(activity,"offset",60);
            org.json.JSONObject work=new org.json.JSONObject("{\"id\":42,\"title\":\"Seasons\",\"kind\":\"series\",\"files\":[{\"id\":1,\"name\":\"Episode 1\",\"season\":1,\"episode\":1},{\"id\":2,\"name\":\"Episode 2\",\"season\":2,\"episode\":1}]}");
            Method render=MainActivity.class.getDeclaredMethod("renderDetail",org.json.JSONObject.class);render.setAccessible(true);render.invoke(activity,work);
            assertNotNull(findText(activity.findViewById(android.R.id.content),"季与集"));
            activity.onBackPressed();assertSame(original,root.get(activity));Field offset=MainActivity.class.getDeclaredField("offset");offset.setAccessible(true);assertEquals(60,offset.getInt(activity));
        }
    }

}
