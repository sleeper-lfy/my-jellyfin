package net.lumen.media;

import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.drawable.Drawable;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import com.google.android.material.button.MaterialButton;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.GraphicsMode;
import static org.junit.Assert.*;

/** Check rendered glyph centers after data/state updates, including narrow enlarged layouts. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w393dp-h852dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
public class MobileAlignmentTest {
    private void layout(View view,int width,int height){
        for(int i=0;i<3;i++){view.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(height,View.MeasureSpec.AT_MOST));view.layout(0,0,width,view.getMeasuredHeight());}
    }
    private void scale(MainActivity activity,float scale){Configuration config=new Configuration(activity.getResources().getConfiguration());config.fontScale=scale;activity.getResources().updateConfiguration(config,activity.getResources().getDisplayMetrics());}
    private Object read(Object object,String name)throws Exception{Field field=object.getClass().getDeclaredField(name);field.setAccessible(true);return field.get(object);}
    private void invoke(Object object,String name,Class<?>[] types,Object... args)throws Exception{Method method=object.getClass().getDeclaredMethod(name,types);method.setAccessible(true);method.invoke(object,args);}
    private void centeredGlyphs(TextView text){
        assertNotNull(text.getLayout());
        float contentLeft=text.getCompoundPaddingLeft(),expected=text.getWidth()/2f;
        for(int line=0;line<text.getLayout().getLineCount();line++){
            float center=contentLeft+(text.getLayout().getLineLeft(line)+text.getLayout().getLineRight(line))/2f;
            assertEquals("Text must share its cell/icon center: "+text.getText(),expected,center,1f);
        }
    }
    private void stacked(MaterialButton button){
        assertEquals(MaterialButton.ICON_GRAVITY_TEXT_TOP,button.getIconGravity());
        assertEquals(View.TEXT_ALIGNMENT_CENTER,button.getTextAlignment());
        Drawable top=button.getCompoundDrawablesRelative()[1];assertNotNull(top);assertSame(button.getIcon(),top);
        assertTrue(button.getHeight()>=48);assertTrue(button.getWidth()>=48);centeredGlyphs(button);
    }
    private void snapshot(View view,String name)throws Exception{
        String directory=System.getenv("LUMEN_ALIGNMENT_SCREENSHOTS");if(directory==null)return;
        File output=new File(directory,name+".png");output.getParentFile().mkdirs();Bitmap image=Bitmap.createBitmap(view.getWidth(),view.getHeight(),Bitmap.Config.ARGB_8888);view.draw(new Canvas(image));try(FileOutputStream stream=new FileOutputStream(output)){image.compress(Bitmap.CompressFormat.PNG,100,stream);}image.recycle();
    }
    @Test public void profileCountsAndCaptionsShareColumnCentersAfterNumbersArrive()throws Exception{
        try(ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            MainActivity activity=life.get();
            for(float font:new float[]{1f,1.5f})for(int direction:new int[]{View.LAYOUT_DIRECTION_LTR,View.LAYOUT_DIRECTION_RTL}){
                scale(activity,font);View profile=BiliMainUi.profile(activity);profile.setLayoutDirection(direction);ViewGroup totals=profile.findViewWithTag("mineTotals");
                String[] keys={"all","favorite","watchlist"},values={"128","36","12"};
                for(int i=0;i<keys.length;i++){TextView number=profile.findViewWithTag("mineTotal:"+keys[i]);number.setText(values[i]);}
                layout(profile,font==1f?393:320,852);
                for(int i=0;i<totals.getChildCount();i++)if(totals.getChildAt(i) instanceof ViewGroup){ViewGroup cell=(ViewGroup)totals.getChildAt(i);TextView number=(TextView)cell.getChildAt(0),caption=(TextView)cell.getChildAt(1);assertEquals(number.getWidth(),caption.getWidth());assertEquals(cell.getWidth(),number.getWidth());centeredGlyphs(number);centeredGlyphs(caption);}
                if(direction==View.LAYOUT_DIRECTION_LTR)snapshot(profile,"mine-totals-font"+font);
            }
        }
    }
    @Test public void detailActionsRemainStackedAndCenteredAfterRatingAndFavoriteRefresh()throws Exception{
        try(ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            MainActivity activity=life.get();
            JSONObject work=new JSONObject().put("id",7).put("title","海岸纪行").put("kind","movie").put("favorite",0).put("watchlist",0).put("rating",JSONObject.NULL).put("file_count",0).put("files",new JSONArray());
            for(float font:new float[]{1f,1.5f}){
                scale(activity,font);invoke(activity,"renderDetail",new Class<?>[]{JSONObject.class},work);View root=(View)read(activity,"root");
                for(int direction:new int[]{View.LAYOUT_DIRECTION_LTR,View.LAYOUT_DIRECTION_RTL}){
                root.setLayoutDirection(direction);
                work.put("rating",8).put("favorite",1).put("watchlist",1);
                invoke(activity,"refreshPersonalButtons",new Class<?>[]{JSONObject.class,JSONObject.class},work,new JSONObject().put("rating",8).put("favorite",1).put("watchlist",1));
                layout(root,font==1f?393:320,1100);ViewGroup actions=root.findViewWithTag("detailPersonalActions");assertEquals(3,actions.getChildCount());
                for(int i=0;i<actions.getChildCount();i++)stacked((MaterialButton)actions.getChildAt(i));
                work.put("rating",JSONObject.NULL).put("favorite",0).put("watchlist",0);
                invoke(activity,"refreshPersonalButtons",new Class<?>[]{JSONObject.class,JSONObject.class},work,new JSONObject().put("rating",JSONObject.NULL).put("favorite",0).put("watchlist",0));
                layout(root,font==1f?393:320,1100);for(int i=0;i<actions.getChildCount();i++)stacked((MaterialButton)actions.getChildAt(i));
                if(direction==View.LAYOUT_DIRECTION_LTR)snapshot(root,"detail-actions-font"+font);
                }
            }
        }
    }
    @Test public void mineShortcutIconsAndLabelsShareCentersAtNarrowLargeFont()throws Exception{
        try(ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            MainActivity activity=life.get();scale(activity,1.5f);String[] labels={"收藏","想看","智能片单","观影统计"},icons={"heart","bookmark","smart_playlist","statistics"};Button[] buttons=new Button[labels.length];
            for(int i=0;i<buttons.length;i++){buttons[i]=MediaStyle.action(activity);buttons[i].setText(labels[i]);BiliMainUi.lightAction(buttons[i],icons[i],false);}
            View card=BiliMainUi.quickGrid(activity,buttons);layout(card,320,300);
            for(Button button:buttons)stacked((MaterialButton)button);
            snapshot(card,"mine-shortcuts-font1.5");
        }
    }
}
