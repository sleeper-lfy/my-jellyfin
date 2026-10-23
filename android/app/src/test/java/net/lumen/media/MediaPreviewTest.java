package net.lumen.media;

import android.app.AlertDialog;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Shader;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import org.json.JSONArray;
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
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.function.BooleanSupplier;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

/** Native Android drawing of the actual activity, using isolated sample API records. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w393dp-h851dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
public class MediaPreviewTest {
    private void field(Object object,String name,Object value)throws Exception{Field field=object.getClass().getDeclaredField(name);field.setAccessible(true);field.set(object,value);}
    private void call(MainActivity activity,String name)throws Exception{Method method=MainActivity.class.getDeclaredMethod(name);method.setAccessible(true);method.invoke(activity);}
    private void idleUntil(BooleanSupplier ready)throws Exception{
        long deadline=System.currentTimeMillis()+6000;
        while(!ready.getAsBoolean()&&System.currentTimeMillis()<deadline){Thread.sleep(15);shadowOf(Looper.getMainLooper()).idle();}
        assertTrue(ready.getAsBoolean());
    }
    private void layout(View root,int width,int height){
        for(int pass=0;pass<3;pass++){root.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(height,View.MeasureSpec.EXACTLY));root.layout(0,0,width,height);}
    }
    private void snapshot(View root,String name)throws Exception{
        String directory=System.getenv("LUMEN_UI_SCREENSHOTS");if(directory==null||directory.isEmpty())return;
        Bitmap image=Bitmap.createBitmap(root.getWidth(),root.getHeight(),Bitmap.Config.ARGB_8888);Canvas canvas=new Canvas(image);canvas.drawColor(0xff101010);root.draw(canvas);
        File output=new File(directory,name);assertTrue(output.getParentFile().isDirectory()||output.getParentFile().mkdirs());
        try(FileOutputStream stream=new FileOutputStream(output)){assertTrue(image.compress(Bitmap.CompressFormat.PNG,100,stream));}image.recycle();
    }
    private int pictures(View view){
        int count=view instanceof ImageView&&((ImageView)view).getDrawable()!=null?1:0;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++)count+=pictures(((ViewGroup)view).getChildAt(i));return count;
    }
    @Test public void libraryFilterSheetAndDetailRenderWithinPhoneWidth()throws Exception{
        Bitmap poster=Bitmap.createBitmap(300,450,Bitmap.Config.ARGB_8888);Canvas canvas=new Canvas(poster);Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        paint.setShader(new LinearGradient(0,0,300,450,0xff28768c,0xff111c2b,Shader.TileMode.CLAMP));canvas.drawRect(0,0,300,450,paint);paint.setShader(null);paint.setColor(0xffb7d6df);paint.setStrokeWidth(1);
        canvas.drawLine(0,320,140,190,paint);canvas.drawLine(140,190,300,350,paint);paint.setStyle(Paint.Style.STROKE);canvas.drawCircle(220,75,30,paint);paint.setStyle(Paint.Style.FILL);paint.setTextSize(14);canvas.drawText("LUMEN · UI PREVIEW",57,390,paint);
        ByteArrayOutputStream encoded=new ByteArrayOutputStream();poster.compress(Bitmap.CompressFormat.PNG,100,encoded);poster.recycle();byte[] cover=encoded.toByteArray();
        JSONArray works=new JSONArray();String[] titles={"海岸纪行","森林之声","城市之夜","远方灯塔","群星之间","大地之歌"};
        for(int i=0;i<titles.length;i++)works.put(new JSONObject().put("id",i+1).put("title",titles[i]).put("kind","movie").put("year",2024).put("favorite",i%2).put("watchlist",0).put("file_count",1).put("community_rating",8.4).put("rating",i==0?7:JSONObject.NULL).put("cover","/api/works/"+(i+1)+"/cover"));
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){
                if(request.getPath().endsWith("/cover"))return new MockResponse().setHeader("Content-Type","image/png").setBody(new okio.Buffer().write(cover));
                if(request.getPath().startsWith("/api/filters"))return new MockResponse().setBody("{\"tags\":[\"纪录片\",\"旅行\"],\"actors\":[\"林遥\",\"周宁\"],\"years\":[2024,2023]}");
                return new MockResponse().setBody("{\"items\":"+works+",\"total\":"+works.length()+"}");
            }});server.start();MainActivity activity=lifecycle.get();field(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));field(activity,"kind","movie");call(activity,"showLibrary");
            View root=((ViewGroup)activity.findViewById(android.R.id.content)).getChildAt(0);View libraryRoot=root;idleUntil(()->pictures(libraryRoot)>=6);layout(root,393,851);
            assertNotNull(root.findViewWithTag("card:1"));View first=root.findViewWithTag("card:1");View last=root.findViewWithTag("card:2");assertEquals(first.getTop(),last.getTop());assertTrue(last.getRight()<=393);
            snapshot(root,"ui-android-library.png");
            field(activity,"tagFilter","纪录片");field(activity,"actorFilter","林遥");field(activity,"yearFilter","2024");call(activity,"showFilters");
            AlertDialog dialog=org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog();shadowOf(Looper.getMainLooper()).idle();View sheet=dialog.getWindow().getDecorView();sheet.measure(View.MeasureSpec.makeMeasureSpec(393,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(803,View.MeasureSpec.AT_MOST));layout(sheet,393,sheet.getMeasuredHeight());snapshot(sheet,"ui-android-filters.png");dialog.dismiss();
            JSONObject detail=new JSONObject(works.getJSONObject(0).toString()).put("favorite",1).put("position",90).put("resume_file_id",10)
                .put("overview","沿着海岸线向北，穿过清晨的港口与安静的山林。本页使用独立测试数据预览界面。")
                .put("tags",new JSONArray().put("纪录片").put("旅行")).put("actors",new JSONArray().put(new JSONObject().put("name","林遥")).put(new JSONObject().put("name","周宁")))
                .put("files",new JSONArray().put(new JSONObject().put("id",10).put("name","海岸纪行.mp4").put("duration",5600)));
            Method render=MainActivity.class.getDeclaredMethod("renderDetail",JSONObject.class);render.setAccessible(true);render.invoke(activity,detail);root=((ViewGroup)activity.findViewById(android.R.id.content)).getChildAt(0);layout(root,393,851);
            assertTrue(root.findViewWithTag("mark:1:favorite").isSelected());snapshot(root,"ui-android-detail.png");
        }
    }
}
