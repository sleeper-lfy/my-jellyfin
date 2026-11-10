package net.lumen.media;

import android.graphics.*;
import android.graphics.drawable.BitmapDrawable;
import android.os.Looper;
import android.view.*;
import android.widget.*;
import org.json.*;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.*;
import org.robolectric.annotation.*;
import org.robolectric.android.controller.ActivityController;
import okhttp3.mockwebserver.*;
import java.io.*;
import java.lang.reflect.*;
import java.util.*;
import java.util.concurrent.*;
import static org.junit.Assert.*;

/** Actual HTTP assets and native layouts, separate from the design-system gallery. */
@RunWith(RobolectricTestRunner.class) @Config(sdk=33,qualifiers="w393dp-h852dp-mdpi") @GraphicsMode(GraphicsMode.Mode.NATIVE)
public class PosterPresentationTest {
    private static final String COAST="/api/assets/coast-poster.png",ORBIT="/api/assets/orbit-poster.png",THUMBNAIL="/api/files/70/thumbnail",UNUSED_RESUME_COVER="/api/assets/resume-work-poster.png";
    private static final class Asset {
        final okio.Buffer bytes;final int width,height,corner;
        Asset(Bitmap bitmap){width=bitmap.getWidth();height=bitmap.getHeight();corner=bitmap.getPixel(3,3);bytes=new okio.Buffer();bitmap.compress(Bitmap.CompressFormat.PNG,100,bytes.outputStream());bitmap.recycle();}
    }
    private Object get(Object target,String name)throws Exception{Field f=target.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(target);}
    private void set(Object target,String name,Object value)throws Exception{Field f=target.getClass().getDeclaredField(name);f.setAccessible(true);f.set(target,value);}
    private void waitFor(java.util.function.BooleanSupplier ready)throws Exception{long until=System.currentTimeMillis()+6000;while(!ready.getAsBoolean()&&System.currentTimeMillis()<until){Thread.sleep(10);Shadows.shadowOf(Looper.getMainLooper()).idle();}assertTrue(ready.getAsBoolean());}
    private void layout(View root){for(int i=0;i<3;i++){root.measure(View.MeasureSpec.makeMeasureSpec(393,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(852,View.MeasureSpec.EXACTLY));root.layout(0,0,393,852);}}
    private void snapshot(View root,String name)throws Exception{
        String dir=System.getenv("LUMEN_POSTER_SCREENSHOTS");if(dir==null)return;File file=new File(dir,name);file.getParentFile().mkdirs();Bitmap image=Bitmap.createBitmap(root.getWidth(),root.getHeight(),Bitmap.Config.ARGB_8888);root.draw(new Canvas(image));try(FileOutputStream out=new FileOutputStream(file)){image.compress(Bitmap.CompressFormat.PNG,100,out);}image.recycle();
    }
    /** Fictional film posters and a landscape frame; no diagnostic borders or user photos. */
    private Asset picture(int width,int height,boolean night,boolean poster){
        Bitmap image=Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);Canvas canvas=new Canvas(image);Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        paint.setShader(new LinearGradient(0,0,0,height,night?0xff15243e:0xff8eb8c6,night?0xff5c5b70:0xffe1c9a2,Shader.TileMode.CLAMP));canvas.drawRect(0,0,width,height,paint);paint.setShader(null);
        paint.setColor(night?0xffe7e6d5:0xfff6deb1);canvas.drawCircle(width*.72f,height*.22f,width*.12f,paint);
        if(night){paint.setColor(0xffe6e5d8);for(int i=0;i<19;i++)canvas.drawCircle(width*(.06f+(i*37%85)/100f),height*(.04f+(i*19%41)/100f),Math.max(1,width*.004f),paint);}
        Path ridge=new Path();ridge.moveTo(0,height*.61f);ridge.lineTo(width*.2f,height*.36f);ridge.lineTo(width*.43f,height*.55f);ridge.lineTo(width*.65f,height*.42f);ridge.lineTo(width,height*.62f);ridge.lineTo(width,height);ridge.lineTo(0,height);ridge.close();paint.setColor(night?0xff30405b:0xff577d7d);canvas.drawPath(ridge,paint);
        paint.setShader(new LinearGradient(0,height*.64f,0,height,night?0xff263349:0xff668e98,night?0xff121c30:0xff264d61,Shader.TileMode.CLAMP));canvas.drawRect(0,height*.64f,width,height,paint);paint.setShader(null);
        Path shore=new Path();shore.moveTo(0,height*.74f);shore.cubicTo(width*.22f,height*.69f,width*.46f,height*.9f,width,height*.76f);shore.lineTo(width,height);shore.lineTo(0,height);shore.close();paint.setColor(night?0xff192839:0xffd6c49e);canvas.drawPath(shore,paint);
        if(poster){paint.setColor(0xfff5eee2);paint.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));paint.setTextSize(width*.072f);canvas.drawText(night?"NIGHT ORBIT":"COAST JOURNAL",width*.07f,height*.84f,paint);paint.setTextSize(width*.035f);canvas.drawText("A LUMEN ORIGINAL",width*.07f,height*.9f,paint);}
        return new Asset(image);
    }
    private JSONObject work(long id,String title,String kind,String cover)throws Exception{return new JSONObject().put("id",id).put("title",title).put("kind",kind).put("year",2025).put("cover",cover).put("file_count",1).put("favorite",0);}
    private String catalog(JSONObject... works)throws Exception{JSONArray items=new JSONArray();for(JSONObject work:works)items.put(work);return new JSONObject().put("items",items).put("total",works.length).toString();}
    private ImageView poster(View root,long id){ViewGroup card=root.findViewWithTag("card:"+id);return (ImageView)((ViewGroup)card.getChildAt(0)).getChildAt(0);}
    private Rect bounds(View view){return new Rect(view.getLeft(),view.getTop(),view.getRight(),view.getBottom());}
    private void assertPosterGeometry(ImageView image){View cover=(View)image.getParent();assertEquals(Math.round(cover.getWidth()*1.5f),cover.getHeight());assertEquals(cover.getWidth(),image.getWidth());assertEquals(cover.getHeight(),image.getHeight());assertTrue(image.getWidth()>0);}
    private void assertLoaded(MainActivity page,ImageView image,String path,Asset asset,ImageView.ScaleType mode){
        assertEquals(page.api.connection.base+path,image.getTag());assertTrue("HTTP asset must replace the placeholder",image.getDrawable() instanceof BitmapDrawable);Bitmap bitmap=((BitmapDrawable)image.getDrawable()).getBitmap();assertEquals(asset.width,bitmap.getWidth());assertEquals(asset.height,bitmap.getHeight());assertEquals(asset.corner,bitmap.getPixel(3,3));assertEquals(mode,image.getScaleType());
        RectF mapped=new RectF(0,0,bitmap.getWidth(),bitmap.getHeight());image.getImageMatrix().mapRect(mapped);
        if(mode==ImageView.ScaleType.CENTER_CROP){assertTrue(mapped.left<=.1f&&mapped.top<=.1f&&mapped.right>=image.getWidth()-.1f&&mapped.bottom>=image.getHeight()-.1f);}else{assertTrue(mapped.left>=-.1f&&mapped.top>=-.1f&&mapped.right<=image.getWidth()+.1f&&mapped.bottom<=image.getHeight()+.1f);}
    }
    @Test public void homeRecentMovieAndVrUseRealPostersWhileContinueRequestsOnlyTheFileThumbnail()throws Exception{
        Asset coast=picture(240,400,false,true),orbit=picture(300,450,true,true),frame=picture(640,360,false,false);Set<String> requested=ConcurrentHashMap.newKeySet();
        String catalog=catalog(work(7,"海岸纪行","movie",COAST),work(8,"星夜环游","vr",ORBIT),work(9,"群岛来信","movie",COAST),work(10,"月海远航","vr",ORBIT));
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){String path=request.getPath();requested.add(path);assertEquals("Bearer abcdefghijklmnopqrstuvwxyz123456",request.getHeader("Authorization"));if(path.equals(COAST))return new MockResponse().setBody(coast.bytes.clone());if(path.equals(ORBIT))return new MockResponse().setBody(orbit.bytes.clone());if(path.equals(THUMBNAIL))return new MockResponse().setBody(frame.bytes.clone());if(path.startsWith("/api/continue"))return new MockResponse().setBody("{\"items\":[{\"id\":99,\"title\":\"沿海的午后\",\"cover\":\""+UNUSED_RESUME_COVER+"\",\"resume\":{\"file_id\":70,\"thumbnail\":\""+THUMBNAIL+"\",\"name\":\"Coast.Journal.2160p.mkv\",\"position\":120,\"duration\":600}}]}");return new MockResponse().setBody(catalog);}});server.start();MainActivity page=life.get();page.api=new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456"));page.showLibrary();View root=(View)get(page,"root");waitFor(()->root.findViewWithTag("card:10")!=null&&root.findViewWithTag("continueArtwork:70")!=null);waitFor(page.imageRequests::idle);layout(root);
            for(long id:new long[]{7,8,9,10}){ImageView image=poster(root,id);assertPosterGeometry(image);assertLoaded(page,image,id%2==1?COAST:ORBIT,id%2==1?coast:orbit,ImageView.ScaleType.CENTER_CROP);assertEquals(page.getString(R.string.catalog_poster_description,page.browseRecords.get(id).optString("title")),image.getContentDescription());}
            ImageView resume=(ImageView)((ViewGroup)root.findViewWithTag("continueArtwork:70")).getChildAt(0);assertLoaded(page,resume,THUMBNAIL,frame,ImageView.ScaleType.FIT_CENTER);assertTrue(requested.contains(COAST));assertTrue(requested.contains(ORBIT));assertTrue(requested.contains(THUMBNAIL));assertFalse("Resume must never request its work cover",requested.contains(UNUSED_RESUME_COVER));assertTrue(requested.stream().anyMatch(path->path.startsWith("/api/works?")));
            snapshot(root,"poster-home-continue-thumbnail.png");((ScrollView)get(page,"browseScroll")).scrollTo(0,root.findViewWithTag("listHeading").getTop());layout(root);snapshot(root,"poster-home-recent-movie-vr.png");
        }
    }
    @Test public void libraryMovieAndVrCategoriesCropPostersAndOtherKindsKeepTheirExistingFitMode()throws Exception{
        Asset coast=picture(240,400,false,true),orbit=picture(300,450,true,true);
        for(String kind:new String[]{"movie","vr","series","fans"}){
            Set<String> requested=ConcurrentHashMap.newKeySet();String catalog=catalog(work(7,"海岸纪行",kind,COAST),work(8,"星夜环游",kind,ORBIT));
            try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
                server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){String path=request.getPath();requested.add(path);if(path.equals(COAST))return new MockResponse().setBody(coast.bytes.clone());if(path.equals(ORBIT))return new MockResponse().setBody(orbit.bytes.clone());return new MockResponse().setBody(catalog);}});server.start();MainActivity page=life.get();page.api=new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456"));set(page,"mainPage","library");page.kind=kind;page.showLibrary();View root=(View)get(page,"root");waitFor(()->root.findViewWithTag("card:8")!=null);waitFor(page.imageRequests::idle);layout(root);boolean cinema=kind.equals("movie")||kind.equals("vr");
                for(long id:new long[]{7,8}){ImageView image=poster(root,id);assertPosterGeometry(image);assertLoaded(page,image,id==7?COAST:ORBIT,id==7?coast:orbit,cinema?ImageView.ScaleType.CENTER_CROP:ImageView.ScaleType.FIT_CENTER);}
                assertTrue(requested.stream().anyMatch(path->path.startsWith("/api/works?")&&path.contains("kind="+kind)));assertFalse(requested.stream().anyMatch(path->path.startsWith("/api/continue")));if(cinema)snapshot(root,"poster-library-"+kind+".png");
            }
        }
    }
    @Test public void absentAndFailedPostersKeepTheirTwoByThreePlaceholdersWithoutUsingAThumbnail()throws Exception{
        CountDownLatch failedPosterRequested=new CountDownLatch(1),finishFailure=new CountDownLatch(1);Set<String> requested=ConcurrentHashMap.newKeySet();String missing="/api/assets/missing-poster.png";
        String catalog=catalog(work(7,"尚未补齐的海报","movie","").put("thumbnail","/api/files/80/thumbnail"),work(8,"星夜环游","vr",missing));
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request)throws InterruptedException{String path=request.getPath();requested.add(path);if(path.equals(missing)){failedPosterRequested.countDown();finishFailure.await();return new MockResponse().setResponseCode(404);}return new MockResponse().setBody(catalog);}});server.start();MainActivity page=life.get();page.api=new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456"));set(page,"mainPage","library");page.showLibrary();View root=(View)get(page,"root");
            try{
                waitFor(()->root.findViewWithTag("card:8")!=null);assertTrue(failedPosterRequested.await(3,TimeUnit.SECONDS));layout(root);ImageView absent=poster(root,7),pending=poster(root,8);assertPosterGeometry(absent);assertPosterGeometry(pending);Rect imageBefore=bounds(pending),cardBefore=bounds(root.findViewWithTag("card:8"));assertEquals(page.getString(R.string.catalog_poster_unavailable,"尚未补齐的海报"),absent.getContentDescription());assertEquals(page.getString(R.string.catalog_poster_loading,"星夜环游"),pending.getContentDescription());assertTrue(absent.getDrawable() instanceof MediaStyle.ArtworkPlaceholder);assertTrue(pending.getDrawable() instanceof MediaStyle.ArtworkPlaceholder);
                finishFailure.countDown();waitFor(page.imageRequests::idle);layout(root);assertEquals(imageBefore,bounds(pending));assertEquals(cardBefore,bounds(root.findViewWithTag("card:8")));assertPosterGeometry(pending);assertTrue(pending.getDrawable() instanceof MediaStyle.ArtworkPlaceholder);assertEquals(page.getString(R.string.catalog_poster_unavailable,"星夜环游"),pending.getContentDescription());assertEquals(ImageView.ScaleType.CENTER_CROP,absent.getScaleType());assertEquals(ImageView.ScaleType.CENTER_CROP,pending.getScaleType());assertFalse(requested.stream().anyMatch(path->path.contains("/thumbnail")));snapshot(root,"poster-library-unavailable.png");
            }finally{finishFailure.countDown();}
        }
    }
}
