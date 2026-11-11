package net.lumen.media;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import androidx.core.graphics.ColorUtils;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.InsetDrawable;
import android.graphics.drawable.LayerDrawable;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import com.google.android.material.shape.MaterialShapeDrawable;
import java.util.Arrays;
import net.lumen.media.ui.theme.NativeActionTokens;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.GraphicsMode;
import static org.junit.Assert.*;

/** Platform dialog actions keep their real painted fill in sync with enabled state. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w393dp-h852dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
public class DialogActionStateTest {
    private String chain(Drawable drawable){
        if(drawable==null)return "null";
        String info=drawable.getClass().getSimpleName()+Arrays.toString(drawable.getState());
        if(drawable instanceof MaterialShapeDrawable){MaterialShapeDrawable shape=(MaterialShapeDrawable)drawable;info+=" fill="+Integer.toHexString(shape.getFillColor().getColorForState(shape.getState(),0));}
        if(drawable instanceof InsetDrawable)info+=" -> "+chain(((InsetDrawable)drawable).getDrawable());
        if(drawable instanceof LayerDrawable){LayerDrawable layer=(LayerDrawable)drawable;for(int i=0;i<layer.getNumberOfLayers();i++)info+=" ["+i+"] "+chain(layer.getDrawable(i));}
        return info;
    }
    private int background(Button button,int canvasColor){
        Bitmap bitmap=Bitmap.createBitmap(button.getWidth(),button.getHeight(),Bitmap.Config.ARGB_8888);bitmap.eraseColor(canvasColor);
        Drawable drawable=button.getBackground();android.graphics.Rect old=new android.graphics.Rect(drawable.getBounds());
        drawable.setBounds(0,0,bitmap.getWidth(),bitmap.getHeight());drawable.draw(new Canvas(bitmap));drawable.setBounds(old);
        int pixel=bitmap.getPixel(bitmap.getWidth()/2,bitmap.getHeight()/2);bitmap.recycle();return pixel;
    }
    private String state(float scale,int width,Button apply){return "scale="+scale+" width="+width+" enabled="+apply.isEnabled()+" text="+Integer.toHexString(apply.getCurrentTextColor())+" view="+Arrays.toString(apply.getDrawableState())+" background="+chain(apply.getBackground());}
    private void enabledPrimary(float scale,int width,Button apply){
        String detail=state(scale,width,apply);assertTrue(detail,apply.isEnabled());assertEquals(detail,NativeActionTokens.content(true,1,false),apply.getCurrentTextColor());assertEquals(detail,255,Color.alpha(apply.getCurrentTextColor()));assertEquals(detail,NativeActionTokens.container(true,1,false),background(apply,Color.TRANSPARENT));
    }
    @Test public void dialogFillAndTextFollowEnabledDisabledEnabledAcrossFontsAndWidths()throws Exception {
        for(float scale:new float[]{1f,1.5f})for(int width:new int[]{393,320}){
            try(ActivityController<Activity> lifecycle=Robolectric.buildActivity(Activity.class).setup()){
                Activity activity=lifecycle.get();Configuration cfg=new Configuration(activity.getResources().getConfiguration());cfg.fontScale=scale;activity.getResources().updateConfiguration(cfg,activity.getResources().getDisplayMetrics());
                LinearLayout fields=new LinearLayout(activity);fields.setOrientation(LinearLayout.VERTICAL);for(int i=0;i<8;i++){EditText input=new EditText(activity);input.setText("筛选条件 "+i);fields.addView(input);}ScrollView scroll=new ScrollView(activity);scroll.addView(fields);
                AlertDialog dialog=new AlertDialog.Builder(activity).setTitle("筛选媒体库").setView(scroll).setPositiveButton("应用",null).setNegativeButton("取消",null).setNeutralButton("重置",null).create();dialog.show();
                try{
                    MediaStyle.sheet(dialog);Button apply=dialog.getButton(AlertDialog.BUTTON_POSITIVE);MediaStyle.button(apply,true,false,false);View decor=dialog.getWindow().getDecorView();
                    for(int pass=0;pass<3;pass++){decor.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(804,View.MeasureSpec.AT_MOST));decor.layout(0,0,width,decor.getMeasuredHeight());}
                    enabledPrimary(scale,width,apply);
                    apply.setEnabled(false);
                    String detail=state(scale,width,apply);assertFalse(detail,apply.isEnabled());assertEquals(detail,NativeActionTokens.disabledContent(true),apply.getCurrentTextColor());assertEquals(detail,97,Color.alpha(apply.getCurrentTextColor()));
                    int disabled=background(apply,Color.TRANSPARENT);assertEquals(detail,31,Color.alpha(disabled));
                    int surface=NativeActionTokens.surfaceContainer(true),expected=ColorUtils.compositeColors(NativeActionTokens.disabledContainer(true,1),surface),painted=background(apply,surface);
                    assertTrue(detail,Math.abs(Color.red(expected)-Color.red(painted))<=1);assertTrue(detail,Math.abs(Color.green(expected)-Color.green(painted))<=1);assertTrue(detail,Math.abs(Color.blue(expected)-Color.blue(painted))<=1);
                    apply.setEnabled(true);
                    enabledPrimary(scale,width,apply);
                }finally{dialog.dismiss();}
            }
        }
    }
}
