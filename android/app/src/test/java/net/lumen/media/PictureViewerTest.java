package net.lumen.media;

import android.app.Dialog;
import android.graphics.Bitmap;
import android.util.LruCache;
import android.view.View;
import android.view.ViewGroup;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.shadows.ShadowDialog;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33)
public class PictureViewerTest {
    private View description(View view,String wanted){
        if(wanted.contentEquals(view.getContentDescription()==null?"":view.getContentDescription()))return view;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){
            View found=description(((ViewGroup)view).getChildAt(i),wanted);if(found!=null)return found;
        }
        return null;
    }
    @Test public void coverOpensZoomViewerAndKeepsDetailAndActorPortrait()throws Exception{
        try(ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            MainActivity activity=lifecycle.get();
            Field apiField=MainActivity.class.getDeclaredField("api");apiField.setAccessible(true);
            Api api=new Api(new Connection("http://127.0.0.1:8097","abcdefghijklmnopqrstuvwxyz123456"));apiField.set(activity,api);
            Field cacheField=MainActivity.class.getDeclaredField("pictures");cacheField.setAccessible(true);
            @SuppressWarnings("unchecked") LruCache<String,Bitmap> cache=(LruCache<String,Bitmap>)cacheField.get(activity);
            cache.put(api.connection.base+"/cover",Bitmap.createBitmap(100,150,Bitmap.Config.ARGB_8888));
            cache.put(api.connection.base+"/face",Bitmap.createBitmap(100,130,Bitmap.Config.ARGB_8888));
            JSONObject work=new JSONObject("{\"id\":1,\"title\":\"Sample\",\"kind\":\"movie\",\"cover\":\"/cover\",\"files\":[],\"actors\":[{\"name\":\"Sample Actress\",\"photo\":\"/face\"}]}");
            Method render=MainActivity.class.getDeclaredMethod("renderDetail",JSONObject.class);render.setAccessible(true);render.invoke(activity,work);
            View content=activity.findViewById(android.R.id.content);View cover=description(content,"放大封面：Sample");
            assertNotNull(cover);assertNotNull(description(content,"演员头像：Sample Actress"));
            cover.performClick();Dialog viewer=ShadowDialog.getLatestDialog();assertNotNull(viewer);assertTrue(viewer.isShowing());
            assertNotNull(findZoom(viewer.getWindow().getDecorView()));viewer.dismiss();
            Field detailId=MainActivity.class.getDeclaredField("detailId");detailId.setAccessible(true);
            assertEquals(1L,detailId.getLong(activity));assertSame(cover,description(activity.findViewById(android.R.id.content),"放大封面：Sample"));
        }
    }
    private View findZoom(View view){
        if(view instanceof ZoomImage)return view;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){View result=findZoom(((ViewGroup)view).getChildAt(i));if(result!=null)return result;}
        return null;
    }
}
