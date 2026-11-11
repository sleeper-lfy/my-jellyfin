package net.lumen.media;

import android.app.AlertDialog;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.Rect;
import android.graphics.Shader;
import android.graphics.drawable.BitmapDrawable;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import com.google.android.material.button.MaterialButton;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.GraphicsMode;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.shadows.ShadowAlertDialog;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Set;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w393dp-h852dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
public class PlayerChromeBilibiliTest {
    private Object get(Object object,String name)throws Exception{Field field=object.getClass().getDeclaredField(name);field.setAccessible(true);return field.get(object);}
    private void set(Object object,String name,Object value)throws Exception{Field field=object.getClass().getDeclaredField(name);field.setAccessible(true);field.set(object,value);}
    private void call(Object object,String name)throws Exception{Method method=object.getClass().getDeclaredMethod(name);method.setAccessible(true);method.invoke(object);}
    private void layout(View root,int width,int height){for(int pass=0;pass<3;pass++){root.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(height,View.MeasureSpec.EXACTLY));root.layout(0,0,width,height);}}
    private FrameLayout build(PlayerActivity activity)throws Exception{
        Method build=PlayerActivity.class.getDeclaredMethod("buildPlayerUi",android.content.SharedPreferences.class);build.setAccessible(true);build.invoke(activity,activity.getSharedPreferences("playback",0));
        set(activity,"work",new JSONObject().put("id",7).put("kind","movie").put("title","海岸纪行").put("year",2025).put("rating",8).put("favorite",1).put("disliked",0));
        set(activity,"file",new JSONObject().put("id",70).put("name","Coast.Journal.2160p.HEVC.mkv").put("height",2160).put("size",7730941133L));call(activity,"refreshPersonal");((TextView)get(activity,"title")).setText("海岸纪行");((TextView)get(activity,"time")).setText("38:28 / 1:48:00");((android.widget.SeekBar)get(activity,"seek")).setProgress(3562);return (FrameLayout)get(activity,"root");
    }
    private Button button(View root,String label){if(root instanceof Button&&label.contentEquals(((Button)root).getText()))return (Button)root;if(root instanceof ViewGroup)for(int i=0;i<((ViewGroup)root).getChildCount();i++){Button result=button(((ViewGroup)root).getChildAt(i),label);if(result!=null)return result;}return null;}
    private Rect bounds(View root,View child){Rect rect=new Rect(0,0,child.getWidth(),child.getHeight());((ViewGroup)root).offsetDescendantRectToMyCoords(child,rect);return rect;}
    private void tap(View root,int x,int y){long now=android.os.SystemClock.uptimeMillis();MotionEvent down=MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,x,y,0),up=MotionEvent.obtain(now,now+50,MotionEvent.ACTION_UP,x,y,0);root.dispatchTouchEvent(down);root.dispatchTouchEvent(up);down.recycle();up.recycle();}
    /** Test-only media artwork. Captures prove native layout, not decoding or playback performance. */
    private void scenery(View view,boolean stereo){
        Bitmap bitmap=Bitmap.createBitmap(852,480,Bitmap.Config.ARGB_8888);Canvas canvas=new Canvas(bitmap);Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        for(int eye=0;eye<(stereo?2:1);eye++){int width=stereo?426:852;canvas.save();canvas.translate(eye*width,0);paint.setShader(new LinearGradient(0,0,0,480,new int[]{0xff506b90,0xffb9c4d1,0xff2b7289,0xff10435d},null,Shader.TileMode.CLAMP));canvas.drawRect(0,0,width,480,paint);paint.setShader(null);paint.setColor(0xff254a4e);Path mountain=new Path();mountain.moveTo(width*.3f,250);mountain.lineTo(width*.6f,110);mountain.lineTo(width*.72f,160);mountain.lineTo(width,60);mountain.lineTo(width,480);mountain.lineTo(width*.56f,390);mountain.close();canvas.drawPath(mountain,paint);paint.setColor(0xffc8c5aa);Path coast=new Path();coast.moveTo(width*.5f,480);coast.cubicTo(width*.65f,390,width*.45f,340,width*.85f,290);coast.lineTo(width,480);coast.close();canvas.drawPath(coast,paint);paint.setColor(0xffc9e1df);paint.setStrokeWidth(3);for(int i=0;i<8;i++)canvas.drawLine(8,270+i*23,width*.45f,255+i*23,paint);canvas.restore();}
        view.setBackground(new BitmapDrawable(view.getResources(),bitmap));
    }
    private void snapshot(View root,String name)throws Exception{String directory=System.getenv("LUMEN_UI_SCREENSHOTS");if(directory==null)return;File file=new File(directory,name);file.getParentFile().mkdirs();Bitmap image=Bitmap.createBitmap(root.getWidth(),root.getHeight(),Bitmap.Config.ARGB_8888);root.draw(new Canvas(image));try(FileOutputStream out=new FileOutputStream(file)){assertTrue(image.compress(Bitmap.CompressFormat.PNG,100,out));}image.recycle();}
    @Test public void portraitUsesAnUncroppedSixteenByNineViewportAndBlankTapStillTogglesChrome()throws Exception{
        try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=lifecycle.get();FrameLayout root=build(activity);View video=(View)get(activity,"video");scenery(video,false);layout(root,393,852);
            assertEquals(393,video.getWidth());assertEquals(Math.round(393*9f/16),video.getHeight());assertTrue(video.getTop()>=64);
            assertEquals(4,((LinearLayout)get(activity,"personalRow")).getChildCount());assertEquals(4,((LinearLayout)get(activity,"quickRow")).getChildCount());
            Rect center=bounds(root,(View)get(activity,"centerPause"));assertTrue(center.top>=video.getTop());assertTrue(center.bottom<=video.getBottom());
            assertTrue(((TextView)get(activity,"portraitMeta")).getText().toString().contains("2160P"));snapshot(root,"native-player-portrait.png");
            tap(root,32,video.getTop()+12);assertEquals(false,get(activity,"controlsVisible"));assertEquals(View.GONE,((View)get(activity,"bottomBar")).getVisibility());
            tap(root,32,video.getTop()+12);assertEquals(true,get(activity,"controlsVisible"));assertEquals(View.VISIBLE,((View)get(activity,"bottomBar")).getVisibility());
            HoldSpeed hold=(HoldSpeed)get(activity,"holdSpeed");HoldSpeedTest.Fake decoder=new HoldSpeedTest.Fake(1.25f);assertTrue(hold.begin(decoder));set(activity,"holdActivated",true);
            MotionEvent cancel=MotionEvent.obtain(0,0,MotionEvent.ACTION_CANCEL,32,video.getTop()+12,0);Method touch=PlayerActivity.class.getDeclaredMethod("playbackTouch",View.class,MotionEvent.class);touch.setAccessible(true);touch.invoke(activity,root.findViewWithTag("videoGestures"),cancel);cancel.recycle();assertEquals(1.25f,decoder.value,0);assertFalse(hold.active());
            layout(root,852,393);assertEquals(393,video.getHeight());assertEquals(View.GONE,((View)get(activity,"portraitInfo")).getVisibility());snapshot(root,"native-player-landscape.png");
        }
    }
    @Test public void settingTabsContainDividedRowsAndDislikeIsARealDisabledActionWhenSaving()throws Exception{
        try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=lifecycle.get();FrameLayout root=build(activity);layout(root,393,852);call(activity,"playbackSettings");AlertDialog dialog=ShadowAlertDialog.getLatestAlertDialog();View decor=dialog.getWindow().getDecorView();layout(decor,393,700);
            LinearLayout groups=decor.findViewWithTag("playerSettingActions");assertEquals(3,groups.getChildCount());LinearLayout first=(LinearLayout)groups.getChildAt(0);assertEquals(7,first.getChildCount());
            MaterialButton audio=(MaterialButton)button(decor,"音轨");assertNotNull(audio);assertTrue(audio.getHeight()>=48);assertEquals(0,android.graphics.Color.alpha(audio.getBackgroundTintList().getDefaultColor()));snapshot(decor,"native-player-settings.png");
            com.google.android.material.materialswitch.MaterialSwitch autoNext=decor.findViewWithTag("playerAutoNextSwitch");boolean original=activity.getSharedPreferences("player",0).getBoolean("auto_next",true);assertEquals(original,autoNext.isChecked());
            autoNext.performClick();assertEquals(!original,activity.getSharedPreferences("player",0).getBoolean("auto_next",true));assertTrue(dialog.isShowing());button(decor,"自动播放下一集").performClick();assertEquals(original,activity.getSharedPreferences("player",0).getBoolean("auto_next",true));assertEquals(original,autoNext.isChecked());assertTrue(dialog.isShowing());
            ((Set<Long>)get(activity,"personalPending")).add(7L);button(decor,"我的评价").performClick();dialog=ShadowAlertDialog.getLatestAlertDialog();Button disliked=button(dialog.getWindow().getDecorView(),"不喜欢");assertNotNull(disliked);assertSame(disliked,get(activity,"personalDisliked"));assertFalse(disliked.isEnabled());assertTrue(disliked.getParent() instanceof PlayerChrome.SettingRow);dialog.dismiss();org.robolectric.Shadows.shadowOf(android.os.Looper.getMainLooper()).idle();assertNull(get(activity,"personalDisliked"));
            call(activity,"playbackSettings");dialog=ShadowAlertDialog.getLatestAlertDialog();button(dialog.getWindow().getDecorView(),"高级").performClick();assertNotNull(button(dialog.getWindow().getDecorView(),"播放诊断"));assertNotNull(button(dialog.getWindow().getDecorView(),"解码模式"));dialog.dismiss();
        }
    }
    @Test public void largeFontAndVrKeepTouchTargetsInsideTheWindowAndExposeEyeMode()throws Exception{
        for(float scale:new float[]{1f,1.5f,2f})try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=lifecycle.get();Configuration configuration=new Configuration(activity.getResources().getConfiguration());configuration.fontScale=scale;activity.getResources().updateConfiguration(configuration,activity.getResources().getDisplayMetrics());FrameLayout root=build(activity);layout(root,320,800);
            LinearLayout quick=(LinearLayout)get(activity,"quickRow");for(int i=0;i<quick.getChildCount();i++){View child=quick.getChildAt(i);Rect rect=bounds(root,child);assertTrue(child.getWidth()>=48);assertTrue(child.getHeight()>=48);assertTrue(rect.right<=320);assertTrue(rect.bottom<=800);}
            assertTrue(bounds(root,(View)get(activity,"portraitInfo")).bottom<=bounds(root,(View)get(activity,"bottomBar")).top);
            set(activity,"file",null);set(activity,"vrEnabled",true);call(activity,"updateRenderMode");layout(root,852,393);View vr=(View)get(activity,"vrVideo");scenery(vr,true);LinearLayout toolbar=(LinearLayout)get(activity,"vrBar");assertEquals(5,toolbar.getChildCount());
            if(toolbar.getVisibility()==View.VISIBLE){Rect rect=bounds(root,toolbar);assertTrue(rect.top>=bounds(root,(View)get(activity,"topBar")).bottom);assertTrue(rect.bottom<=bounds(root,(View)get(activity,"bottomBar")).top);}
            Button eye=(Button)get(activity,"eyeMode");assertTrue(eye.getContentDescription().toString().contains("单眼 / 双眼"));eye.performClick();assertEquals(true,get(activity,"vrHeadset"));assertTrue(eye.isSelected());eye.performClick();assertEquals(false,get(activity,"vrHeadset"));
            if(scale==1f)snapshot(root,"native-player-vr.png");
        }
    }
    @Test public void actualAutoNextSwitchUsesSemanticCyanAndDisabledTints()throws Exception{
        try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=lifecycle.get();FrameLayout root=build(activity);layout(root,393,852);call(activity,"playbackSettings");AlertDialog dialog=ShadowAlertDialog.getLatestAlertDialog();
            com.google.android.material.materialswitch.MaterialSwitch toggle=dialog.getWindow().getDecorView().findViewWithTag("playerAutoNextSwitch");assertNotNull(toggle);
            int[] checked={android.R.attr.state_enabled,android.R.attr.state_checked},unchecked={android.R.attr.state_enabled},disabled={-android.R.attr.state_enabled,android.R.attr.state_checked};
            assertEquals(net.lumen.media.ui.theme.NativeActionTokens.primary(true),toggle.getTrackTintList().getColorForState(checked,0));
            assertEquals(net.lumen.media.ui.theme.NativeActionTokens.content(true,1,false),toggle.getThumbTintList().getColorForState(checked,0));
            assertEquals(net.lumen.media.ui.theme.NativeActionTokens.surfaceContainerHighest(true),toggle.getTrackTintList().getColorForState(unchecked,0));
            assertEquals(net.lumen.media.ui.theme.NativeActionTokens.onSurfaceVariant(true),toggle.getThumbTintList().getColorForState(unchecked,0));
            assertEquals(31,android.graphics.Color.alpha(toggle.getTrackTintList().getColorForState(disabled,0)));assertEquals(97,android.graphics.Color.alpha(toggle.getThumbTintList().getColorForState(disabled,0)));
            assertEquals(net.lumen.media.ui.theme.NativeActionTokens.primary(true),toggle.getThumbIconTintList().getColorForState(checked,0));assertEquals(net.lumen.media.ui.theme.NativeActionTokens.outlineVariant(true),toggle.getTrackDecorationTintList().getColorForState(unchecked,0));dialog.dismiss();
        }
    }
}
