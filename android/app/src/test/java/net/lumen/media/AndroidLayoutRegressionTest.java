package net.lumen.media;

import android.app.AlertDialog;
import android.graphics.*;
import android.graphics.drawable.BitmapDrawable;
import android.os.Looper;
import android.view.*;
import android.widget.*;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.*;
import org.robolectric.annotation.*;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.shadows.ShadowAlertDialog;
import okhttp3.mockwebserver.*;
import java.io.*;
import java.lang.reflect.*;
import java.util.function.BooleanSupplier;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w393dp-h852dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
public class AndroidLayoutRegressionTest {
    private boolean missingThumbnail;
    private final java.util.Set<String> requested=java.util.concurrent.ConcurrentHashMap.newKeySet();
    private void set(Object target,String name,Object value)throws Exception {Field f=target.getClass().getDeclaredField(name);f.setAccessible(true);f.set(target,value);}
    private Object get(Object target,String name)throws Exception {Field f=target.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(target);}
    private void call(Object target,String name)throws Exception {Method m=target.getClass().getDeclaredMethod(name);m.setAccessible(true);m.invoke(target);}
    private void layout(View root,int width,int height){for(int i=0;i<3;i++){root.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(height,View.MeasureSpec.EXACTLY));root.layout(0,0,width,height);}}
    private void dialogLayout(View root,int width,int maximumHeight){for(int i=0;i<3;i++){root.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(maximumHeight,View.MeasureSpec.AT_MOST));root.layout(0,0,width,root.getMeasuredHeight());}}
    private void waitFor(BooleanSupplier ready)throws Exception {long until=System.currentTimeMillis()+6000;while(!ready.getAsBoolean()&&System.currentTimeMillis()<until){Thread.sleep(15);Shadows.shadowOf(Looper.getMainLooper()).idle();}assertTrue(ready.getAsBoolean());}
    private void snapshot(View root,String name)throws Exception {String dir=System.getenv("LUMEN_UI_SCREENSHOTS");if(dir==null)return;File file=new File(dir,name);file.getParentFile().mkdirs();Bitmap image=Bitmap.createBitmap(root.getWidth(),root.getHeight(),Bitmap.Config.ARGB_8888);root.draw(new Canvas(image));try(FileOutputStream out=new FileOutputStream(file)){image.compress(Bitmap.CompressFormat.PNG,100,out);}image.recycle();}
    private void connect(MainActivity activity,MockWebServer server)throws Exception {set(activity,"api",new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456")));}
    private MockWebServer server()throws Exception {
        MockWebServer server=new MockWebServer();
        java.util.Map<String,okio.Buffer> images=new java.util.HashMap<>();
        for(int[] dimensions:new int[][]{{400,800},{1000,300},{600,900}}){okio.Buffer picture=new okio.Buffer();poster(dimensions[0],dimensions[1]).compress(Bitmap.CompressFormat.PNG,100,picture.outputStream());images.put("/api/test-cover-"+dimensions[0]+".png",picture);}
        okio.Buffer thumb=new okio.Buffer();poster(1200,675).compress(Bitmap.CompressFormat.PNG,100,thumb.outputStream());images.put("/api/files/70/thumbnail",thumb);images.put("/api/resume-only-poster.png",images.get("/api/test-cover-400.png"));
        org.json.JSONArray works=new org.json.JSONArray();String[] names={"海岸纪行：沿着海风，走向群岛深处", "星空下的旅行：穿越山河与漫长夜晚的完整记录", "山海相逢"};int[] widths={400,1000,600};
        for(int i=0;i<names.length;i++)works.put(new org.json.JSONObject().put("id",7+i).put("title",names[i]).put("kind","movie").put("cover","/api/test-cover-"+widths[i]+".png").put("favorite",i==1?1:0).put("file_count",1));
        String catalog=new org.json.JSONObject().put("items",works).put("total",3).toString();
        org.json.JSONObject resume=new org.json.JSONObject().put("file_id",70).put("name","S02E03 · Coast.Journal.2160p.HEVC.mkv").put("position",2308).put("duration",3600);if(!missingThumbnail)resume.put("thumbnail","/api/files/70/thumbnail");String continuation=new org.json.JSONObject().put("items",new org.json.JSONArray().put(new org.json.JSONObject().put("id",7).put("title",names[0]).put("cover","/api/resume-only-poster.png").put("resume",resume))).toString();
        String titles=new org.json.JSONObject().put("titles",new org.json.JSONObject().put("7","第一集：长标题测试海岸纪行，沿着海风走向群岛深处，以及越来越长的后半部分，确保两行以后省略但仍能正常选择和操作，补充一段让标题更长的文字").put("8",names[1]).put("9",names[2])).toString();
        server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){String path=request.getPath();requested.add(path);okio.Buffer image=images.get(path);if(image!=null)return new MockResponse().setHeader("Content-Type","image/png").setBody(image.clone());return new MockResponse().setBody(path.startsWith("/api/continue")?continuation:path.startsWith("/api/queue-titles")?titles:path.startsWith("/api/works?")||path.startsWith("/api/discover?")?catalog:"{\"items\":[],\"total\":0,\"tags\":[]}");}});server.start();return server;
    }
    private ImageView firstImage(View root){if(root instanceof ImageView)return (ImageView)root;if(root instanceof ViewGroup){ViewGroup group=(ViewGroup)root;for(int i=0;i<group.getChildCount();i++){ImageView found=firstImage(group.getChildAt(i));if(found!=null)return found;}}return null;}
    private void waitForCatalog(View root)throws Exception {waitFor(()->root.findViewWithTag("card:7")!=null);waitFor(()->firstImage(root.findViewWithTag("card:7")).getDrawable() instanceof BitmapDrawable);}
    private Bitmap poster(int width,int height){Bitmap image=Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);Canvas canvas=new Canvas(image);Paint p=new Paint();p.setShader(new LinearGradient(0,0,width,height,0xff368b9b,0xff182c48,Shader.TileMode.CLAMP));canvas.drawRect(0,0,width,height,p);p.setShader(null);p.setColor(0xfff1d38c);canvas.drawCircle(width*.5f,height*.25f,Math.min(width,height)*.15f,p);p.setColor(0xff99d5bf);canvas.drawRect(width*.1f,height*.65f,width*.9f,height*.9f,p);p.setColor(Color.WHITE);p.setTextSize(Math.min(width,height)*.09f);canvas.drawText("COAST JOURNAL",width*.08f,height*.53f,p);
        int border=Math.max(12,Math.min(width,height)/20);p.setColor(Color.RED);canvas.drawRect(0,0,width,border,p);p.setColor(Color.GREEN);canvas.drawRect(0,height-border,width,height,p);p.setColor(Color.BLUE);canvas.drawRect(0,border,border,height-border,p);p.setColor(Color.YELLOW);canvas.drawRect(width-border,border,width,height-border,p);return image;}
    private boolean contains(Bitmap bitmap,int color){for(int y=0;y<bitmap.getHeight();y++)for(int x=0;x<bitmap.getWidth();x++)if(bitmap.getPixel(x,y)==color)return true;return false;}
    @Test public void continuePreservesEveryEdgeForPortraitAndWideArtworkAndKeepsPlayOffImage()throws Exception {
        try(MockWebServer server=server();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            MainActivity activity=life.get();connect(activity,server);call(activity,"showLibrary");View root=(View)get(activity,"root");waitFor(()->root.findViewWithTag("continueArtwork:70")!=null);ImageView cover=(ImageView)((ViewGroup)root.findViewWithTag("continueArtwork:70")).getChildAt(0);waitFor(()->cover.getDrawable() instanceof BitmapDrawable);assertEquals("1200px video thumbnail is downsampled by Api.image to 600px",600,((BitmapDrawable)cover.getDrawable()).getBitmap().getWidth());assertEquals(server.url("/").toString().replaceAll("/$","")+"/api/files/70/thumbnail",cover.getTag());assertTrue(requested.contains("/api/files/70/thumbnail"));assertFalse("continue must never request the work poster",requested.contains("/api/resume-only-poster.png"));waitForCatalog(root);
            for(int[] dimensions:new int[][]{{400,800},{1000,300},{1200,675}}){Bitmap bitmap=poster(dimensions[0],dimensions[1]);cover.setImageDrawable(new BitmapDrawable(activity.getResources(),bitmap));layout(root,320,852);assertEquals(ImageView.ScaleType.FIT_CENTER,cover.getScaleType());RectF bounds=new RectF(0,0,dimensions[0],dimensions[1]);cover.getImageMatrix().mapRect(bounds);assertTrue(bounds.left>=-.01f);assertTrue(bounds.top>=-.01f);assertTrue(bounds.right<=cover.getWidth()+.01f);assertTrue(bounds.bottom<=cover.getHeight()+.01f);Bitmap drawn=Bitmap.createBitmap(cover.getWidth(),cover.getHeight(),Bitmap.Config.ARGB_8888);cover.draw(new Canvas(drawn));for(int color:new int[]{Color.RED,Color.GREEN,Color.BLUE,Color.YELLOW})assertTrue("edge color is missing: "+color,contains(drawn,color));drawn.recycle();assertNotSame("play must not obscure the subject",cover.getParent(),root.findViewWithTag("continuePlay:70").getParent());snapshot(root,"android-home-320-"+dimensions[0]+"x"+dimensions[1]+".png");}
            cover.setImageBitmap(poster(1200,675));layout(root,393,852);snapshot(root,"android-home-393.png");LinearLayout heading=root.findViewWithTag("listHeading");assertTrue(heading.getChildAt(2).getLeft()-heading.getChildAt(1).getRight()>=8);
        }
    }
    @Test public void oldServerWithoutResumeThumbnailShowsPlaceholderInsteadOfPoster()throws Exception {
        missingThumbnail=true;
        try(MockWebServer server=server();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            MainActivity activity=life.get();connect(activity,server);call(activity,"showLibrary");View root=(View)get(activity,"root");waitFor(()->root.findViewWithTag("continueThumbnailMissing:70")!=null);waitForCatalog(root);layout(root,393,852);ImageView image=(ImageView)((ViewGroup)root.findViewWithTag("continueArtwork:70")).getChildAt(0);assertFalse(image.getDrawable() instanceof BitmapDrawable);assertFalse(requested.contains("/api/resume-only-poster.png"));assertFalse(requested.contains("/api/files/70/thumbnail"));snapshot(root,"android-home-missing-thumbnail.png");
        }
    }
    @Test public void queueLongNamesStayTwoLinesAndAllActionsFitNarrowDialog()throws Exception {
        for(float fontScale:new float[]{1f,1.3f}){
            try(MockWebServer server=server();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
                MainActivity activity=life.get();android.content.res.Configuration cfg=new android.content.res.Configuration(activity.getResources().getConfiguration());cfg.fontScale=fontScale;activity.getResources().updateConfiguration(cfg,activity.getResources().getDisplayMetrics());
                connect(activity,server);activity.getSharedPreferences("queue",0).edit().putString("ids","[7,8,9]").apply();call(activity,"queueEditor");waitFor(()->{AlertDialog current=ShadowAlertDialog.getLatestAlertDialog();return current!=null&&current.isShowing();});AlertDialog dialog=ShadowAlertDialog.getLatestAlertDialog();View decor=dialog.getWindow().getDecorView();
                for(int[] window:new int[][]{{320,760},{393,760},{640,393}}){
                    int width=window[0];dialogLayout(decor,width,window[1]);assertTrue(decor.getHeight()<=window[1]);ListView list=decor.findViewWithTag("phoneQueueItems");assertNotNull(list);assertTrue(list.getChildCount()>0);
                    CheckedTextView first=(CheckedTextView)list.getChildAt(0);assertEquals(2,first.getMaxLines());assertEquals(android.text.TextUtils.TruncateAt.END,first.getEllipsize());assertTrue("expected full original title: "+first.getText(),first.getText().length()>60);assertTrue("queue row too short: "+first.getHeight(),first.getHeight()>=72);assertTrue("long item height="+first.getHeight(),first.getHeight()<=96);assertTrue("queue line count="+first.getLayout().getLineCount(),first.getLayout().getLineCount()<=2);if(width<=393)assertTrue("long text needs visible ellipsis at width="+width,first.getLayout().getEllipsisCount(first.getLayout().getLineCount()-1)>0);
                    LinearLayout actions=decor.findViewWithTag("phoneQueueActions");for(int i=0;i<actions.getChildCount();i++){View button=actions.getChildAt(i);assertTrue(button.getWidth()>=48);assertTrue(button.getHeight()>=48);assertTrue(button.getRight()<=actions.getWidth());if(i>0)assertEquals(12,button.getLeft()-actions.getChildAt(i-1).getRight());}
                    assertTrue(list.getHeight()>=48);int[] location=new int[2];actions.getLocationInWindow(location);assertTrue(location[1]+actions.getHeight()<=window[1]);
                    Button close=dialog.getButton(AlertDialog.BUTTON_NEGATIVE);close.getLocationInWindow(location);assertTrue(close.getHeight()>=48);assertTrue(location[1]+close.getHeight()<=window[1]);
                    snapshot(decor,"android-queue-"+width+(fontScale>1?"-large-font":"")+".png");
                }
                dialog.dismiss();
            }
        }
    }
}
