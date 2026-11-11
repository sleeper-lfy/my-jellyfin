package net.lumen.media;

import android.app.AlertDialog;
import android.content.res.Configuration;
import android.graphics.Rect;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.TextView;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.shadows.ShadowAlertDialog;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w393dp-h852dp-mdpi")
public class PlaybackNoticeUiTest {
    private Object get(Object target,String name)throws Exception{Field field=target.getClass().getDeclaredField(name);field.setAccessible(true);return field.get(target);}
    private void set(Object target,String name,Object value)throws Exception{Field field=target.getClass().getDeclaredField(name);field.setAccessible(true);field.set(target,value);}
    private void call(Object target,String name)throws Exception{Method method=target.getClass().getDeclaredMethod(name);method.setAccessible(true);method.invoke(target);}
    private FrameLayout build(PlayerActivity activity)throws Exception{Method build=PlayerActivity.class.getDeclaredMethod("buildPlayerUi",android.content.SharedPreferences.class);build.setAccessible(true);build.invoke(activity,activity.getSharedPreferences("playback",0));return (FrameLayout)get(activity,"root");}
    private void layout(View root,int width,int height){for(int pass=0;pass<3;pass++){root.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(height,View.MeasureSpec.EXACTLY));root.layout(0,0,width,height);}}
    @SuppressWarnings({"unchecked","rawtypes"}) private void notice(PlayerActivity activity,String text,String name)throws Exception{Class<? extends Enum> type=(Class<? extends Enum>)Class.forName("net.lumen.media.PlayerActivity$Notice");Method method=PlayerActivity.class.getDeclaredMethod("setPlaybackNotice",String.class,type);method.setAccessible(true);method.invoke(activity,text,Enum.valueOf(type,name));}
    private Rect bounds(ViewGroup root,View child){Rect rect=new Rect(0,0,child.getWidth(),child.getHeight());root.offsetDescendantRectToMyCoords(child,rect);return rect;}
    @Test public void finalDecodeFailureIsVisibleAfterLayoutAndOffersTheCompleteMessage()throws Exception{
        try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=lifecycle.get();FrameLayout root=build(activity);layout(root,393,852);call(activity,"showFinalPlaybackError");layout(root,393,852);
            TextView status=(TextView)get(activity,"status");assertEquals(View.VISIBLE,status.getVisibility());assertEquals(View.VISIBLE,((View)get(activity,"bottomBar")).getVisibility());assertTrue(status.getText().toString().contains("播放失败"));assertTrue(status.getText().toString().contains("解码模式"));assertTrue(status.getHeight()>=48);assertEquals(View.GONE,((View)get(activity,"gestureHint")).getVisibility());assertEquals(true,get(activity,"controlsVisible"));
            notice(activity,"原画直传 · 播放进度同步至电脑","NONE");assertEquals(View.VISIBLE,status.getVisibility());assertTrue(status.getText().toString().contains("播放失败"));
            status.performClick();AlertDialog details=ShadowAlertDialog.getLatestAlertDialog();assertEquals("播放状态",org.robolectric.Shadows.shadowOf(details).getTitle());assertTrue(org.robolectric.Shadows.shadowOf(details).getMessage().toString().contains("解码模式"));details.dismiss();
        }
    }
    @Test public void loadingAndWarningsReserveSpaceAndNormalPlaybackHasNoStatusCard()throws Exception{
        for(float font:new float[]{1f,2f})try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=lifecycle.get();Configuration config=new Configuration(activity.getResources().getConfiguration());config.fontScale=font;activity.getResources().updateConfiguration(config,activity.getResources().getDisplayMetrics());FrameLayout root=build(activity);notice(activity,"正在连接视频…","LOADING");
            for(int[] size:new int[][]{{393,852},{852,393},{640,280},{640,200}}){layout(root,size[0],size[1]);TextView status=(TextView)get(activity,"status");assertEquals(View.VISIBLE,status.getVisibility());Rect top=bounds(root,(View)get(activity,"topBar")),bottom=bounds(root,(View)get(activity,"bottomBar")),feedback=bounds(root,status);assertTrue("feedback must not cover the header",top.bottom<=bottom.top);assertTrue(feedback.bottom<=size[1]);assertTrue(feedback.left>=0);assertTrue(feedback.right<=size[0]);assertTrue(status.getHeight()>=48);if(size[1]<=280){View pause=root.findViewWithTag("playerNoticePause");assertEquals(View.VISIBLE,pause.getVisibility());assertTrue(pause.getHeight()>=48);}}
            notice(activity,"自动解码","NONE");layout(root,393,852);assertEquals(View.GONE,((View)get(activity,"status")).getVisibility());
            notice(activity,"观看记录暂未连接","WARNING");layout(root,393,852);assertEquals(View.VISIBLE,((View)get(activity,"status")).getVisibility());
        }
    }
    @Test public void portraitIdentityNamesFansAndOtherAndKeepsSeriesEpisodeIdentity()throws Exception{
        try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=lifecycle.get();build(activity);set(activity,"file",new JSONObject().put("season",2).put("episode",3));
            for(String[] item:new String[][]{{"fans","Fans 视频"},{"other","其他视频"},{"series","剧集"}}){set(activity,"work",new JSONObject().put("title","示例").put("kind",item[0]));call(activity,"updatePortraitInfo");String text=((TextView)get(activity,"portraitMeta")).getText().toString();assertTrue(text.startsWith(item[1]));if(item[0].equals("series"))assertTrue(text.contains("S2 E3"));}
        }
    }
}
