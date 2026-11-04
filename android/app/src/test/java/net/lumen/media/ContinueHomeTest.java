package net.lumen.media;

import android.content.Intent;
import android.content.res.Configuration;
import android.os.Bundle;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
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
import org.json.JSONObject;
import org.json.JSONArray;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33)
public class ContinueHomeTest {
    private Object get(Object target,String name)throws Exception{Field field=target.getClass().getDeclaredField(name);field.setAccessible(true);return field.get(target);}
    private void set(Object target,String name,Object value)throws Exception{Field field=target.getClass().getDeclaredField(name);field.setAccessible(true);field.set(target,value);}
    private Object call(Object target,String name)throws Exception{Method method=target.getClass().getDeclaredMethod(name);method.setAccessible(true);return method.invoke(target);}
    private View find(View view,String text){
        if(view instanceof TextView&&((TextView)view).getText().toString().equals(text))return view;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){View result=find(((ViewGroup)view).getChildAt(i),text);if(result!=null)return result;}
        return null;
    }
    private void pump()throws Exception{Thread.sleep(15);shadowOf(Looper.getMainLooper()).idle();}
    @Test public void continueShelfStartsExactFileAndResumeKeepsBrowseRoot()throws Exception{
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create().start().resume()){
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){
                if(request.getPath().startsWith("/api/continue"))return new MockResponse().setBody("{\"items\":[{\"id\":42,\"title\":\"Recently watched\",\"resume\":{\"file_id\":77,\"position\":125,\"duration\":600,\"label\":\"继续 Part 2 · 2:05 · 剩余 7:55\"}}]}");
                return new MockResponse().setBody("{\"items\":[],\"total\":0}");
            }});server.start();MainActivity activity=lifecycle.get();set(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));
            call(activity,"showLibrary");View root=activity.findViewById(android.R.id.content);long deadline=System.currentTimeMillis()+5000;
            while(find(root,"继续播放")==null&&System.currentTimeMillis()<deadline)pump();
            assertNotNull(find(root,"继续观看"));assertNotNull(find(root,"继续 Part 2 · 2:05 · 剩余 7:55"));
            Object original=get(activity,"root");set(activity,"offset",90);
            find(root,"继续播放").performClick();Intent launch=shadowOf(activity).getNextStartedActivity();
            assertEquals(42,launch.getLongExtra("work_id",0));assertEquals(77,launch.getLongExtra("file_id",0));
            lifecycle.pause().resume();assertSame(original,get(activity,"root"));assertEquals(90,get(activity,"offset"));
        }
    }
    @Test public void savedBrowseStateRetainsFiltersPageTargetAndScroll()throws Exception{
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){
                try{
                    String path=request.getPath();int start=Integer.parseInt(path.split("offset=")[1].split("&")[0]);JSONArray rows=new JSONArray();
                    for(int i=start;i<Math.min(90,start+30);i++)rows.put(new JSONObject().put("id",i+1).put("title","Film "+i).put("kind","movie"));
                    return new MockResponse().setBody(new JSONObject().put("items",rows).put("total",90).toString());
                }catch(Exception error){return new MockResponse().setBody("{\"items\":[],\"total\":0}");}
            }});server.start();MainActivity activity=lifecycle.get();set(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));
            set(activity,"kind","vr");set(activity,"actorFilter","Actor");set(activity,"tagsAllFilter","Tag A,Tag B");call(activity,"showLibrary");
            long deadline=System.currentTimeMillis()+5000;while((int)get(activity,"offset")<30&&System.currentTimeMillis()<deadline)pump();
            set(activity,"offset",90);Bundle state=(Bundle)call(activity,"browseState");state.putInt("scroll",450);
            Method restore=MainActivity.class.getDeclaredMethod("restoreBrowseState",Bundle.class);restore.setAccessible(true);restore.invoke(activity,state);
            assertEquals("vr",get(activity,"kind"));assertEquals("Actor",get(activity,"actorFilter"));assertEquals("Tag A,Tag B",get(activity,"tagsAllFilter"));
            assertEquals(90,get(activity,"restoreOffset"));assertEquals(450,get(activity,"restoreScroll"));
            deadline=System.currentTimeMillis()+5000;while((int)get(activity,"offset")<90&&System.currentTimeMillis()<deadline)pump();
            assertEquals(90,get(activity,"offset"));assertEquals(0,get(activity,"restoreOffset"));
        }
    }
}
