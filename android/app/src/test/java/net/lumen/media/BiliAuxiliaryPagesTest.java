package net.lumen.media;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Rect;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.Drawable;
import android.os.Looper;
import android.os.SystemClock;
import android.provider.Settings;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import androidx.core.content.ContextCompat;
import com.google.android.material.card.MaterialCardView;
import com.google.android.material.chip.Chip;
import com.google.android.material.chip.ChipGroup;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.GraphicsMode;
import org.robolectric.shadows.ShadowAlertDialog;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BooleanSupplier;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

/** Real native pages and requests, using fictional artwork and isolated server state. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w393dp-h852dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
public class BiliAuxiliaryPagesTest {
    private static final String TOKEN="abcdefghijklmnopqrstuvwxyz123456";
    private Object get(Object target,String name)throws Exception{Field field=target.getClass().getDeclaredField(name);field.setAccessible(true);return field.get(target);}
    private void set(Object target,String name,Object value)throws Exception{Field field=target.getClass().getDeclaredField(name);field.setAccessible(true);field.set(target,value);}
    private void call(Object target,String name)throws Exception{Method method=target.getClass().getDeclaredMethod(name);method.setAccessible(true);method.invoke(target);}
    private void working(UpdateActivity target,boolean value)throws Exception{Method method=UpdateActivity.class.getDeclaredMethod("state",boolean.class);method.setAccessible(true);method.invoke(target,value);}
    private void waitFor(BooleanSupplier ready)throws Exception{long end=System.currentTimeMillis()+6000;while(!ready.getAsBoolean()&&System.currentTimeMillis()<end){Thread.sleep(10);shadowOf(Looper.getMainLooper()).idle();}assertTrue("The real page did not reach its expected state",ready.getAsBoolean());}
    private View content(Activity activity){return ((ViewGroup)activity.findViewById(android.R.id.content)).getChildAt(0);}
    private void layout(View root,int width,int height){for(int pass=0;pass<3;pass++){root.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(height,View.MeasureSpec.EXACTLY));root.layout(0,0,width,height);}}
    private void dialogLayout(View root,int width,int height){for(int pass=0;pass<3;pass++){root.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(height,View.MeasureSpec.AT_MOST));root.layout(0,0,width,root.getMeasuredHeight());}}
    @SuppressWarnings("deprecation") private void font(Activity activity){Configuration config=new Configuration(activity.getResources().getConfiguration());config.fontScale=1.5f;activity.getResources().getDisplayMetrics().scaledDensity=activity.getResources().getDisplayMetrics().density*1.5f;activity.getResources().updateConfiguration(config,activity.getResources().getDisplayMetrics());}
    private Button button(View root,String title){if(root instanceof Button&&title.contentEquals(((Button)root).getText()))return (Button)root;if(root instanceof ViewGroup)for(int i=0;i<((ViewGroup)root).getChildCount();i++){Button found=button(((ViewGroup)root).getChildAt(i),title);if(found!=null)return found;}return null;}
    private TextView text(View root,String needle){if(root instanceof TextView&&((TextView)root).getText().toString().contains(needle))return (TextView)root;if(root instanceof ViewGroup)for(int i=0;i<((ViewGroup)root).getChildCount();i++){TextView found=text(((ViewGroup)root).getChildAt(i),needle);if(found!=null)return found;}return null;}
    private int loadedImages(View root){int count=root instanceof ImageView&&((ImageView)root).getDrawable() instanceof BitmapDrawable?1:0;if(root instanceof ViewGroup)for(int index=0;index<((ViewGroup)root).getChildCount();index++)count+=loadedImages(((ViewGroup)root).getChildAt(index));return count;}
    private Rect bounds(View root,View child){Rect rect=new Rect(0,0,child.getWidth(),child.getHeight());((ViewGroup)root).offsetDescendantRectToMyCoords(child,rect);return rect;}
    private void tap(View root,View target){
        target.requestRectangleOnScreen(new Rect(0,0,target.getWidth(),target.getHeight()),true);Rect rect=bounds(root,target);long now=SystemClock.uptimeMillis();MotionEvent down=MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,rect.exactCenterX(),rect.exactCenterY(),0),up=MotionEvent.obtain(now,now+32,MotionEvent.ACTION_UP,rect.exactCenterX(),rect.exactCenterY(),0);root.dispatchTouchEvent(down);root.dispatchTouchEvent(up);down.recycle();up.recycle();shadowOf(Looper.getMainLooper()).idle();
    }
    private void readable(View root){
        if(root.getVisibility()!=View.VISIBLE)return;
        if(root instanceof TextView){TextView text=(TextView)root;if(text.getText().length()>0&&text.getLayout()!=null){assertTrue("Text clipped vertically: "+text.getText(),text.getLayout().getHeight()<=text.getHeight()-text.getCompoundPaddingTop()-text.getCompoundPaddingBottom());}}
        if(root instanceof ViewGroup){ViewGroup parent=(ViewGroup)root;for(int i=0;i<parent.getChildCount();i++){View child=parent.getChildAt(i);if(child.getVisibility()!=View.VISIBLE)continue;assertTrue("Child overflows window horizontally: "+child.getContentDescription(),child.getLeft()>=0&&child.getRight()<=parent.getWidth());readable(child);}}
    }
    private void snapshot(View root,String name)throws Exception{
        String directory=System.getenv("LUMEN_BILI_AUX_SCREENSHOTS");if(directory==null||directory.isEmpty())directory=System.getenv("LUMEN_BILI_SCREENSHOTS");if(directory==null||directory.isEmpty())return;Bitmap bitmap=Bitmap.createBitmap(root.getWidth(),root.getHeight(),Bitmap.Config.ARGB_8888);root.draw(new Canvas(bitmap));File file=new File(directory,name);assertTrue(file.getParentFile().isDirectory()||file.getParentFile().mkdirs());try(FileOutputStream stream=new FileOutputStream(file)){assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG,100,stream));}bitmap.recycle();
    }
    private final class Fixture implements AutoCloseable {
        final MockWebServer server=new MockWebServer();final List<String> paths=new CopyOnWriteArrayList<>();final List<JSONObject> commands=new CopyOnWriteArrayList<>();final AtomicInteger stateReads=new AtomicInteger();volatile long file=70;
        Fixture()throws Exception{
            Bitmap bitmap=Bitmap.createBitmap(240,360,Bitmap.Config.ARGB_8888);Drawable artwork=ContextCompat.getDrawable(RuntimeEnvironment.getApplication(),R.drawable.discovery_preview_coast);assertNotNull(artwork);artwork.setBounds(0,0,240,360);artwork.draw(new Canvas(bitmap));ByteArrayOutputStream bytes=new ByteArrayOutputStream();bitmap.compress(Bitmap.CompressFormat.PNG,100,bytes);bitmap.recycle();byte[] image=bytes.toByteArray();
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){try{
                String path=request.getPath();paths.add(path);assertEquals("Bearer "+TOKEN,request.getHeader("Authorization"));
                if(path.endsWith("/thumbnail")||path.endsWith("/cover"))return new MockResponse().setHeader("Content-Type","image/png").setBody(new okio.Buffer().write(image));
                if(path.equals("/api/remote")&&request.getMethod().equals("POST")){commands.add(new JSONObject(request.getBody().readUtf8()));return new MockResponse().setBody("{\"command_id\":\"sample-command\"}");}
                if(path.equals("/api/remote")){stateReads.incrementAndGet();return new MockResponse().setBody(new JSONObject().put("active",true).put("file_id",file).put("work_id",7).put("title","海岸纪行").put("position",2308).put("duration",6480).put("playing",true).put("volume",48).put("shutdown_supported",true).put("shutdown_allowed",true).put("audio",new JSONArray().put(new JSONObject().put("name","默认（国语）").put("index",2))).put("subtitles",new JSONArray()).toString());}
                if(path.startsWith("/api/tasks")){
                    JSONArray items=new JSONArray().put(new JSONObject().put("id","scrape").put("work_id",7).put("work_title","海岸纪行").put("label","影片资料刮削").put("status","done").put("status_label","已完成"));
                    if(!path.contains("offset=30"))items.put(new JSONObject().put("id","thumbnail").put("work_id",8).put("work_title","星夜环游").put("label","视频缩略图").put("status","running").put("status_label","进行中").put("progress",new JSONObject().put("completed",64).put("total",100).put("unit","items"))).put(new JSONObject().put("id","repair").put("work_id",9).put("work_title","雪山之上").put("label","资料修复").put("status","pending").put("status_label","待确认").put("reason","请到电脑处理。"));
                    return new MockResponse().setBody(new JSONObject().put("items",items).put("total",31).toString());
                }
                return new MockResponse().setBody("{}");
            }catch(Exception error){throw new AssertionError(error);}}});server.start();
        }
        Api api()throws Exception{return new Api(new Connection(server.url("/").toString(),TOKEN));}
        @Override public void close()throws Exception{server.close();}
    }
    private RemoteActivity remote(ActivityController<RemoteActivity> life,Fixture fixture)throws Exception{RemoteActivity activity=life.get();set(activity,"api",fixture.api());call(activity,"buildUi");life.start().resume().visible();return activity;}
    private boolean polling(RemoteActivity activity){try{return (Boolean)get(activity,"polling");}catch(Exception error){throw new AssertionError(error);}}

    @Test public void remoteMediaCardUsesExactThumbnailAndQuickActionsSendOriginalCommands()throws Exception{
        try(Fixture fixture=new Fixture();ActivityController<RemoteActivity> life=Robolectric.buildActivity(RemoteActivity.class).create()){
            RemoteActivity activity=remote(life,fixture);waitFor(()->fixture.paths.contains("/api/files/70/thumbnail"));waitFor(()->{try{return ((ImageView)get(activity,"thumbnail")).getDrawable() instanceof BitmapDrawable;}catch(Exception error){return false;}});
            View root=content(activity);layout(root,393,852);assertTrue(root.findViewWithTag("remoteCurrentMedia") instanceof MaterialCardView);LinearLayout quick=root.findViewWithTag("remoteMediaActions");assertEquals(LinearLayout.HORIZONTAL,quick.getOrientation());assertEquals(3,quick.getChildCount());assertEquals(56,((Button)get(activity,"togglePlayback")).getHeight());
            tap(root,button(root,"静音 / 恢复"));waitFor(()->fixture.commands.stream().anyMatch(command->command.optString("action").equals("mute")));JSONObject mute=fixture.commands.stream().filter(command->command.optString("action").equals("mute")).findFirst().get();assertTrue(mute.getBoolean("value"));
            tap(root,button(root,"选择音轨"));AlertDialog tracks=ShadowAlertDialog.getLatestAlertDialog();assertEquals("电脑音轨",shadowOf(tracks).getTitle());tracks.getListView().performItemClick(tracks.getListView().getChildAt(1),1,1);waitFor(()->fixture.commands.stream().anyMatch(command->command.optString("action").equals("audio")&&command.optInt("value")==2));tracks.dismiss();
            waitFor(()->!polling(activity));int reads=fixture.stateReads.get();call(activity,"poll");waitFor(()->fixture.stateReads.get()>reads&&!polling(activity));assertEquals("Repeated state polling must not reload the same file image",1,fixture.paths.stream().filter(path->path.equals("/api/files/70/thumbnail")).count());
            // The production guard correctly ignores a poll while its previous request is active.
            // Advance this fixture only after that real request has finished, rather than racing it.
            fixture.file=71;call(activity,"poll");waitFor(()->fixture.paths.contains("/api/files/71/thumbnail"));waitFor(()->{try{ImageView thumbnail=(ImageView)get(activity,"thumbnail");return thumbnail.getDrawable() instanceof BitmapDrawable&&String.valueOf(thumbnail.getTag()).endsWith("/api/files/71/thumbnail");}catch(Exception error){return false;}});assertFalse(fixture.paths.stream().anyMatch(path->path.contains("/works/7/cover")));((ScrollView)root).scrollTo(0,0);layout(root,393,852);snapshot(root,"bili-remote-393.png");
        }
    }

    @Test public void remoteShutdownStillRequiresPermissionAndExplicitConfirmation()throws Exception{
        try(Fixture fixture=new Fixture();ActivityController<RemoteActivity> life=Robolectric.buildActivity(RemoteActivity.class).create()){
            RemoteActivity activity=remote(life,fixture);waitFor(()->{try{return ((Button)get(activity,"shutdown")).isEnabled();}catch(Exception error){return false;}});View root=content(activity);layout(root,393,852);Button shutdown=(Button)get(activity,"shutdown");tap(root,shutdown);AlertDialog confirmation=ShadowAlertDialog.getLatestAlertDialog();assertEquals("关闭当前连接的电脑？",shadowOf(confirmation).getTitle());assertTrue(fixture.commands.isEmpty());confirmation.getButton(AlertDialog.BUTTON_NEGATIVE).performClick();assertTrue(fixture.commands.isEmpty());
            tap(root,shutdown);confirmation=ShadowAlertDialog.getLatestAlertDialog();confirmation.getButton(AlertDialog.BUTTON_POSITIVE).performClick();waitFor(()->fixture.commands.stream().anyMatch(command->command.optString("action").equals("shutdown")));assertTrue(fixture.commands.stream().filter(command->command.optString("action").equals("shutdown")).findFirst().get().getBoolean("confirm"));
            set(activity,"state",new JSONObject().put("shutdown_supported",true).put("shutdown_allowed",true).put("shutdown_pending",9));call(activity,"powerState");assertFalse(shutdown.isEnabled());Button cancel=(Button)get(activity,"cancelShutdown");assertEquals(View.VISIBLE,cancel.getVisibility());layout(root,393,852);tap(root,cancel);waitFor(()->fixture.commands.stream().anyMatch(command->command.optString("action").equals("shutdown_cancel")));
            set(activity,"state",new JSONObject().put("shutdown_supported",true).put("shutdown_allowed",false));call(activity,"powerState");assertFalse(shutdown.isEnabled());assertEquals(View.GONE,cancel.getVisibility());
        }
    }

    @Test public void taskCardsAreReadOnlyAndRealChipsRetainFilterAndPagingRequests()throws Exception{
        try(Fixture fixture=new Fixture();ActivityController<Activity> life=Robolectric.buildActivity(Activity.class).setup()){
            AlertDialog dialog=TaskCenter.show(life.get(),fixture.api());try{
                View root=dialog.getWindow().getDecorView();waitFor(()->root.findViewWithTag("computerTaskCard:repair")!=null);dialogLayout(root,393,788);assertNotNull(text(root,"任务在电脑执行"));assertNotNull(text(root,"请到电脑处理"));ViewGroup rows=root.findViewWithTag("computerTaskRows");assertEquals(3,rows.getChildCount());for(int index=0;index<3;index++)assertTrue(rows.getChildAt(index) instanceof MaterialCardView);
                ChipGroup categories=root.findViewWithTag("computerTaskCategory");assertEquals(5,categories.getChildCount());assertTrue(categories.getChildAt(0) instanceof Chip);assertTrue(categories.isSingleSelection());assertNotNull(text(root,"进度 64 / 100"));assertNull(button(rows,"重试"));assertNull(button(rows,"确认"));waitFor(()->loadedImages(rows)==3);snapshot(root,"bili-tasks-393.png");
                tap(root,root.findViewWithTag("nextTaskPage"));waitFor(()->fixture.paths.stream().anyMatch(path->path.contains("/api/tasks?state=all&offset=30")));waitFor(()->root.findViewWithTag("previousTaskPage").isEnabled());dialogLayout(root,393,788);Chip pending=root.findViewWithTag("taskCategory:pending");tap(root,pending);waitFor(()->fixture.paths.stream().anyMatch(path->path.contains("/api/tasks?state=pending&offset=0")));assertTrue(pending.isChecked());assertFalse(root.findViewWithTag("previousTaskPage").isEnabled());assertTrue("Task pages must never emit action requests",fixture.commands.isEmpty());
            }finally{dialog.dismiss();}
        }
    }

    private byte[] manifest(String version,long code){return ("{\"version\":\""+version+"\",\"version_code\":"+code+",\"bytes\":5,\"sha256\":\""+"a".repeat(64)+"\"}").getBytes(StandardCharsets.UTF_8);}
    @Test public void updateContextualActionsPreserveCheckCancelAndSystemInstallFlow()throws Exception{
        CountDownLatch reply=new CountDownLatch(1);try(ActivityController<UpdateActivity> life=Robolectric.buildActivity(UpdateActivity.class)){
            UpdateActivity activity=life.get();android.content.pm.PackageInfo installed=RuntimeEnvironment.getApplication().getPackageManager().getPackageInfo("net.lumen.media",0);String[] parts=installed.versionName.split("\\.");String nextVersion=parts[0]+"."+parts[1]+"."+(Integer.parseInt(parts[2])+1);
            activity.fetcher=(url,limit)->{reply.await(4,TimeUnit.SECONDS);if(url.equals(GitHubUpdates.RELEASE))throw new java.io.IOException("Use isolated target fixture");return manifest(nextVersion,installed.getLongVersionCode()+1);};life.create().start().resume().visible();View root=content(activity);layout(root,393,852);assertEquals(View.GONE,((Button)get(activity,"download")).getVisibility());assertEquals(View.GONE,((Button)get(activity,"install")).getVisibility());assertEquals(View.GONE,((Button)get(activity,"cancel")).getVisibility());reply.countDown();waitFor(()->{try{return ((Button)get(activity,"download")).isEnabled();}catch(Exception error){return false;}});
            assertEquals(View.VISIBLE,((Button)get(activity,"download")).getVisibility());assertEquals(View.GONE,((Button)get(activity,"install")).getVisibility());assertEquals(View.GONE,((Button)get(activity,"cancel")).getVisibility());assertTrue(root.findViewWithTag("updateInformation") instanceof MaterialCardView);layout(root,393,852);snapshot(root,"bili-update-393.png");
            working(activity,true);Button cancel=(Button)get(activity,"cancel");assertEquals(View.VISIBLE,cancel.getVisibility());assertEquals(View.GONE,((Button)get(activity,"download")).getVisibility());layout(root,393,852);tap(root,cancel);assertEquals(Boolean.TRUE,get(activity,"cancelled"));assertFalse(cancel.isEnabled());
            File verified=new File(activity.getCacheDir(),"already-verified-fixture.apk");set(activity,"downloaded",verified);working(activity,false);Button install=(Button)get(activity,"install");assertEquals(View.VISIBLE,install.getVisibility());assertEquals(View.GONE,((Button)get(activity,"download")).getVisibility());layout(root,393,852);tap(root,install);Intent permission=shadowOf(activity).getNextStartedActivity();assertNotNull(permission);assertEquals(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,permission.getAction());assertTrue(permission.getDataString().contains("net.lumen.media"));
        }finally{reply.countDown();}
    }

    @Test @Config(qualifiers="w320dp-h852dp-mdpi") public void narrowLargeFontRemoteAndTaskLayoutsKeepAllActionsReadable()throws Exception{
        try(Fixture fixture=new Fixture();ActivityController<RemoteActivity> life=Robolectric.buildActivity(RemoteActivity.class).create()){
            font(life.get());RemoteActivity activity=remote(life,fixture);waitFor(()->fixture.paths.contains("/api/remote"));View root=content(activity);layout(root,320,852);readable(root);ViewGroup quick=root.findViewWithTag("remoteMediaActions");for(int index=0;index<quick.getChildCount();index++){View action=quick.getChildAt(index);assertTrue(action.getWidth()>=48);assertTrue(action.getHeight()>=48);}snapshot(root,"bili-remote-320-font150.png");
        }
        try(Fixture fixture=new Fixture();ActivityController<Activity> life=Robolectric.buildActivity(Activity.class).setup()){
            font(life.get());AlertDialog dialog=TaskCenter.show(life.get(),fixture.api());try{View root=dialog.getWindow().getDecorView();waitFor(()->root.findViewWithTag("computerTaskCard:repair")!=null);dialogLayout(root,320,788);assertTrue(root.findViewWithTag("computerTaskRows").getHeight()>0);for(String tag:new String[]{"previousTaskPage","nextTaskPage"}){Button action=root.findViewWithTag(tag);assertTrue(action.getWidth()>=48);assertTrue(action.getHeight()>=48);assertTrue(bounds(root,action).bottom<=root.getHeight());}snapshot(root,"bili-tasks-320-font150.png");}finally{dialog.dismiss();}
        }
    }

    @Test @Config(qualifiers="w320dp-h852dp-mdpi") public void narrowLargeFontUpdateUsesScrollableBodyAndOnePrimaryAction()throws Exception{
        try(ActivityController<UpdateActivity> life=Robolectric.buildActivity(UpdateActivity.class)){
            UpdateActivity activity=life.get();font(activity);activity.fetcher=(url,limit)->{throw new java.io.IOException("当前测试来源不可用");};life.create().start().resume().visible();waitFor(()->{try{return ((Button)get(activity,"check")).isEnabled();}catch(Exception error){return false;}});View root=content(activity);layout(root,320,852);Button check=(Button)get(activity,"check");assertEquals(View.VISIBLE,check.getVisibility());for(String field:new String[]{"download","install","cancel"})assertEquals(View.GONE,((Button)get(activity,field)).getVisibility());assertTrue(bounds(root,check).bottom<=root.getHeight());readable(root);snapshot(root,"bili-update-320-font150.png");
        }
    }
}
