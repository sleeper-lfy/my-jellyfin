package net.lumen.media;

import android.app.AlertDialog;
import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Intent;
import android.content.pm.ProviderInfo;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.Bundle;
import android.os.Looper;
import android.provider.OpenableColumns;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.TextView;
import okhttp3.mockwebserver.MockWebServer;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.Shadows;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.shadows.ShadowAlertDialog;
import org.robolectric.shadows.ShadowContentResolver;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w393dp-h852dp-mdpi")
public class ExternalPlayerUiTest {
    private Object get(Object target,String name)throws Exception{Field field=target.getClass().getDeclaredField(name);field.setAccessible(true);return field.get(target);}
    private void set(Object target,String name,Object value)throws Exception{Field field=target.getClass().getDeclaredField(name);field.setAccessible(true);field.set(target,value);}
    private void call(Object target,String name)throws Exception{Method method=target.getClass().getDeclaredMethod(name);method.setAccessible(true);method.invoke(target);}
    private void waitFor(BooleanSupplier ready)throws Exception{long deadline=System.currentTimeMillis()+5000;while(!ready.getAsBoolean()&&System.currentTimeMillis()<deadline){Thread.sleep(10);Shadows.shadowOf(Looper.getMainLooper()).idle();}assertTrue(ready.getAsBoolean());}
    private Intent view(){return new Intent(Intent.ACTION_VIEW).setDataAndType(Uri.parse("https://example.invalid/standalone.mp4"),"video/mp4").putExtra("work_id",999L).putExtra("file_id",888L).putExtra("queue",true);}
    private Button button(View root,String text){if(root instanceof Button&&text.contentEquals(((Button)root).getText()))return (Button)root;if(root instanceof ViewGroup)for(int i=0;i<((ViewGroup)root).getChildCount();i++){Button found=button(((ViewGroup)root).getChildAt(i),text);if(found!=null)return found;}return null;}
    public static final class MetadataProvider extends ContentProvider {
        final AtomicBoolean queried=new AtomicBoolean(),onMain=new AtomicBoolean();
        volatile CountDownLatch entered,release;
        @Override public boolean onCreate(){return true;}
        @Override public String getType(Uri uri){return "video/mp4";}
        @Override public Cursor query(Uri uri,String[] projection,String selection,String[] args,String sort){queried.set(true);onMain.set(Looper.myLooper()==Looper.getMainLooper());if(entered!=null)entered.countDown();if(release!=null)try{release.await(3,TimeUnit.SECONDS);}catch(InterruptedException interrupted){Thread.currentThread().interrupt();}MatrixCursor cursor=new MatrixCursor(new String[]{OpenableColumns.DISPLAY_NAME});cursor.addRow(new Object[]{"Provider movie.mp4"});return cursor;}
        @Override public Uri insert(Uri uri,ContentValues values){throw new UnsupportedOperationException();}
        @Override public int delete(Uri uri,String selection,String[] args){return 0;}
        @Override public int update(Uri uri,ContentValues values,String selection,String[] args){return 0;}
    }
    @Test public void contentMetadataLoadsOffTheMainThreadWithoutAConnectionOrLibraryIdentity()throws Exception{
        RuntimeEnvironment.getApplication().getSharedPreferences("connection",0).edit().clear().apply();MetadataProvider provider=new MetadataProvider();ProviderInfo info=new ProviderInfo();info.authority="external-player-fixture";provider.attachInfo(RuntimeEnvironment.getApplication(),info);ShadowContentResolver.registerProviderInternal(info.authority,provider);
        Intent intent=new Intent(Intent.ACTION_VIEW).setDataAndType(Uri.parse("content://external-player-fixture/video/7"),"video/mp4").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION).putExtra("work_id",999L).putExtra("queue",true);
        try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class,intent).create()){
            PlayerActivity activity=lifecycle.get();waitFor(()->{try{return get(activity,"externalSource")!=null;}catch(Exception ignored){return false;}});assertTrue(provider.queried.get());assertFalse(provider.onMain.get());assertFalse(activity.isFinishing());assertEquals(true,get(activity,"externalPlayback"));assertNull(get(activity,"api"));assertNull(get(activity,"bridge"));assertNull(get(activity,"work"));assertNull(get(activity,"file"));assertNull(get(activity,"session"));assertEquals(false,get(activity,"queueMode"));assertEquals(0L,get(activity,"desiredWork"));assertEquals("Provider movie.mp4",((TextView)get(activity,"title")).getText().toString());
        }
    }
    @Test public void externalSettingsDisableLibraryActionsButRetainDecoderSubtitleAndPictureTools()throws Exception{
        try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class,view()).create()){
            PlayerActivity activity=lifecycle.get();waitFor(()->{try{return get(activity,"externalSource")!=null;}catch(Exception ignored){return false;}});assertFalse(((Button)get(activity,"personalFavorite")).isEnabled());assertFalse(((Button)get(activity,"personalRating")).isEnabled());assertFalse(((Button)get(activity,"quickFiles")).isEnabled());
            call(activity,"playbackSettings");AlertDialog settings=ShadowAlertDialog.getLatestAlertDialog();for(String name:new String[]{"选集 / 文件","时间点书签","我的评价","播放队列","上个视频","下个视频"}){Button action=button(settings.getWindow().getDecorView(),name);assertNotNull(name,action);assertFalse(name,action.isEnabled());assertTrue(action.getContentDescription().toString().contains("仅媒体库"));}
            com.google.android.material.materialswitch.MaterialSwitch automatic=settings.getWindow().getDecorView().findViewWithTag("playerAutoNextSwitch");assertNotNull(automatic);assertFalse(automatic.isEnabled());settings.dismiss();
            call(activity,"subtitleSettings");AlertDialog subtitles=ShadowAlertDialog.getLatestAlertDialog();assertEquals("字幕同步与样式",Shadows.shadowOf(subtitles).getTitle());subtitles.dismiss();
            call(activity,"beautySettings");AlertDialog beauty=ShadowAlertDialog.getLatestAlertDialog();assertEquals("实时美颜",Shadows.shadowOf(beauty).getTitle());beauty.dismiss();
            call(activity,"vrSettings");AlertDialog vr=ShadowAlertDialog.getLatestAlertDialog();assertEquals("VR 播放设置",Shadows.shadowOf(vr).getTitle());vr.dismiss();
            call(activity,"decoder");AlertDialog decoder=ShadowAlertDialog.getLatestAlertDialog();assertEquals(3,decoder.getListView().getCount());decoder.dismiss();assertNull(get(activity,"api"));assertNull(get(activity,"player"));
        }
    }
    @Test public void decoderAndVrChangesDuringBlockedMetadataDoNotInvalidateTheUriResolution()throws Exception{
        MetadataProvider provider=new MetadataProvider();provider.entered=new CountDownLatch(1);provider.release=new CountDownLatch(1);ProviderInfo info=new ProviderInfo();info.authority="external-player-blocked";provider.attachInfo(RuntimeEnvironment.getApplication(),info);ShadowContentResolver.registerProviderInternal(info.authority,provider);
        Intent intent=new Intent(Intent.ACTION_VIEW).setDataAndType(Uri.parse("content://external-player-blocked/video/7"),"video/mp4").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class,intent).create()){
            PlayerActivity activity=lifecycle.get();assertTrue(provider.entered.await(2,TimeUnit.SECONDS));assertEquals(true,get(activity,"externalLoading"));int generation=(Integer)get(activity,"generation");
            Method decoder=PlayerActivity.class.getDeclaredMethod("applyDecoderMode",int.class);decoder.setAccessible(true);decoder.invoke(activity,PlaybackDecoderPolicy.MEDIACODEC_JNI);
            Method vr=PlayerActivity.class.getDeclaredMethod("setVrEnabled",boolean.class);vr.setAccessible(true);vr.invoke(activity,true);assertTrue((Integer)get(activity,"generation")>generation);assertEquals(true,get(activity,"externalLoading"));
            provider.release.countDown();waitFor(()->{try{return get(activity,"externalSource")!=null&&Boolean.FALSE.equals(get(activity,"externalLoading"));}catch(Exception ignored){return false;}});
            assertEquals(PlaybackDecoderPolicy.MEDIACODEC_JNI,get(activity,"decoderMode"));assertEquals(true,get(activity,"vrEnabled"));assertNull(get(activity,"externalResolution"));assertNull(get(activity,"api"));assertNull(get(activity,"player"));assertEquals("Provider movie.mp4",((TextView)get(activity,"title")).getText().toString());
        }finally{provider.release.countDown();}
    }
    @Test public void externalChangesStayInMemoryAndNeverPostLibraryRecordsOrConsumeTheQueue()throws Exception{
        try(MockWebServer server=new MockWebServer();ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class,view()).create()){
            server.start();PlayerActivity activity=lifecycle.get();waitFor(()->{try{return get(activity,"externalSource")!=null;}catch(Exception ignored){return false;}});
            activity.getSharedPreferences("queue",0).edit().putString("ids","[7,8]").putInt("index",1).apply();Map<String,?> queueBefore=new HashMap<>(activity.getSharedPreferences("queue",0).getAll());activity.getSharedPreferences("media-preferences",0).edit().putString("unchanged-fixture","keep").apply();Map<String,?> preferencesBefore=new HashMap<>(activity.getSharedPreferences("media-preferences",0).getAll());
            assertNull(get(activity,"api"));set(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));((JSONObject)get(activity,"filePreferences")).put("subtitle_delay",1.5);call(activity,"changedPreferences");call(activity,"flushPreferences");call(activity,"showPlayerQueue");call(activity,"showBookmarks");
            set(activity,"resumeMs",45000L);Bundle saved=new Bundle();activity.onSaveInstanceState(saved);assertEquals(45000L,saved.getLong("external_position"));assertFalse(saved.containsKey("work_id"));assertFalse(saved.containsKey("file_id"));
            Method tick=PlayerActivity.class.getDeclaredMethod("tick",boolean.class,boolean.class);tick.setAccessible(true);tick.invoke(activity,false,false);tick.invoke(activity,true,true);call(activity,"onPlaybackEnded");assertEquals(0,server.getRequestCount());assertEquals(queueBefore,activity.getSharedPreferences("queue",0).getAll());assertEquals(preferencesBefore,activity.getSharedPreferences("media-preferences",0).getAll());assertNull(get(activity,"bridge"));assertNull(get(activity,"session"));assertNull(get(activity,"work"));assertNull(get(activity,"file"));assertTrue(((TextView)get(activity,"status")).getText().toString().contains("外部视频播放结束"));set(activity,"api",null);
        }
    }
}
