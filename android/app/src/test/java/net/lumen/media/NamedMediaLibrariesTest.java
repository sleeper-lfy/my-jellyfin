package net.lumen.media;

import android.app.Activity;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.os.Bundle;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import com.google.android.material.chip.Chip;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.BooleanSupplier;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.json.JSONArray;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.Shadows;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.GraphicsMode;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w393dp-h852dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
public class NamedMediaLibrariesTest {
    private void set(Object target,String key,Object value)throws Exception{Field field=target.getClass().getDeclaredField(key);field.setAccessible(true);field.set(target,value);}
    private Object get(Object target,String key)throws Exception{Field field=target.getClass().getDeclaredField(key);field.setAccessible(true);return field.get(target);}
    private Object call(Object target,String name,Class<?>[] types,Object... args)throws Exception{Method method=target.getClass().getDeclaredMethod(name,types);method.setAccessible(true);return method.invoke(target,args);}
    private void waitFor(BooleanSupplier ready)throws Exception{long until=System.currentTimeMillis()+6000;while(!ready.getAsBoolean()&&System.currentTimeMillis()<until){Thread.sleep(15);Shadows.shadowOf(Looper.getMainLooper()).idle();}assertTrue(ready.getAsBoolean());}
    private void layout(View root,int width,int height){for(int i=0;i<3;i++){root.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(height,View.MeasureSpec.EXACTLY));root.layout(0,0,width,height);}}
    private void snapshot(View root,String name)throws Exception{String directory=System.getenv("LUMEN_NAMED_LIBRARY_SCREENSHOTS");if(directory==null)return;File path=new File(directory,name+".png");path.getParentFile().mkdirs();Bitmap image=Bitmap.createBitmap(root.getWidth(),root.getHeight(),Bitmap.Config.ARGB_8888);root.draw(new Canvas(image));try(FileOutputStream output=new FileOutputStream(path)){image.compress(Bitmap.CompressFormat.PNG,100,output);}image.recycle();}
    @Test public void officialReadOnlySelectorKeepsLongLibraryNamesReachable()throws Exception{
        try(ActivityController<Activity> life=Robolectric.buildActivity(Activity.class).setup()){
            JSONArray items=new JSONArray("[{\"id\":1,\"name\":\"家庭电影收藏\",\"kind\":\"movie\",\"count\":128},{\"id\":2,\"name\":\"VR电影与旅行纪录片\",\"kind\":\"vr\",\"count\":36}]");
            long[] selected={0};View view=MediaLibrarySelector.create(life.get(),items,2,(id,name,kind)->selected[0]=id,()->{});life.get().setContentView(view);layout(view,320,64);
            Chip vr=view.findViewWithTag("mediaLibrary:2");assertTrue(vr.isChecked());assertTrue(vr.getHeight()>=48);assertTrue(vr.getContentDescription().toString().contains("电脑端管理"));
            ((Chip)view.findViewWithTag("mediaLibrary:1")).performClick();assertEquals(1,selected[0]);assertFalse(vr.isChecked());assertTrue(((Chip)view.findViewWithTag("mediaLibrary:1")).isChecked());snapshot(view,"android-library-selector-320");
        }
    }
    @Test public void selectingLibraryScopesBrowseFacetsDetailPlaybackAndConfigurationRestore()throws Exception{
        List<String> requests=new CopyOnWriteArrayList<>();
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create().start().resume().visible()){
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){
                requests.add(request.getMethod()+" "+request.getPath());String body="{\"items\":[],\"total\":0}";
                if(request.getPath().startsWith("/api/media-libraries"))body="{\"items\":[{\"id\":1,\"name\":\"家庭电影\",\"kind\":\"movie\",\"count\":1},{\"id\":2,\"name\":\"VR收藏\",\"kind\":\"vr\",\"count\":1}]}";
                else if(request.getPath().startsWith("/api/filters"))body="{\"tags\":[],\"actors\":[],\"years\":[2024]}";
                else if(request.getPath().startsWith("/api/works/7"))body="{\"id\":7,\"title\":\"山海纪行\",\"kind\":\"vr\",\"file_count\":1,\"resume_file_id\":70,\"files\":[{\"id\":70,\"name\":\"journey.mp4\"}],\"tags\":[],\"actors\":[]}";
                else if(request.getPath().startsWith("/api/works?"))body="{\"total\":1,\"items\":[{\"id\":7,\"title\":\"山海纪行\",\"kind\":\"vr\",\"file_count\":1}]}";
                return new MockResponse().setHeader("Content-Type","application/json").setBody(body);
            }});server.start();MainActivity activity=life.get();set(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));set(activity,"mediaLibrariesSupported",true);set(activity,"mainPage","library");call(activity,"showLibrary",new Class<?>[0]);
            waitFor(()->activity.findViewById(android.R.id.content).findViewWithTag("mediaLibrary:2")!=null);activity.findViewById(android.R.id.content).findViewWithTag("mediaLibrary:2").performClick();
            waitFor(()->requests.stream().anyMatch(path->path.contains("/api/works?")&&path.contains("media_library_id=2")&&path.contains("kind=vr")));
            assertEquals(2L,get(activity,"mediaLibraryId"));String path=(String)call(activity,"listPath",new Class<?>[0]);assertTrue(path.contains("media_library_id=2"));
            Configuration config=new Configuration(activity.getResources().getConfiguration());config.fontScale=1.5f;activity.onConfigurationChanged(config);assertEquals(2L,get(activity,"mediaLibraryId"));
            waitFor(()->activity.findViewById(android.R.id.content).findViewWithTag("mediaLibrary:2")!=null);View root=(View)get(activity,"root");layout(root,393,852);snapshot(root,"android-named-library-393");
            call(activity,"showFilters",new Class<?>[0]);waitFor(()->requests.stream().anyMatch(url->url.contains("/api/filters?")&&url.contains("media_library_id=2")));((LibraryFilterBottomSheet)org.robolectric.shadows.ShadowDialog.getLatestDialog()).dismiss();
            activity.openDetail(7);waitFor(()->requests.stream().anyMatch(url->url.equals("GET /api/works/7?media_library_id=2")));waitFor(()->activity.findViewById(android.R.id.content).findViewWithTag("detailPersonalActions")!=null);
            Intent intent=(Intent)call(activity,"playerIntent",new Class<?>[]{long.class,boolean.class},70L,false);assertEquals(2,intent.getLongExtra("media_library_id",0));assertTrue(intent.getStringExtra("browse_path").contains("media_library_id=2"));
            assertTrue(requests.stream().allMatch(url->url.startsWith("GET ")));
        }
    }
    @Test public void manuallyMixingLibrariesKeepsThePhoneQueuePlayable()throws Exception{
        try(ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity activity=life.get();activity.getSharedPreferences("queue",0).edit().clear().commit();
            set(activity,"mediaLibraryId",1L);call(activity,"addToPhoneQueue",new Class<?>[]{long.class},7L);
            assertEquals(1,activity.getSharedPreferences("queue",0).getLong("media_library_id",0));
            set(activity,"mediaLibraryId",2L);call(activity,"addToPhoneQueue",new Class<?>[]{long.class},8L);
            assertEquals(0,activity.getSharedPreferences("queue",0).getLong("media_library_id",-1));
            assertEquals(2,new JSONArray(activity.getSharedPreferences("queue",0).getString("ids","[]")).length());
        }
    }
}
