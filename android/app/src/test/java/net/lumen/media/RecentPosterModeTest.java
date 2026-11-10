package net.lumen.media;

import android.graphics.*;
import android.os.Looper;
import android.view.*;
import android.widget.*;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.*;
import org.robolectric.annotation.*;
import org.robolectric.android.controller.ActivityController;
import okhttp3.mockwebserver.*;
import java.io.*;
import java.lang.reflect.*;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class) @Config(sdk=33,qualifiers="w393dp-h852dp-mdpi") @GraphicsMode(GraphicsMode.Mode.NATIVE)
public class RecentPosterModeTest {
    private Object get(Object target,String name)throws Exception{Field f=target.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(target);}
    private void waitFor(java.util.function.BooleanSupplier ready)throws Exception{long until=System.currentTimeMillis()+6000;while(!ready.getAsBoolean()&&System.currentTimeMillis()<until){Thread.sleep(10);Shadows.shadowOf(Looper.getMainLooper()).idle();}assertTrue(ready.getAsBoolean());}
    private void layout(View root){for(int i=0;i<3;i++){root.measure(View.MeasureSpec.makeMeasureSpec(393,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(852,View.MeasureSpec.EXACTLY));root.layout(0,0,393,852);}}
    private void snapshot(View root,String name)throws Exception{String dir=System.getenv("LUMEN_UI_SCREENSHOTS");if(dir==null)return;File file=new File(dir,name);file.getParentFile().mkdirs();Bitmap image=Bitmap.createBitmap(root.getWidth(),root.getHeight(),Bitmap.Config.ARGB_8888);root.draw(new Canvas(image));try(FileOutputStream out=new FileOutputStream(file)){image.compress(Bitmap.CompressFormat.PNG,100,out);}image.recycle();}
    private okio.Buffer picture(int width,int height){Bitmap image=Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);Canvas canvas=new Canvas(image);Paint paint=new Paint();paint.setShader(new LinearGradient(0,0,width,height,0xff294957,0xff15212c,Shader.TileMode.CLAMP));canvas.drawRect(0,0,width,height,paint);paint.setShader(null);paint.setColor(0xffd9cda8);canvas.drawCircle(width*.7f,height*.2f,Math.min(width,height)*.12f,paint);paint.setColor(0xff476d68);canvas.drawRect(0,height*.6f,width,height,paint);paint.setColor(0xffeef3f5);paint.setTextSize(Math.min(width,height)*.08f);canvas.drawText("COAST JOURNAL",width*.06f,height*.85f,paint);okio.Buffer out=new okio.Buffer();image.compress(Bitmap.CompressFormat.PNG,100,out.outputStream());image.recycle();return out;}
    @Test public void recentCardsRestoreUniformPosterCropWhileResumeKeepsTheVideoThumbnail()throws Exception{
        okio.Buffer poster=picture(240,360),frame=picture(480,270);
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){String path=request.getPath();if(path.equals("/api/preview-poster"))return new MockResponse().setBody(poster.clone());if(path.equals("/api/preview-thumbnail"))return new MockResponse().setBody(frame.clone());if(path.startsWith("/api/continue"))return new MockResponse().setBody("{\"items\":[{\"id\":7,\"title\":\"海岸纪行\",\"resume\":{\"file_id\":70,\"thumbnail\":\"/api/preview-thumbnail\",\"name\":\"Coast.Journal.2160p.mkv\",\"position\":120,\"duration\":600}}]}");return new MockResponse().setBody("{\"items\":[{\"id\":7,\"title\":\"海岸纪行\",\"kind\":\"movie\",\"year\":2024,\"cover\":\"/api/preview-poster\"},{\"id\":8,\"title\":\"山海相逢\",\"kind\":\"movie\",\"year\":2023,\"cover\":\"/api/preview-thumbnail\"}],\"total\":2}");}});server.start();MainActivity page=life.get();page.api=new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456"));page.showLibrary();View root=(View)get(page,"root");waitFor(()->root.findViewWithTag("card:8")!=null&&root.findViewWithTag("continueArtwork:70")!=null);waitFor(page.imageRequests::idle);layout(root);
            for(long id:new long[]{7,8}){LinearLayout card=root.findViewWithTag("card:"+id);ViewGroup cover=(ViewGroup)card.getChildAt(0);ImageView image=(ImageView)cover.getChildAt(0);assertEquals(ImageView.ScaleType.CENTER_CROP,image.getScaleType());assertEquals(Math.round(cover.getWidth()*1.5f),cover.getHeight());}
            ImageView resume=(ImageView)((ViewGroup)root.findViewWithTag("continueArtwork:70")).getChildAt(0);assertEquals(ImageView.ScaleType.FIT_CENTER,resume.getScaleType());assertEquals(page.api.connection.base+"/api/preview-thumbnail",resume.getTag());snapshot(root,"home-resume-and-posters.png");((ScrollView)get(page,"browseScroll")).scrollTo(0,350);layout(root);snapshot(root,"recently-added-restored.png");
        }
    }
}
