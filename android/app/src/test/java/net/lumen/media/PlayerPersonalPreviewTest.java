package net.lumen.media;

import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.view.View;
import android.widget.Button;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.GraphicsMode;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class) @Config(sdk=33) @GraphicsMode(GraphicsMode.Mode.NATIVE)
public class PlayerPersonalPreviewTest {
    private Field field(String name)throws Exception{Field field=PlayerActivity.class.getDeclaredField(name);field.setAccessible(true);return field;}
    @Test public void playerActionsRenderInPortraitAndLandscapeVr()throws Exception{
        try(ActivityController<PlayerActivity> lifecycle=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=lifecycle.get();Method build=PlayerActivity.class.getDeclaredMethod("buildPlayerUi",android.content.SharedPreferences.class);build.setAccessible(true);build.invoke(activity,activity.getSharedPreferences("playback",0));
            field("work").set(activity,new JSONObject("{\"id\":1,\"title\":\"山海纪行 · 独立示例\",\"favorite\":1,\"liked\":1,\"disliked\":0,\"rating\":9}"));field("file").set(activity,new JSONObject().put("id",10));
            Method refresh=PlayerActivity.class.getDeclaredMethod("refreshPersonal");refresh.setAccessible(true);refresh.invoke(activity);
            ((android.widget.TextView)field("title").get(activity)).setText("山海纪行 · 独立示例");
            ((android.widget.TextView)field("status").get(activity)).setText("播放器界面预览 · 无真实媒体");
            View root=(View)field("root").get(activity);
            for(int index=0;index<2;index++){
                ((View)field("vrBar").get(activity)).setVisibility(index==1?View.VISIBLE:View.GONE);
                int width=index==0?393:851,height=index==0?851:393;
                for(int pass=0;pass<3;pass++){root.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(height,View.MeasureSpec.EXACTLY));root.layout(0,0,width,height);}
                assertTrue(((Button)field("personalFavorite").get(activity)).isSelected());assertTrue(((Button)field("personalLiked").get(activity)).isSelected());assertEquals("9 分",((Button)field("personalRating").get(activity)).getText().toString());
                String directory=System.getenv("LUMEN_UI_SCREENSHOTS");if(directory==null)continue;
                Bitmap image=Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);Canvas canvas=new Canvas(image);canvas.drawColor(0xff000000);root.draw(canvas);File output=new File(directory,index==0?"player-personal-android.png":"player-personal-android-vr.png");assertTrue(output.getParentFile().isDirectory()||output.getParentFile().mkdirs());try(FileOutputStream stream=new FileOutputStream(output)){assertTrue(image.compress(Bitmap.CompressFormat.PNG,100,stream));}image.recycle();
            }
        }
    }
}
