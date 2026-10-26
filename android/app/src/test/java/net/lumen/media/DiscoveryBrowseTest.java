package net.lumen.media;

import android.content.Intent;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.widget.AutoCompleteTextView;
import android.widget.EditText;
import android.widget.Spinner;
import android.widget.TextView;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import org.robolectric.android.controller.ActivityController;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33)
public class DiscoveryBrowseTest {
    private void set(Object object,String name,Object value)throws Exception{Field field=object.getClass().getDeclaredField(name);field.setAccessible(true);field.set(object,value);}
    private Object get(Object object,String name){try{Field field=object.getClass().getDeclaredField(name);field.setAccessible(true);return field.get(object);}catch(Exception error){throw new RuntimeException(error);}}
    private void call(Object object,String name)throws Exception{Method method=object.getClass().getDeclaredMethod(name);method.setAccessible(true);method.invoke(object);}
    private String path(MainActivity activity)throws Exception{Method method=MainActivity.class.getDeclaredMethod("listPath");method.setAccessible(true);return (String)method.invoke(activity);}
    private View root(MainActivity activity){return activity.findViewById(android.R.id.content);}
    private View text(View view,String wanted,boolean contains){
        if(view instanceof TextView&&(contains?((TextView)view).getText().toString().contains(wanted):((TextView)view).getText().toString().equals(wanted)))return view;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){View found=text(((ViewGroup)view).getChildAt(i),wanted,contains);if(found!=null)return found;}
        return null;
    }
    private EditText name(View view){
        if(view instanceof EditText&&"发现影片名称搜索".contentEquals(view.getContentDescription()))return (EditText)view;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){EditText found=name(((ViewGroup)view).getChildAt(i));if(found!=null)return found;}
        return null;
    }
    private AutoCompleteTextView firstTag(View view){
        if(view instanceof AutoCompleteTextView)return (AutoCompleteTextView)view;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){AutoCompleteTextView found=firstTag(((ViewGroup)view).getChildAt(i));if(found!=null)return found;}
        return null;
    }
    private void waitFor(java.util.function.BooleanSupplier condition)throws Exception{
        long deadline=System.currentTimeMillis()+7000;
        while(!condition.getAsBoolean()&&System.currentTimeMillis()<deadline){Thread.sleep(10);shadowOf(Looper.getMainLooper()).idleFor(50,TimeUnit.MILLISECONDS);}
        assertTrue("Asynchronous discovery result did not arrive",condition.getAsBoolean());
    }
    private void show(MainActivity activity,MockWebServer server,boolean online)throws Exception{
        set(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));
        set(activity,"discovery",true);set(activity,"discoveryOnline",online);call(activity,"showLibrary");
    }
    private MockResponse json(String body){return new MockResponse().setHeader("Content-Type","application/json").setBody(body);}
    private String providers(){return "{\"items\":[{\"id\":\"archive\",\"name\":\"Archive\",\"supports_tags\":true},{\"id\":\"names\",\"name\":\"Names only\",\"supports_tags\":false}]}";}
    private String facets(){return "{\"tags\":[\"Drama\",\"Travel\"],\"actors\":[],\"years\":[]}";}

    @Test public void visibleNameTagAndSortControlsSendCombinedFullResultQueryAndKeepIndependentPreferences()throws Exception{
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){
                assertEquals("Bearer abcdefghijklmnopqrstuvwxyz123456",request.getHeader("Authorization"));
                return json(request.getPath().startsWith("/api/filters")?facets():"{\"items\":[],\"total\":0}");
            }});server.start();MainActivity activity=lifecycle.get();show(activity,server,false);
            assertEquals("按影片名称搜索",name(root(activity)).getHint().toString());
            AutoCompleteTextView tag=root(activity).findViewWithTag("discoveryTag");assertNotNull(tag);
            waitFor(()->tag.getAdapter().getCount()==2);
            name(root(activity)).setText("Sample title");tag.setText("Dra",false);root(activity).findViewWithTag("discoverySearch").performClick();
            String selected=path(activity);assertTrue(selected.contains("q=Sample%20title"));assertTrue(selected.contains("tag_q=Dra"));assertTrue(selected.contains("sort=discovered"));
            set(activity,"offset",60);Spinner sort=root(activity).findViewWithTag("discoverySort");sort.getOnItemSelectedListener().onItemSelected(sort,null,2,2);
            assertTrue(path(activity).contains("offset=0"));assertTrue(path(activity).contains("sort=title"));
            root(activity).findViewWithTag("discoveryDirection").performClick();assertTrue(path(activity).contains("direction=asc"));
            assertEquals("title",activity.getSharedPreferences("discovery",0).getString("sort",""));assertFalse(activity.getSharedPreferences("discovery",0).getBoolean("descending",true));
            assertEquals("added",get(activity,"sortField"));assertEquals(true,get(activity,"sortDescending"));
            assertTrue(path(activity).contains("q=Sample%20title")&&path(activity).contains("tag_q=Dra"));
        }
    }

    @Test public void onlineSearchSurvivesSortDuringSubmissionAndSortsOnlyReturnedIdsWithoutLocalSubstringFilters()throws Exception{
        AtomicInteger posts=new AtomicInteger(),polls=new AtomicInteger();AtomicReference<String> payload=new AtomicReference<>(),resultPath=new AtomicReference<>();
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){
                String path=request.getPath();assertEquals("Bearer abcdefghijklmnopqrstuvwxyz123456",request.getHeader("Authorization"));
                if(path.startsWith("/api/discovery/providers"))return json(providers());
                if(path.startsWith("/api/filters"))return json(facets());
                if(path.equals("/api/discovery/search")&&request.getMethod().equals("POST")){posts.incrementAndGet();payload.set(request.getBody().readUtf8());return json("{\"task_id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"}").setResponseCode(202).setBodyDelay(300,TimeUnit.MILLISECONDS);}
                if(path.startsWith("/api/discovery/search/"))return json(polls.incrementAndGet()==1?"{\"status\":\"running\"}":"{\"status\":\"done\",\"result\":{\"ids\":[42,43],\"errors\":[{\"plugin\":\"names\",\"name\":\"Names only\",\"message\":\"不支持标签搜索\"}]}}");
                if(path.equals("/api/works/42"))return json("{\"id\":42,\"title\":\"Provider spelling differs\",\"kind\":\"movie\",\"files\":[],\"tags\":[\"Other tag\"]}");
                if(path.startsWith("/api/discover?")){resultPath.set(path);return json("{\"items\":[{\"id\":42,\"title\":\"Provider spelling differs\",\"kind\":\"movie\"},{\"id\":43,\"title\":\"Another match\",\"kind\":\"movie\"}],\"total\":2}");}
                return json("{}");
            }});server.start();MainActivity activity=lifecycle.get();show(activity,server,true);
            waitFor(()->root(activity).findViewWithTag("discoverySearch").isEnabled());
            set(activity,"kind","fans");set(activity,"actorFilter","Old actor");set(activity,"yearFilter","2020");set(activity,"favorites",true);set(activity,"watchFilter","completed");set(activity,"savedList","Old list");
            name(root(activity)).setText("Search words");((AutoCompleteTextView)root(activity).findViewWithTag("discoveryTag")).setText("Drama",false);
            root(activity).findViewWithTag("discoverySearch").performClick();root(activity).findViewWithTag("discoveryDirection").performClick();
            waitFor(()->root(activity).findViewWithTag("card:42")!=null);
            JSONObject submitted=new JSONObject(payload.get());assertEquals("Search words",submitted.getString("query"));assertEquals("Drama",submitted.getString("tag"));assertEquals("",submitted.getString("plugin"));
            assertTrue(resultPath.get().contains("ids=42,43"));assertTrue(resultPath.get().contains("&q=&tag_q="));assertFalse(resultPath.get().contains("Search%20words"));
            assertTrue(resultPath.get().contains("&kind=&favorite=false"));assertTrue(resultPath.get().contains("&actor=&year="));assertTrue(resultPath.get().contains("&watch_state=&list=&ids="));
            assertNotNull(text(root(activity),"Names only：不支持标签搜索",true));assertEquals(1,posts.get());
            Spinner sort=root(activity).findViewWithTag("discoverySort");sort.getOnItemSelectedListener().onItemSelected(sort,null,4,4);
            assertTrue(path(activity).contains("sort=community_rating"));assertTrue(path(activity).contains("ids=42,43"));assertEquals(1,posts.get());
            call(activity,"showFilters");android.app.AlertDialog filter=org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog();
            firstTag(filter.getWindow().getDecorView()).setText("Narrow result",false);filter.getButton(android.app.AlertDialog.BUTTON_POSITIVE).performClick();
            assertTrue(path(activity).contains("ids=42,43"));assertTrue(path(activity).contains("tag_q=Narrow%20result"));assertEquals("Drama",((AutoCompleteTextView)root(activity).findViewWithTag("discoveryTag")).getText().toString());
            waitFor(()->root(activity).findViewWithTag("card:42")!=null);root(activity).findViewWithTag("card:42").performClick();
            waitFor(()->text(root(activity),"Other tag",false)!=null);text(root(activity),"Other tag",false).performClick();
            assertTrue(path(activity).contains("tag_q=Other%20tag"));assertFalse(path(activity).contains("&ids="));
            activity.onBackPressed();assertEquals(42L,get(activity,"detailId"));assertTrue(path(activity).contains("ids=42,43"));assertTrue(path(activity).contains("sort=community_rating"));assertTrue(path(activity).contains("tag_q=Narrow%20result"));
            activity.onBackPressed();assertEquals(0L,get(activity,"detailId"));assertEquals(1,posts.get());
        }
    }

    @Test public void unsupportedTagSearchIsExplainedAndFailedSearchCanRetryWithExplicitEmptyResultIds()throws Exception{
        AtomicInteger posts=new AtomicInteger();
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){
                String path=request.getPath();
                if(path.startsWith("/api/discovery/providers"))return json(providers());if(path.startsWith("/api/filters"))return json(facets());
                if(path.equals("/api/discovery/search")&&request.getMethod().equals("POST")){int attempt=posts.incrementAndGet();return json("{\"task_id\":\""+(attempt==1?"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")+"\"}").setResponseCode(202);}
                if(path.startsWith("/api/discovery/search/"))return json(path.endsWith("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")?"{\"status\":\"failed\",\"error\":\"Source unavailable\",\"result\":{\"errors\":[{\"name\":\"Names only\",\"message\":\"HTTP 503\"}]}}":"{\"status\":\"done\",\"result\":{\"ids\":[],\"errors\":[]}}");
                return json("{\"items\":[],\"total\":0}");
            }});server.start();MainActivity activity=lifecycle.get();set(activity,"discoveryProvider","names");show(activity,server,true);
            waitFor(()->root(activity).findViewWithTag("discoverySearch").isEnabled());
            name(root(activity)).setText("Title");((AutoCompleteTextView)root(activity).findViewWithTag("discoveryTag")).setText("Drama",false);root(activity).findViewWithTag("discoverySearch").performClick();
            assertNotNull(text(root(activity),"该站点不支持标签搜索",true));assertEquals(0,posts.get());
            ((AutoCompleteTextView)root(activity).findViewWithTag("discoveryTag")).setText("",false);root(activity).findViewWithTag("discoverySearch").performClick();
            waitFor(()->"failed".equals(get(activity,"discoverySearchState")));
            assertNotNull(text(root(activity),"Names only：HTTP 503",true));assertTrue(root(activity).findViewWithTag("discoverySearch").isEnabled());
            root(activity).findViewWithTag("discoverySearch").performClick();waitFor(()->"done".equals(get(activity,"discoverySearchState")));
            assertEquals(2,posts.get());assertTrue(path(activity).endsWith("&ids="));
            waitFor(()->text(root(activity),"本次站点搜索没有匹配结果",true)!=null);
        }
    }

    @Test public void fansCategoryShowsAuthorVideosAndStartsNormalPlayerWithSelectedFile()throws Exception{
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){return json("{\"items\":[],\"total\":0}");}});server.start();MainActivity activity=lifecycle.get();
            set(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));call(activity,"showLibrary");
            View fans=text(root(activity),"Fans视频",false);assertNotNull(fans);fans.performClick();assertTrue(path(activity).contains("kind=fans"));
            JSONObject work=new JSONObject("{\"id\":42,\"title\":\"Author example\",\"kind\":\"fans\",\"file_count\":2,\"files\":[{\"id\":101,\"name\":\"First video\",\"duration\":120},{\"id\":102,\"name\":\"Second video\",\"duration\":180}]}");
            Method render=MainActivity.class.getDeclaredMethod("renderDetail",JSONObject.class);render.setAccessible(true);render.invoke(activity,work);
            assertNotNull(text(root(activity),"作者视频",false));assertNull(text(root(activity),"季与集",false));assertFalse(VrProjection.autoEnable("fans"));
            text(root(activity),"Second video  ·  3 分钟",false).performClick();Intent intent=shadowOf(activity).getNextStartedActivity();
            assertEquals(PlayerActivity.class.getName(),intent.getComponent().getClassName());assertEquals(42,intent.getLongExtra("work_id",0));assertEquals(102,intent.getLongExtra("file_id",0));assertTrue(intent.getStringExtra("browse_path").contains("kind=fans"));
        }
    }
}
