package net.lumen.media;

import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.os.Looper;
import android.view.View;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.json.JSONObject;
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
public class SeriesSelectionTest {
    private void set(MainActivity activity,String key,Object value)throws Exception{Field field=MainActivity.class.getDeclaredField(key);field.setAccessible(true);field.set(activity,value);}
    private void render(MainActivity activity,JSONObject work)throws Exception{Method method=MainActivity.class.getDeclaredMethod("renderDetail",JSONObject.class);method.setAccessible(true);method.invoke(activity,work);Shadows.shadowOf(Looper.getMainLooper()).idle();}
    private JSONObject series()throws Exception{return new JSONObject("{\"id\":9,\"title\":\"山海记\",\"kind\":\"series\",\"resume_file_id\":101,\"files\":[{\"id\":100,\"name\":\"特别篇.mp4\",\"season\":0,\"episode\":1,\"duration\":1800},{\"id\":101,\"name\":\"第一集.mp4\",\"season\":1,\"episode\":1,\"duration\":1800},{\"id\":102,\"name\":\"第二集.mp4\",\"season\":1,\"episode\":2,\"duration\":1800},{\"id\":201,\"name\":\"第一集.mp4\",\"season\":2,\"episode\":1,\"duration\":1800}]}");}
    private void connect(MainActivity activity,MockWebServer server)throws Exception{set(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));activity.mediaLibraryId=6;activity.mediaLibraryName="家庭剧集";}
    private View content(MainActivity activity){return activity.findViewById(android.R.id.content);}
    private SearchDropdown selector(MainActivity activity){return content(activity).findViewWithTag("detailSeasonSelector");}
    private void choose(MainActivity activity,int index){
        View root=content(activity);root.measure(View.MeasureSpec.makeMeasureSpec(393,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(852,View.MeasureSpec.EXACTLY));root.layout(0,0,393,852);
        SearchDropdown field=selector(activity);field.requestFocus();field.requestRectangleOnScreen(new android.graphics.Rect(0,0,field.getWidth(),field.getHeight()),true);
        // Deliver the exposed dropdown's item event; Robolectric does not drive its popup keyboard selection.
        field.setText(field.getAdapter().getItem(index).toString(),false);field.getOnItemClickListener().onItemClick(null,null,index,index);Shadows.shadowOf(Looper.getMainLooper()).idle();
    }
    private int rowVisibility(MainActivity activity,long file){return ((View)content(activity).findViewWithTag("episode:"+file).getParent()).getVisibility();}
    private void snapshot(View view,String name)throws Exception{
        String directory=System.getenv("LUMEN_EPISODE_SHUFFLE_SCREENSHOTS");if(directory==null)return;
        view.measure(View.MeasureSpec.makeMeasureSpec(393,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(852,View.MeasureSpec.EXACTLY));view.layout(0,0,393,852);
        File path=new File(directory,name+".png");path.getParentFile().mkdirs();Bitmap image=Bitmap.createBitmap(393,852,Bitmap.Config.ARGB_8888);view.draw(new Canvas(image));try(FileOutputStream output=new FileOutputStream(path)){image.compress(Bitmap.CompressFormat.PNG,100,output);}image.recycle();
    }
    @Test public void seasonChoiceSurvivesConfigurationAndDetailRefreshAndLaunchesTheExactEpisode()throws Exception{
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).setup()){
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){return new MockResponse().setBody("{\"items\":[],\"total\":0}");}});server.start();MainActivity page=life.get();connect(page,server);JSONObject work=series();render(page,work);
            assertNotNull(selector(page));assertEquals(4,selector(page).getAdapter().getCount());choose(page,3);
            assertEquals(View.VISIBLE,rowVisibility(page,201));assertEquals(View.GONE,rowVisibility(page,101));assertEquals(View.GONE,rowVisibility(page,100));
            page.onConfigurationChanged(new Configuration(page.getResources().getConfiguration()));Shadows.shadowOf(Looper.getMainLooper()).idle();
            assertEquals("第 2 季",selector(page).getText().toString());assertEquals(View.GONE,rowVisibility(page,101));
            render(page,work.put("favorite",1));assertEquals("第 2 季",selector(page).getText().toString());snapshot(content(page),"series-season-selection-393");
            content(page).findViewWithTag("episode:201").performClick();Intent intent=Shadows.shadowOf(page).getNextStartedActivity();
            assertEquals(9,intent.getLongExtra("work_id",0));assertEquals(201,intent.getLongExtra("file_id",0));assertEquals(6,intent.getLongExtra("media_library_id",0));
        }
    }
    @Test public void specialsAndIndependentLibraryChoicesFilterOnlyTheirOwnRows()throws Exception{
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).setup()){
            server.start();MainActivity page=life.get();connect(page,server);JSONObject work=series();render(page,work);choose(page,1);
            assertEquals(View.VISIBLE,rowVisibility(page,100));assertEquals(View.GONE,rowVisibility(page,101));
            page.mediaLibraryId=7;render(page,work);assertEquals("全部季",selector(page).getText().toString());assertEquals(View.VISIBLE,rowVisibility(page,101));
            page.mediaLibraryId=6;render(page,work);assertEquals("特别篇",selector(page).getText().toString());assertEquals(View.GONE,rowVisibility(page,201));
        }
    }
    @Test public void displayedEpisodeKeepsItsWorkIdWhileAnotherDetailRequestIsPending()throws Exception{
        CountDownLatch requested=new CountDownLatch(1),release=new CountDownLatch(1);
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).setup()){
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request)throws InterruptedException{if(request.getPath().startsWith("/api/works/99")){requested.countDown();release.await(6,TimeUnit.SECONDS);}return new MockResponse().setBody("{\"items\":[],\"total\":0}");}});server.start();MainActivity page=life.get();connect(page,server);render(page,series());
            try{
                View selected=content(page).findViewWithTag("episode:102");page.openDetail(99);assertTrue(requested.await(6,TimeUnit.SECONDS));selected.performClick();
                Intent intent=Shadows.shadowOf(page).getNextStartedActivity();assertEquals(9,intent.getLongExtra("work_id",0));assertEquals(102,intent.getLongExtra("file_id",0));
            }finally{release.countDown();}
        }
    }
}
