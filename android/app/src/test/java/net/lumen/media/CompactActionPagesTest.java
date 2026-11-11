package net.lumen.media;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Color;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import com.google.android.material.button.MaterialButton;
import com.google.android.material.card.MaterialCardView;
import com.google.android.material.chip.ChipGroup;
import com.google.android.material.materialswitch.MaterialSwitch;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.shadows.ShadowAlertDialog;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w320dp-h800dp-mdpi")
public class CompactActionPagesTest {
    private void call(Object target,String name)throws Exception{Method method=target.getClass().getDeclaredMethod(name);method.setAccessible(true);method.invoke(target);}
    private Object field(Object target,String name)throws Exception{Field field=target.getClass().getDeclaredField(name);field.setAccessible(true);return field.get(target);}
    private void field(Object target,String name,Object value)throws Exception{Field field=target.getClass().getDeclaredField(name);field.setAccessible(true);field.set(target,value);}
    private void working(UpdateActivity target,boolean value)throws Exception{Method method=UpdateActivity.class.getDeclaredMethod("state",boolean.class);method.setAccessible(true);method.invoke(target,value);}
    private void waitFor(BooleanSupplier condition)throws Exception{long end=System.currentTimeMillis()+5000;while(!condition.getAsBoolean()&&System.currentTimeMillis()<end){Thread.sleep(10);shadowOf(Looper.getMainLooper()).idle();}assertTrue(condition.getAsBoolean());}
    private void layout(View view){for(int pass=0;pass<3;pass++){view.measure(View.MeasureSpec.makeMeasureSpec(320,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(800,View.MeasureSpec.EXACTLY));view.layout(0,0,320,800);}}
    private void layoutDialog(View view){for(int pass=0;pass<3;pass++){view.measure(View.MeasureSpec.makeMeasureSpec(320,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(752,View.MeasureSpec.AT_MOST));view.layout(0,0,320,view.getMeasuredHeight());}}
    private View root(Activity activity){return ((ViewGroup)activity.findViewById(android.R.id.content)).getChildAt(0);}
    private void target(View child){assertTrue(child instanceof MaterialButton);assertTrue("A real action retains a 48dp touch height",child.getHeight()>=48);assertTrue("A real action retains a 48dp touch width",child.getWidth()>=48);assertTrue(child.getLeft()>=0&&child.getRight()<=((View)child.getParent()).getWidth());}
    private List<View> visible(ViewGroup group){List<View> result=new ArrayList<>();for(int index=0;index<group.getChildCount();index++)if(group.getChildAt(index).getVisibility()==View.VISIBLE)result.add(group.getChildAt(index));return result;}
    private void assertActionGroup(LinearLayout group){
        assertNotNull(group);List<View> actions=visible(group);assertFalse("At least the applicable action remains available",actions.isEmpty());
        for(int index=0;index<actions.size();index++){
            View child=actions.get(index);target(child);
            if(index>0){View before=actions.get(index-1);assertEquals("Spacing belongs between visible actions",12,group.getOrientation()==LinearLayout.VERTICAL?child.getTop()-before.getBottom():child.getLeft()-before.getRight());}
        }
    }
    @Test public void remoteAndUpdateActionsUseRealQuickControlsAndContextualMaterialActions()throws Exception{
        try(ActivityController<RemoteActivity> lifecycle=Robolectric.buildActivity(RemoteActivity.class).create()){
            RemoteActivity activity=lifecycle.get();call(activity,"buildUi");View root=root(activity);layout(root);
            assertTrue(root.findViewWithTag("remoteCurrentMedia") instanceof MaterialCardView);LinearLayout media=root.findViewWithTag("remoteMediaActions");assertEquals(3,media.getChildCount());assertEquals(LinearLayout.HORIZONTAL,media.getOrientation());assertActionGroup(media);
            for(View action:visible(media)){MaterialButton quick=(MaterialButton)action;assertNotNull(quick.getIcon());assertEquals(MaterialButton.ICON_GRAVITY_TOP,quick.getIconGravity());assertEquals("Quick actions use a transparent container",0,Color.alpha(quick.getBackgroundTintList().getDefaultColor()));}
            LinearLayout power=root.findViewWithTag("remotePowerActions");assertTrue(root.findViewWithTag("remotePowerCard") instanceof MaterialCardView);target(power.getChildAt(0));assertFalse(power.getChildAt(0).isEnabled());assertEquals(View.GONE,power.getChildAt(1).getVisibility());assertEquals(12,((LinearLayout.LayoutParams)power.getLayoutParams()).topMargin);
        }
        try(ActivityController<UpdateActivity> lifecycle=Robolectric.buildActivity(UpdateActivity.class)){
            UpdateActivity activity=lifecycle.get();activity.fetcher=(url,limit)->{throw new java.io.IOException("offline fixture");};lifecycle.create();waitFor(()->{try{return ((Button)field(activity,"check")).isEnabled();}catch(Exception error){return false;}});View root=root(activity);layout(root);LinearLayout actions=root.findViewWithTag("updateActions");assertEquals(4,actions.getChildCount());assertEquals(1,visible(actions).size());assertActionGroup(actions);assertTrue(root.findViewWithTag("updateInformation") instanceof MaterialCardView);
            assertFalse(((Button)field(activity,"download")).isEnabled());assertFalse(((Button)field(activity,"install")).isEnabled());assertFalse(((Button)field(activity,"cancel")).isEnabled());assertEquals(View.GONE,((Button)field(activity,"download")).getVisibility());
            field(activity,"candidate",new GitHubUpdates.Candidate("99.0.0",999,GitHubUpdates.TARGET+"Lumen-android-debug.apk",5,"a".repeat(64),"测试版本说明","fixture"));working(activity,false);layout(root);assertEquals(2,visible(actions).size());assertActionGroup(actions);assertTrue(((Button)field(activity,"download")).isEnabled());assertEquals(View.GONE,((Button)field(activity,"install")).getVisibility());
            working(activity,true);layout(root);assertEquals(1,visible(actions).size());assertActionGroup(actions);assertTrue(((Button)field(activity,"cancel")).isEnabled());assertEquals(View.GONE,((Button)field(activity,"download")).getVisibility());assertEquals(16,((LinearLayout.LayoutParams)actions.getLayoutParams()).topMargin);
        }
    }
    private int settingRows(ViewGroup root){
        int count=0;for(int index=0;index<root.getChildCount();index++){View child=root.getChildAt(index);if(child instanceof PlayerChrome.SettingRow){PlayerChrome.SettingRow row=(PlayerChrome.SettingRow)child;target(row.action);assertTrue(row.getHeight()>=56);assertTrue(row.action.getHeight()<=row.getHeight());count++;}else if(child instanceof ViewGroup)count+=settingRows((ViewGroup)child);}return count;
    }
    @Test public void playerSettingsUseDividedGroupsAndTabFramesWithoutShrinkingTransport()throws Exception{
        try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=lifecycle.get();Method build=PlayerActivity.class.getDeclaredMethod("buildPlayerUi",android.content.SharedPreferences.class);build.setAccessible(true);build.invoke(activity,activity.getSharedPreferences("playback",0));layout(root(activity));call(activity,"playbackSettings");AlertDialog settings=ShadowAlertDialog.getLatestAlertDialog();try{
                View decor=settings.getWindow().getDecorView();layoutDialog(decor);LinearLayout groups=decor.findViewWithTag("playerSettingActions");assertTrue("Common settings are divided into functional cards",groups.getChildCount()>=3);assertTrue(settingRows(groups)>=8);MaterialSwitch autoNext=decor.findViewWithTag("playerAutoNextSwitch");assertNotNull(autoNext);boolean before=autoNext.isChecked();autoNext.performClick();assertEquals(!before,activity.getSharedPreferences("player",0).getBoolean("auto_next",before));
                LinearLayout tabs=decor.findViewWithTag("playerSettingTabs");assertEquals(3,tabs.getChildCount());int lastRight=0;for(int index=0;index<3;index++){assertTrue(tabs.getChildAt(index) instanceof FrameLayout);FrameLayout frame=(FrameLayout)tabs.getChildAt(index);target(frame.getChildAt(0));assertTrue(frame.getLeft()>=lastRight);lastRight=frame.getRight();}assertTrue(((Button)((FrameLayout)tabs.getChildAt(0)).getChildAt(0)).isSelected());
                ((Button)((FrameLayout)tabs.getChildAt(1)).getChildAt(0)).performClick();layoutDialog(decor);assertFalse(((Button)((FrameLayout)tabs.getChildAt(0)).getChildAt(0)).isSelected());assertTrue(((Button)((FrameLayout)tabs.getChildAt(1)).getChildAt(0)).isSelected());assertNotNull(decor.findViewWithTag("playerSetting:实时美颜"));assertEquals(4,settingRows(groups));
            }finally{settings.dismiss();}
            call(activity,"vrSettings");AlertDialog vr=ShadowAlertDialog.getLatestAlertDialog();try{layoutDialog(vr.getWindow().getDecorView());LinearLayout choices=vr.getWindow().getDecorView().findViewWithTag("playerVrSettings");int buttons=0;for(int index=0;index<choices.getChildCount();index++)if(choices.getChildAt(index) instanceof Button&&!(choices.getChildAt(index) instanceof android.widget.CompoundButton)){target(choices.getChildAt(index));buttons++;}assertTrue(buttons>=2);}finally{vr.dismiss();}
            ViewGroup page=(ViewGroup)root(activity);ViewGroup transport=page.findViewWithTag("playbackTransport");assertNotNull(transport);assertEquals("Portrait uses the actual central playback control",View.GONE,transport.getVisibility());ViewGroup center=page.findViewWithTag("playerCenterTransport");assertEquals(View.VISIBLE,center.getVisibility());assertEquals(1,center.getChildCount());assertTrue(center.getChildAt(0) instanceof PlaybackIconButton);assertTrue("Portrait play remains a full 64dp target",center.getChildAt(0).getHeight()>=64);
            for(int pass=0;pass<3;pass++){page.measure(View.MeasureSpec.makeMeasureSpec(800,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(360,View.MeasureSpec.EXACTLY));page.layout(0,0,800,360);}assertEquals(View.VISIBLE,transport.getVisibility());assertEquals(5,transport.getChildCount());for(int index=0;index<transport.getChildCount();index++){View action=transport.getChildAt(index);assertEquals(View.VISIBLE,action.getVisibility());assertTrue(action instanceof PlaybackIconButton);assertTrue("Landscape transport retains its full touch target",action.getHeight()>=48&&action.getWidth()>=48);assertTrue(action.getLeft()>=0&&action.getRight()<=transport.getWidth());}
        }
    }
    @Test public void taskPagingKeepsReadOnlyRequestDisabledStateAndTwelveDpGap()throws Exception{
        try(MockWebServer server=new MockWebServer();ActivityController<Activity> lifecycle=Robolectric.buildActivity(Activity.class).setup()){
            server.enqueue(new MockResponse().setBody("{\"items\":[],\"total\":0}"));server.start();Api api=new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456"));AlertDialog dialog=TaskCenter.show(lifecycle.get(),api);
            try{View decor=dialog.getWindow().getDecorView();waitFor(()->decor.findViewWithTag("refreshComputerTasks").isEnabled());layoutDialog(decor);LinearLayout paging=decor.findViewWithTag("computerTaskPaging");assertEquals(2,paging.getChildCount());assertActionGroup(paging);assertFalse(paging.getChildAt(0).isEnabled());assertFalse(paging.getChildAt(1).isEnabled());assertEquals(16,((LinearLayout.LayoutParams)paging.getLayoutParams()).topMargin);ChipGroup category=decor.findViewWithTag("computerTaskCategory");assertEquals(5,category.getChildCount());assertTrue(category.isSingleSelection());RecordedRequest request=server.takeRequest(2,TimeUnit.SECONDS);assertNotNull(request);assertEquals("GET",request.getMethod());assertTrue(request.getPath().contains("state=all"));assertTrue(request.getPath().contains("offset=0"));assertEquals("Bearer abcdefghijklmnopqrstuvwxyz123456",request.getHeader("Authorization"));}
            finally{dialog.dismiss();}
        }
    }
}
