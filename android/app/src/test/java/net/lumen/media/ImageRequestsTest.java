package net.lumen.media;

import android.graphics.Bitmap;
import android.os.Looper;
import android.util.LruCache;
import android.widget.ImageView;
import java.lang.reflect.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.function.BooleanSupplier;
import okhttp3.mockwebserver.*;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.*;
import org.robolectric.annotation.Config;
import org.robolectric.android.controller.ActivityController;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

@RunWith(RobolectricTestRunner.class) @Config(sdk=33)
public class ImageRequestsTest {
    private void waitFor(BooleanSupplier test)throws Exception{long end=System.currentTimeMillis()+4000;while(!test.getAsBoolean()&&System.currentTimeMillis()<end){Thread.sleep(10);shadowOf(Looper.getMainLooper()).idle();}assertTrue(test.getAsBoolean());}
    @Test public void blockedImagesDoNotBlockAnActualActivityOperation()throws Exception{
        CountDownLatch images=new CountDownLatch(2),release=new CountDownLatch(1);AtomicBoolean operation=new AtomicBoolean();
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> lifecycle=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request)throws InterruptedException{
                if(request.getPath().contains("cover")){images.countDown();release.await(4,TimeUnit.SECONDS);return new MockResponse().setResponseCode(404);}
                return new MockResponse().setBody("{}");
            }});server.start();MainActivity activity=lifecycle.get();Api api=new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456"));
            Field connection=MainActivity.class.getDeclaredField("api");connection.setAccessible(true);connection.set(activity,api);
            Method image=MainActivity.class.getDeclaredMethod("loadImage",ImageView.class,String.class);image.setAccessible(true);
            try{
                for(int i=0;i<8;i++)image.invoke(activity,new ImageView(activity),"/api/works/"+i+"/cover");
                assertTrue(images.await(2,TimeUnit.SECONDS));
                Method request=MainActivity.class.getDeclaredMethod("request",MainActivity.Work.class,MainActivity.Result.class);request.setAccessible(true);
                request.invoke(activity,(MainActivity.Work)()->api.get("/api/works"),(MainActivity.Result)result->operation.set(true));
                waitFor(operation::get);assertEquals(1,release.getCount());
            }finally{release.countDown();}
        }
    }
    @Test public void duplicateImagesShareDownloadAndPageCancellationDiscardsQueuedWork()throws Exception{
        AtomicInteger requests=new AtomicInteger();CountDownLatch active=new CountDownLatch(2),release=new CountDownLatch(1);
        try(MockWebServer server=new MockWebServer();ActivityController<android.app.Activity> lifecycle=Robolectric.buildActivity(android.app.Activity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request)throws InterruptedException{requests.incrementAndGet();active.countDown();release.await(4,TimeUnit.SECONDS);return new MockResponse().setResponseCode(404);}});server.start();
            ImageRequests images=new ImageRequests(new LruCache<String,Bitmap>(10));Api api=new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456"));
            try{
                ImageView first=new ImageView(lifecycle.get()),second=new ImageView(lifecycle.get());
                images.load(api,first,"/api/one/cover");images.load(api,second,"/api/one/cover");
                waitFor(()->requests.get()==1);
                images.load(api,new ImageView(lifecycle.get()),"/api/two/cover");assertTrue(active.await(2,TimeUnit.SECONDS));
                images.load(api,new ImageView(lifecycle.get()),"/api/queued/cover");
                images.cancelPage();release.countDown();waitFor(images::idle);assertEquals(2,requests.get());assertNull(first.getDrawable());assertNull(second.getDrawable());
            }finally{release.countDown();images.close();}
        }
    }
    private void backgroundPaused(ImageRequests images)throws Exception {
        Field field=ImageRequests.class.getDeclaredField("workers");field.setAccessible(true);ThreadPoolExecutor workers=(ThreadPoolExecutor)field.get(images);
        waitFor(()->workers.getActiveCount()==0&&workers.getQueue().isEmpty());shadowOf(Looper.getMainLooper()).idle();
    }
    @Test public void busyVideoThumbnailRetriesThenFillsBothViewsAndCache()throws Exception {
        AtomicInteger count=new AtomicInteger();okio.Buffer png=new okio.Buffer();Bitmap bitmap=Bitmap.createBitmap(12,8,Bitmap.Config.ARGB_8888);bitmap.eraseColor(android.graphics.Color.CYAN);bitmap.compress(Bitmap.CompressFormat.PNG,100,png.outputStream());
        try(MockWebServer server=new MockWebServer();ActivityController<android.app.Activity> lifecycle=Robolectric.buildActivity(android.app.Activity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){return count.incrementAndGet()<=2?new MockResponse().setResponseCode(503):new MockResponse().setHeader("Content-Type","image/png").setBody(png.clone());}});server.start();
            Api api=new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456"));ImageRequests images=new ImageRequests(new LruCache<String,Bitmap>(10));
            try {
                ImageView first=new ImageView(lifecycle.get()),second=new ImageView(lifecycle.get());String path="/api/files/70/thumbnail";images.load(api,first,path);images.load(api,second,path);
                waitFor(()->count.get()==1);backgroundPaused(images);assertFalse(images.idle());
                shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofMillis(499));assertEquals(1,count.get());shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofMillis(1));waitFor(()->count.get()==2);backgroundPaused(images);
                shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofMillis(1000));waitFor(()->first.getDrawable()!=null&&second.getDrawable()!=null);assertEquals(3,count.get());
                ImageView cached=new ImageView(lifecycle.get());images.load(api,cached,path);assertNotNull(cached.getDrawable());assertEquals(3,count.get());backgroundPaused(images);assertTrue(images.idle());
            }finally{images.close();}
        }
    }
    @Test public void thumbnailRetriesAreBoundedAndCancelledAndOtherErrorsDoNotRetry()throws Exception {
        java.util.Map<String,AtomicInteger> counts=new java.util.concurrent.ConcurrentHashMap<>();
        try(MockWebServer server=new MockWebServer();ActivityController<android.app.Activity> lifecycle=Robolectric.buildActivity(android.app.Activity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){String path=request.getPath();counts.computeIfAbsent(path,key->new AtomicInteger()).incrementAndGet();return new MockResponse().setResponseCode(path.contains("79")?404:path.contains("80")?401:503);}});server.start();
            Api api=new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456"));ImageRequests images=new ImageRequests(new LruCache<String,Bitmap>(10));java.util.List<ImageView> targets=new java.util.ArrayList<>();
            java.util.function.Consumer<String> load=path->{ImageView view=new ImageView(lifecycle.get());targets.add(view);images.load(api,view,path);};
            java.util.function.ToIntFunction<String> count=path->counts.containsKey(path)?counts.get(path).get():0;
            try {
                String capped="/api/files/77/thumbnail";load.accept(capped);waitFor(()->count.applyAsInt(capped)==1);backgroundPaused(images);
                int expected=1;for(long delay:new long[]{500,1000,2000}){shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofMillis(delay));final int next=++expected;waitFor(()->count.applyAsInt(capped)==next);backgroundPaused(images);}
                assertTrue(images.idle());shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofSeconds(10));assertEquals(4,count.applyAsInt(capped));
                String cancelled="/api/files/78/thumbnail";load.accept(cancelled);waitFor(()->count.applyAsInt(cancelled)==1);backgroundPaused(images);images.cancelPage();shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofSeconds(10));assertTrue(images.idle());assertEquals(1,count.applyAsInt(cancelled));
                for(String path:new String[]{"/api/files/79/thumbnail","/api/files/80/thumbnail","/api/works/1/cover"})load.accept(path);waitFor(images::idle);shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofSeconds(10));for(String path:new String[]{"/api/files/79/thumbnail","/api/files/80/thumbnail","/api/works/1/cover"})assertEquals(path,1,count.applyAsInt(path));
                String closed="/api/files/81/thumbnail";load.accept(closed);waitFor(()->count.applyAsInt(closed)==1);backgroundPaused(images);images.close();shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofSeconds(10));assertEquals(1,count.applyAsInt(closed));assertTrue(images.idle());
            }finally{images.close();}
        }
    }

}
