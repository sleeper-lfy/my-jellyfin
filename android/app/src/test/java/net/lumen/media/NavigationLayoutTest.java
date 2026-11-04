package net.lumen.media;

import android.app.AlertDialog;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.os.Bundle;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.ScrollView;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.GraphicsMode;
import org.robolectric.android.controller.ActivityController;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.RecordedRequest;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w360dp-h800dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
public class NavigationLayoutTest {
    private Object read(Object target,String name)throws Exception{Field field=target.getClass().getDeclaredField(name);field.setAccessible(true);return field.get(target);}
    private void set(Object target,String name,Object value)throws Exception{Field field=target.getClass().getDeclaredField(name);field.setAccessible(true);field.set(target,value);}
    private Object call(Object target,String name)throws Exception{Method method=target.getClass().getDeclaredMethod(name);method.setAccessible(true);return method.invoke(target);}
    private View find(View root,String label){if(root instanceof TextView&&label.equals(((TextView)root).getText().toString()))return root;if(root instanceof ViewGroup)for(int i=0;i<((ViewGroup)root).getChildCount();i++){View found=find(((ViewGroup)root).getChildAt(i),label);if(found!=null)return found;}return null;}
    private MockWebServer server()throws Exception{
        MockWebServer server=new MockWebServer();server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){return new MockResponse().setBody("{\"items\":[],\"total\":0,\"tags\":[],\"actors\":[],\"years\":[]}");}});server.start();return server;
    }
    private void connect(MainActivity activity,MockWebServer server)throws Exception{set(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));}
    private void layout(View root,int width,int height){for(int i=0;i<3;i++){root.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(height,View.MeasureSpec.EXACTLY));root.layout(0,0,width,height);}}
    private void fits(TextView view){assertNotNull(view);assertNotNull(view.getLayout());assertTrue(view.getText()+" text="+view.getLayout().getHeight()+" box="+view.getHeight(),view.getLayout().getHeight()<=view.getHeight()-view.getCompoundPaddingTop()-view.getCompoundPaddingBottom()+1);}
    private void snapshot(View root,String filename)throws Exception{
        String folder=System.getenv("LUMEN_UI_SCREENSHOTS");if(folder==null||folder.isEmpty())return;File target=new File(folder,filename);target.getParentFile().mkdirs();Bitmap image=Bitmap.createBitmap(root.getWidth(),root.getHeight(),Bitmap.Config.ARGB_8888);root.draw(new Canvas(image));try(FileOutputStream stream=new FileOutputStream(target)){image.compress(Bitmap.CompressFormat.PNG,100,stream);}image.recycle();
    }
    @Test public void fourPrimaryDestinationsExposeWatchlistAndKeepScopeOnRestore()throws Exception{
        try(MockWebServer server=server();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            MainActivity activity=lifecycle.get();connect(activity,server);call(activity,"showLibrary");View root=(View)read(activity,"root");layout(root,360,800);
            LinearLayout nav=root.findViewWithTag("primaryNavigation");assertEquals(4,nav.getChildCount());assertNotNull(root.findViewWithTag("nav:library"));
            root.findViewWithTag("nav:mine").performClick();root=(View)read(activity,"root");layout(root,360,800);snapshot(root,"ui-android-mine.png");assertNotNull(find(root,"想看"));assertNotNull(find(root,"电脑任务中心"));assertNotNull(find(root,"手机播放队列"));
            find(root,"想看").performClick();assertTrue(((String)call(activity,"listPath")).contains("watchlist=true"));assertEquals("mine",read(activity,"mainPage"));
            Bundle saved=(Bundle)call(activity,"browseState");Method restore=MainActivity.class.getDeclaredMethod("restoreBrowseState",Bundle.class);restore.setAccessible(true);restore.invoke(activity,saved);assertEquals(true,read(activity,"watchlistOnly"));
            root=(View)read(activity,"root");root.findViewWithTag("nav:library").performClick();assertTrue(((String)call(activity,"listPath")).contains("watchlist=false"));assertNotNull(((View)read(activity,"root")).findViewWithTag("libraryCategory"));
        }
    }
    @Test public void narrowScreensKeepBothYearsAndLongDetailTextReadable()throws Exception{
        for(int width:new int[]{320,360})for(float scale:new float[]{1f,1.5f}){
            RuntimeEnvironment.setQualifiers("w"+width+"dp-h800dp-mdpi");
            try(MockWebServer server=server();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
                MainActivity activity=lifecycle.get();Configuration cfg=new Configuration(activity.getResources().getConfiguration());cfg.fontScale=scale;activity.getResources().updateConfiguration(cfg,activity.getResources().getDisplayMetrics());connect(activity,server);set(activity,"kind","movie");call(activity,"showLibrary");call(activity,"showFilters");
                AlertDialog filters=org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog();View sheet=filters.getWindow().getDecorView();layout(sheet,width,752);
                TextView from=sheet.findViewWithTag("filterYearFrom"),to=sheet.findViewWithTag("filterYearTo");assertTrue(from.getWidth()>100);assertTrue(to.getWidth()>100);assertEquals(from.getWidth(),to.getWidth());
                if(width==360&&scale==1f)snapshot(sheet,"ui-android-filters-fixed.png");filters.dismiss();
                String actor="安娜玛丽亚·亚历山德拉";
                JSONObject work=new JSONObject().put("id",42).put("title","长标题示例 ABC-123").put("kind","movie").put("file_count",1).put("resume_file_id",10)
                    .put("files",new JSONArray().put(new JSONObject().put("id",10).put("name","ABC-123.2160p.HEVC.10bit.mp4")))
                    .put("resume",new JSONObject().put("position",2710).put("label","继续 ABC-123.2160p.HEVC.10bit.DTS-HD.MA5.1.mp4 · 45:10 · 剩余 1:24:50"))
                    .put("actors",new JSONArray().put(new JSONObject().put("name",actor).put("photo","/api/photo")));
                Method render=MainActivity.class.getDeclaredMethod("renderDetail",JSONObject.class);render.setAccessible(true);render.invoke(activity,work);View root=(View)read(activity,"root");layout(root,width,800);
                TextView play=root.findViewWithTag("detailPlay");assertEquals("继续播放",play.getText().toString());fits(play);fits(root.findViewWithTag("detailResumeInfo"));fits(root.findViewWithTag("actorName:"+actor));
                if(width==360&&scale==1.5f)snapshot(root,"ui-android-detail-large-font.png");
                root.findViewWithTag("detailMore").performClick();AlertDialog actions=org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog();View menu=actions.getWindow().getDecorView();assertNotNull(find(menu,"加入手机播放队列"));assertNotNull(find(menu,"从头播放"));assertNull(find(menu,"排序"));assertNull(find(menu,"切换连接"));actions.dismiss();
            }
        }
    }
    @Test public void appliedFiltersScrollWithMediaInsteadOfShrinkingViewport()throws Exception{
        try(MockWebServer server=server();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            MainActivity activity=lifecycle.get();connect(activity,server);set(activity,"kind","movie");set(activity,"tagFilter","一个很长的标签");set(activity,"actorFilter","演员名字");set(activity,"yearMinFilter","2000");set(activity,"yearMaxFilter","2026");set(activity,"tagsAllFilter","标签一,标签二");call(activity,"showLibrary");
            View root=(View)read(activity,"root");layout(root,320,640);View filters=root.findViewWithTag("activeFilters");View parent=filters;while(parent.getParent() instanceof View&&!(parent instanceof ScrollView))parent=(View)parent.getParent();assertSame(read(activity,"browseScroll"),parent);
            ViewGroup nav=root.findViewWithTag("primaryNavigation");assertTrue(nav.getBottom()<=640);assertTrue(((ScrollView)read(activity,"browseScroll")).getHeight()>300);snapshot(root,"ui-android-library-filtered.png");
        }
    }
    @Test public void phoneQueueCanReorderAndRemoveWithoutReopeningDialog()throws Exception{
        try(MockWebServer server=server();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            MainActivity activity=lifecycle.get();connect(activity,server);activity.getSharedPreferences("queue",0).edit().putString("ids","[11,22,33]").putInt("index",1).commit();call(activity,"queueEditor");
            long deadline=System.currentTimeMillis()+5000;AlertDialog dialog=null;
            while(System.currentTimeMillis()<deadline){Thread.sleep(15);org.robolectric.Shadows.shadowOf(android.os.Looper.getMainLooper()).idle();dialog=org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog();if(dialog!=null&&find(dialog.getWindow().getDecorView(),"下移")!=null)break;}
            assertNotNull(dialog);View page=dialog.getWindow().getDecorView();find(page,"下移").performClick();assertEquals("[11,33,22]",activity.getSharedPreferences("queue",0).getString("ids",""));assertEquals(2,activity.getSharedPreferences("queue",0).getInt("index",-1));
            find(page,"上移").performClick();assertEquals("[11,22,33]",activity.getSharedPreferences("queue",0).getString("ids",""));
            find(page,"移除").performClick();assertEquals("[11,33]",activity.getSharedPreferences("queue",0).getString("ids",""));assertSame(dialog,org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog());assertTrue(dialog.isShowing());dialog.dismiss();
        }
    }

}
