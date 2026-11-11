package net.lumen.media;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
import com.google.android.material.chip.Chip;
import com.google.android.material.chip.ChipGroup;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w320dp-h800dp-mdpi")
public class TaskCenterTest {
    private void waitUntil(BooleanSupplier ready)throws Exception{
        long deadline=System.currentTimeMillis()+5000;
        while(!ready.getAsBoolean()&&System.currentTimeMillis()<deadline){Thread.sleep(15);shadowOf(Looper.getMainLooper()).idle();}
        assertTrue(ready.getAsBoolean());
    }
    private View find(View view,String label){
        if(view instanceof TextView&&((TextView)view).getText().toString().contains(label))return view;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){View result=find(((ViewGroup)view).getChildAt(i),label);if(result!=null)return result;}
        return null;
    }
    private Api api(MockWebServer server)throws Exception{return new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456"));}
    private MockResponse response(int start,int count,int total)throws Exception{
        JSONArray items=new JSONArray();
        for(int i=start;i<start+count;i++)items.put(new JSONObject().put("id","job-"+i).put("label","自动入库")
            .put("status_label","待确认").put("work_title","影片 "+i).put("reason","影片匹配需要确认，请在电脑选择正确的资料。")
            .put("updated","2026-11-04T03:00:00+00:00"));
        return new MockResponse().setBody(new JSONObject().put("items",items).put("total",total).toString());
    }
    @Test public void computerTasksShowReadOnlyScopeAndPageWithoutLosingDialog()throws Exception{
        try(MockWebServer server=new MockWebServer();ActivityController<Activity> lifecycle=Robolectric.buildActivity(Activity.class).setup()){
            server.enqueue(response(0,30,31));server.enqueue(response(30,1,31));server.enqueue(response(0,1,1));server.start();
            AlertDialog dialog=TaskCenter.show(lifecycle.get(),api(server),42);View root=dialog.getWindow().getDecorView();
            try{
                waitUntil(()->find(root,"影片 0")!=null);
                RecordedRequest first=server.takeRequest(2,TimeUnit.SECONDS);
                assertNotNull(first);assertEquals("Bearer abcdefghijklmnopqrstuvwxyz123456",first.getHeader("Authorization"));
                assertTrue(first.getPath().contains("work_id=42"));assertTrue(first.getPath().contains("state=all"));
                assertNotNull(find(root,"关联此影片的电脑任务"));assertNotNull(find(root,"选择正确的资料"));
                root.findViewWithTag("nextTaskPage").performClick();waitUntil(()->find(root,"第 31–31 项")!=null);
                assertTrue(server.takeRequest(2,TimeUnit.SECONDS).getPath().contains("offset=30"));assertNull(find(root,"影片 0"));
                ChipGroup category=root.findViewWithTag("computerTaskCategory");assertEquals(5,category.getChildCount());assertTrue(category.isSingleSelection());
                Chip pending=root.findViewWithTag("taskCategory:pending");assertNotNull(pending);assertTrue(pending.isEnabled());pending.performClick();shadowOf(Looper.getMainLooper()).idle();
                waitUntil(()->find(root,"第 1–1 项")!=null);
                String path=server.takeRequest(2,TimeUnit.SECONDS).getPath();assertTrue(path.contains("state=pending"));assertTrue(path.contains("offset=0"));
                assertTrue(pending.isChecked());assertFalse(root.findViewWithTag("previousTaskPage").isEnabled());assertTrue(dialog.isShowing());
            }finally{dialog.dismiss();}
        }
    }
    @Test public void failedRequestCanRetryAndOldServerHasExplicitUpdateMessage()throws Exception{
        try(MockWebServer server=new MockWebServer();ActivityController<Activity> lifecycle=Robolectric.buildActivity(Activity.class).setup()){
            server.enqueue(new MockResponse().setResponseCode(500));server.enqueue(response(0,1,1));server.enqueue(new MockResponse().setResponseCode(404));server.start();
            AlertDialog dialog=TaskCenter.show(lifecycle.get(),api(server));View root=dialog.getWindow().getDecorView();
            try{
                waitUntil(()->find(root,"读取失败")!=null);assertTrue(root.findViewWithTag("refreshComputerTasks").isEnabled());
                root.findViewWithTag("refreshComputerTasks").performClick();waitUntil(()->find(root,"影片 0")!=null);
                root.findViewWithTag("refreshComputerTasks").performClick();waitUntil(()->find(root,"电脑端暂不支持任务列表，请更新电脑端")!=null);
            }finally{dialog.dismiss();}
        }
    }
    @Test public void dismissIgnoresAnInFlightResponse()throws Exception{
        try(MockWebServer server=new MockWebServer();ActivityController<Activity> lifecycle=Robolectric.buildActivity(Activity.class).setup()){
            server.enqueue(response(0,1,1).setBodyDelay(300,TimeUnit.MILLISECONDS));server.start();
            AlertDialog dialog=TaskCenter.show(lifecycle.get(),api(server));View root=dialog.getWindow().getDecorView();
            assertNotNull(server.takeRequest(2,TimeUnit.SECONDS));dialog.dismiss();
            Thread.sleep(400);shadowOf(Looper.getMainLooper()).idle();
            assertFalse(dialog.isShowing());assertNull(find(root,"影片 0"));
        }
    }
}
