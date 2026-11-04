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
}
