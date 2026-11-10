package net.lumen.media;

import android.app.AlertDialog;
import android.content.SharedPreferences;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;
import org.robolectric.shadows.ShadowAlertDialog;
import org.robolectric.android.controller.ActivityController;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33)
public class PlaybackDecoderPolicyTest {
    @Test public void existingSoftwarePreferenceMigratesAndEveryNewModePersists(){
        SharedPreferences preferences=RuntimeEnvironment.getApplication().getSharedPreferences("decoder-test",0);
        preferences.edit().clear().apply();assertEquals(PlaybackDecoderPolicy.AUTOMATIC,PlaybackDecoderPolicy.load(preferences));
        preferences.edit().putBoolean("software",true).apply();assertEquals(PlaybackDecoderPolicy.SOFTWARE,PlaybackDecoderPolicy.load(preferences));
        PlaybackDecoderPolicy.save(preferences,PlaybackDecoderPolicy.MEDIACODEC_JNI);assertEquals(PlaybackDecoderPolicy.MEDIACODEC_JNI,PlaybackDecoderPolicy.load(preferences));assertFalse(preferences.getBoolean("software",true));
        PlaybackDecoderPolicy.save(preferences,PlaybackDecoderPolicy.SOFTWARE);assertEquals(PlaybackDecoderPolicy.SOFTWARE,PlaybackDecoderPolicy.load(preferences));
        PlaybackDecoderPolicy.save(preferences,PlaybackDecoderPolicy.AUTOMATIC);assertEquals(PlaybackDecoderPolicy.AUTOMATIC,PlaybackDecoderPolicy.load(preferences));
        preferences.edit().putInt("decoder_mode",999).apply();assertEquals(PlaybackDecoderPolicy.AUTOMATIC,PlaybackDecoderPolicy.load(preferences));
    }
    @Test public void actualDecoderChooserCanSelectJniAndReturnToAutomaticWithoutOpeningANativeDecoder()throws Exception{
        try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=lifecycle.get();Method chooser=PlayerActivity.class.getDeclaredMethod("decoder");chooser.setAccessible(true);
            chooser.invoke(activity);AlertDialog dialog=ShadowAlertDialog.getLatestAlertDialog();
            assertEquals(3,dialog.getListView().getCount());assertTrue(dialog.getListView().getAdapter().getItem(1).toString().contains("JNI"));
            dialog.getListView().performItemClick(null,1,1);
            assertEquals(PlaybackDecoderPolicy.MEDIACODEC_JNI,PlaybackDecoderPolicy.load(activity.getSharedPreferences("playback",0)));
            chooser.invoke(activity);dialog=ShadowAlertDialog.getLatestAlertDialog();assertEquals(1,dialog.getListView().getCheckedItemPosition());
            dialog.getListView().performItemClick(null,0,0);assertEquals(PlaybackDecoderPolicy.AUTOMATIC,PlaybackDecoderPolicy.load(activity.getSharedPreferences("playback",0)));
            Field player=PlayerActivity.class.getDeclaredField("player");player.setAccessible(true);assertNull(player.get(activity));
        }
    }
    @Test public void holdSpeedLabelsRetainQuarterRates(){assertEquals("1.25",PlaybackPolicy.speedLabel(1.25f));assertEquals("1.75",PlaybackPolicy.speedLabel(1.75f));assertEquals("2",PlaybackPolicy.speedLabel(2));}
    @Test public void nativeClockBurstsAreConsumedBeforeTheControlRefreshPath()throws Exception{
        try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=lifecycle.get();
            Method filter=PlayerActivity.class.getDeclaredMethod("handleClockEvent",org.videolan.libvlc.MediaPlayer.Event.class);filter.setAccessible(true);
            java.lang.reflect.Constructor<org.videolan.libvlc.MediaPlayer.Event> constructor=org.videolan.libvlc.MediaPlayer.Event.class.getDeclaredConstructor(int.class,long.class);constructor.setAccessible(true);
            for(int i=0;i<1000;i++){
                assertEquals(true,filter.invoke(activity,constructor.newInstance(org.videolan.libvlc.MediaPlayer.Event.TimeChanged,(long)i)));
                assertEquals(true,filter.invoke(activity,constructor.newInstance(org.videolan.libvlc.MediaPlayer.Event.PositionChanged,(long)i)));
            }
            for(int type:new int[]{org.videolan.libvlc.MediaPlayer.Event.Paused,org.videolan.libvlc.MediaPlayer.Event.Playing,org.videolan.libvlc.MediaPlayer.Event.Vout,org.videolan.libvlc.MediaPlayer.Event.EncounteredError})
                assertEquals(false,filter.invoke(activity,constructor.newInstance(type,0L)));
        }
    }
}
