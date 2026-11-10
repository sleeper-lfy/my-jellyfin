package net.lumen.media;

import android.graphics.Bitmap;
import android.graphics.Rect;
import android.os.Handler;
import android.os.Looper;
import android.util.LruCache;
import android.widget.ImageView;
import java.lang.ref.WeakReference;
import java.util.*;
import java.util.concurrent.*;

/** Image work never occupies the operation executor. All targets are weak. */
final class ImageRequests implements AutoCloseable {
    private static final long[] THUMBNAIL_RETRY_MS={500,1000,2000};
    private final Handler main=new Handler(Looper.getMainLooper());
    private final ThreadPoolExecutor workers=new ThreadPoolExecutor(2,2,0,TimeUnit.SECONDS,new PriorityBlockingQueue<>());
    private final Map<String,Load> pending=new HashMap<>();
    private final LruCache<String,Bitmap> cache;
    private long sequence=0;
    private boolean closed,priorityPending;
    private final Runnable priorityUpdate=()->{priorityPending=false;reprioritize();};
    ImageRequests(LruCache<String,Bitmap> cache){this.cache=cache;}
    private final class Load implements Runnable,Comparable<Load> {
        final String key,path;final Api api;final long order=sequence++;
        final Api.Cancellation cancellation=new Api.Cancellation();
        final List<WeakReference<ImageView>> targets=new ArrayList<>();
        boolean visible;int retries;
        final Runnable retry=this::retryDownload;
        private boolean current(){return !closed&&!cancellation.cancelled()&&pending.get(key)==this;}
        private void retryDownload(){
            if(!current())return;
            targets.removeIf(ref->{ImageView view=ref.get();return view==null||!key.equals(view.getTag());});
            if(targets.isEmpty()){pending.remove(key);cancellation.cancel();return;}
            workers.execute(this);
        }
        private void failed(Exception error){
            if(!current())return;
            boolean busyThumbnail=error instanceof Api.StatusException&&((Api.StatusException)error).status==503&&path.matches("/api/files/[0-9]+/thumbnail");
            if(busyThumbnail&&retries<THUMBNAIL_RETRY_MS.length){main.postDelayed(retry,THUMBNAIL_RETRY_MS[retries++]);}
            else pending.remove(key);
        }
        Load(Api api,String path,String key){this.api=api;this.path=path;this.key=key;}
        public int compareTo(Load other){int priority=Boolean.compare(other.visible,visible);return priority!=0?priority:Long.compare(order,other.order);}
        public void run(){
            try{
                cancellation.check();
                Bitmap bitmap=api.image(path,cancellation);
                main.post(()->{
                    if(closed||cancellation.cancelled()||pending.get(key)!=this)return;
                    pending.remove(key);
                    if(bitmap==null)return;
                    cache.put(key,bitmap);
                    for(WeakReference<ImageView> ref:targets){ImageView view=ref.get();if(view!=null&&key.equals(view.getTag()))view.setImageBitmap(bitmap);}
                });
            }catch(Exception error){main.post(()->failed(error));}
        }
    }
    void load(Api api,ImageView view,String path){
        if(closed||path.isEmpty()||path.equals("null"))return;
        String key=api.connection.base+path;view.setTag(key);
        Bitmap bitmap=cache.get(key);if(bitmap!=null){view.setImageBitmap(bitmap);return;}
        Load load=pending.get(key);
        if(load==null){load=new Load(api,path,key);load.targets.add(new WeakReference<>(view));load.visible=view.getGlobalVisibleRect(new Rect());pending.put(key,load);workers.execute(load);}
        else {boolean present=false;for(WeakReference<ImageView> ref:load.targets)if(ref.get()==view){present=true;break;}if(!present)load.targets.add(new WeakReference<>(view));}
        prioritizeVisible();
    }
    void prioritizeVisible(){
        if(!closed&&!priorityPending){priorityPending=true;main.postDelayed(priorityUpdate,16);}
    }
    private void reprioritize(){
        if(closed)return;
        for(Load load:pending.values()){
            boolean visible=false;
            Iterator<WeakReference<ImageView>> iterator=load.targets.iterator();
            while(iterator.hasNext()){
                ImageView view=iterator.next().get();
                if(view==null||!load.key.equals(view.getTag()))iterator.remove();
                else visible|=view.getGlobalVisibleRect(new Rect());
            }
            if(workers.getQueue().remove(load)){load.visible=visible;workers.execute(load);}
        }
    }
    boolean idle(){return pending.isEmpty()&&workers.getActiveCount()==0&&workers.getQueue().isEmpty();}
    void cancelPage(){
        main.removeCallbacks(priorityUpdate);priorityPending=false;
        // Disconnecting an active call can free a worker immediately. Remove
        // queued loads first so leaving a page cannot start another download.
        workers.getQueue().clear();
        for(Load load:pending.values()){main.removeCallbacks(load.retry);load.cancellation.cancel();}
        pending.clear();
    }
    void restore(Api api,android.view.View root){
        if(root instanceof ImageView&&root.getTag() instanceof String){String key=(String)root.getTag();if(key.startsWith(api.connection.base+"/api/"))load(api,(ImageView)root,key.substring(api.connection.base.length()));}
        if(root instanceof android.view.ViewGroup){android.view.ViewGroup group=(android.view.ViewGroup)root;for(int i=0;i<group.getChildCount();i++)restore(api,group.getChildAt(i));}
    }
    public void close(){closed=true;cancelPage();workers.shutdownNow();main.removeCallbacksAndMessages(null);}
}
