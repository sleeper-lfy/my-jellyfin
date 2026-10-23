package net.lumen.media;

import android.os.Looper;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.GraphicsMode;
import org.robolectric.android.controller.ActivityController;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.RecordedRequest;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.BooleanSupplier;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33)
public class MediaDesignTest {
    private void field(Object object,String name,Object value)throws Exception{Field field=object.getClass().getDeclaredField(name);field.setAccessible(true);field.set(object,value);}
    private Object read(Object object,String name)throws Exception{Field field=object.getClass().getDeclaredField(name);field.setAccessible(true);return field.get(object);}
    private void waitMain(BooleanSupplier ready)throws Exception{
        long deadline=System.currentTimeMillis()+6000;
        while(!ready.getAsBoolean()&&System.currentTimeMillis()<deadline){Thread.sleep(15);shadowOf(Looper.getMainLooper()).idle();}
        assertTrue(ready.getAsBoolean());
    }
    @Test @GraphicsMode(GraphicsMode.Mode.NATIVE) public void collectionUpdatesInPlaceAndFailureRestoresPreviousState()throws Exception{
        AtomicBoolean fail=new AtomicBoolean(false);
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){
                assertEquals("/api/works/42/personal",request.getPath());
                return new MockResponse().setResponseCode(fail.get()?500:200).setBody("{\"ok\":true}");
            }});server.start();MainActivity activity=lifecycle.get();
            field(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));
            JSONObject work=new JSONObject().put("id",42).put("title","Selected movie").put("kind","movie").put("favorite",0).put("watchlist",0).put("files",new org.json.JSONArray()).put("file_count",0).put("overview","A long synopsis. ".repeat(200));
            Method render=MainActivity.class.getDeclaredMethod("renderDetail",JSONObject.class);render.setAccessible(true);render.invoke(activity,work);
            LinearLayout root=(LinearLayout)read(activity,"root");
            root.measure(View.MeasureSpec.makeMeasureSpec(360,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(800,View.MeasureSpec.EXACTLY));root.layout(0,0,360,800);shadowOf(Looper.getMainLooper()).idle();
            ScrollView scroll=(ScrollView)read(activity,"detailScroll");scroll.scrollTo(0,100);int position=scroll.getScrollY();assertTrue("page="+scroll.getChildAt(0).getHeight()+", viewport="+scroll.getHeight(),position>0);
            Button favorite=root.findViewWithTag("mark:42:favorite");favorite.performClick();assertTrue(favorite.isSelected());assertFalse(favorite.isEnabled());
            waitMain(favorite::isEnabled);
            assertEquals(1,work.optInt("favorite"));assertEquals("已收藏",favorite.getText().toString());assertSame(root,read(activity,"root"));assertEquals(position,scroll.getScrollY());
            fail.set(true);favorite.performClick();assertFalse(favorite.isSelected());waitMain(favorite::isEnabled);
            assertTrue(favorite.isSelected());assertEquals(1,work.optInt("favorite"));assertSame(root,read(activity,"root"));
        }
    }
    @Test @Config(sdk={26,35}) public void chipRowsWrapAndReflowAfterRemovalWithoutHorizontalOverflow()throws Exception{
        try(ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            MainActivity activity=lifecycle.get();ChipLayout row=new ChipLayout(activity);
            for(int i=0;i<5;i++){
                Button button=new Button(activity);button.setText("Filter "+i);MediaStyle.button(button,false,false,false);row.addView(button,new android.view.ViewGroup.LayoutParams(140,-2));
            }
            row.measure(View.MeasureSpec.makeMeasureSpec(320,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(0,View.MeasureSpec.UNSPECIFIED));row.layout(0,0,320,row.getMeasuredHeight());
            assertTrue(row.getChildAt(2).getTop()>row.getChildAt(0).getTop());
            for(int i=0;i<row.getChildCount();i++){View child=row.getChildAt(i);assertTrue(child.getRight()<=320);assertTrue(child.getHeight()>=MediaStyle.dp(activity,48));}
            row.removeViewAt(0);row.measure(View.MeasureSpec.makeMeasureSpec(320,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(0,View.MeasureSpec.UNSPECIFIED));row.layout(0,0,320,row.getMeasuredHeight());
            assertEquals(0,row.getChildAt(0).getLeft());assertEquals(0,row.getChildAt(0).getTop());
        }
    }
}
