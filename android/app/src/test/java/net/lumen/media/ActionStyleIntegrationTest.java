package net.lumen.media;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Rect;
import android.graphics.drawable.Drawable;
import android.os.Looper;
import android.os.SystemClock;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ScrollView;
import android.widget.TextView;
import androidx.core.content.ContextCompat;
import com.google.android.material.button.MaterialButton;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.GraphicsMode;
import org.robolectric.shadows.ShadowAlertDialog;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BooleanSupplier;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

/** Exercises the ordinary action factories where users actually encounter them. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk = 33, qualifiers = "w393dp-h852dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
public class ActionStyleIntegrationTest {
    private static final String TOKEN = "abcdefghijklmnopqrstuvwxyz123456";
    private static final String LONG_TITLE = "海岸纪行：沿着海风走向群岛深处，穿过清晨港口与安静山林的漫长旅程";

    private Object field(Object target, String name) throws Exception {
        Field field = target.getClass().getDeclaredField(name);field.setAccessible(true);return field.get(target);
    }
    private void field(Object target, String name, Object value) throws Exception {
        Field field = target.getClass().getDeclaredField(name);field.setAccessible(true);field.set(target,value);
    }
    private void call(Object target, String name) throws Exception {
        Method method=target.getClass().getDeclaredMethod(name);method.setAccessible(true);method.invoke(target);
    }
    private void waitFor(BooleanSupplier ready) throws Exception {
        long deadline=System.currentTimeMillis()+6000;
        while(!ready.getAsBoolean()&&System.currentTimeMillis()<deadline){Thread.sleep(10);shadowOf(Looper.getMainLooper()).idle();}
        assertTrue("The actual screen did not reach the requested state",ready.getAsBoolean());
    }
    private View content(Activity activity){return ((ViewGroup)activity.findViewById(android.R.id.content)).getChildAt(0);}
    private void layout(View root,int width,int height){
        for(int pass=0;pass<3;pass++){root.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(height,View.MeasureSpec.EXACTLY));root.layout(0,0,width,height);}
    }
    private void dialogLayout(View root,int width,int maximumHeight){
        for(int pass=0;pass<3;pass++){root.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(maximumHeight,View.MeasureSpec.AT_MOST));root.layout(0,0,width,root.getMeasuredHeight());}
    }
    @SuppressWarnings("deprecation") private void font(Activity activity,float scale){
        Configuration config=new Configuration(activity.getResources().getConfiguration());config.fontScale=scale;
        activity.getResources().getDisplayMetrics().scaledDensity=activity.getResources().getDisplayMetrics().density*scale;
        activity.getResources().updateConfiguration(config,activity.getResources().getDisplayMetrics());
    }
    private Button findButton(View root,String label){
        if(root instanceof Button&&label.contentEquals(((Button)root).getText()))return (Button)root;
        if(root instanceof ViewGroup){ViewGroup group=(ViewGroup)root;for(int i=0;i<group.getChildCount();i++){Button found=findButton(group.getChildAt(i),label);if(found!=null)return found;}}
        return null;
    }
    private Button button(View root,String label){Button button=findButton(root,label);assertNotNull("Missing real action: "+label,button);return button;}
    private List<View> visibleChildren(ViewGroup group){
        List<View> children=new ArrayList<>();for(int i=0;i<group.getChildCount();i++)if(group.getChildAt(i).getVisibility()!=View.GONE)children.add(group.getChildAt(i));return children;
    }
    private void gap(ViewGroup group){
        List<View> children=visibleChildren(group);assertTrue("Need adjacent actions to verify actual spacing",children.size()>1);
        int rowBottom=children.get(0).getBottom();
        for(int i=1;i<children.size();i++){
            View before=children.get(i-1),after=children.get(i);boolean linear=group instanceof LinearLayout;
            boolean vertical=linear&&((LinearLayout)group).getOrientation()==LinearLayout.VERTICAL;
            // A horizontal LinearLayout vertically centers children of different heights;
            // only a wrapping flow can start another row when its child's top changes.
            int actual=vertical?after.getTop()-before.getBottom():linear||after.getTop()==before.getTop()?after.getLeft()-before.getRight():after.getTop()-rowBottom;
            assertEquals("Actions must reserve an external 12dp gap: "+before.getContentDescription()+" / "+after.getContentDescription(),12,actual);
            rowBottom=after.getTop()==before.getTop()?Math.max(rowBottom,after.getBottom()):after.getBottom();
        }
    }
    private void readable(Button button){
        assertTrue("Touch width: "+button.getText(),button.getWidth()>=48);
        assertTrue("Touch height: "+button.getText(),button.getHeight()>=48);
        assertNotNull("Text must actually be laid out",button.getLayout());
        int available=button.getHeight()-button.getCompoundPaddingTop()-button.getCompoundPaddingBottom();
        assertTrue("Text clipped vertically: "+button.getText()+" text="+button.getLayout().getHeight()+" available="+available,button.getLayout().getHeight()<=available);
        int textLeft=button.getCompoundPaddingLeft(),textRight=button.getWidth()-button.getCompoundPaddingRight();
        for(int line=0;line<button.getLayout().getLineCount();line++){
            // MaterialButton can update its compound icon after the paragraph is allocated.
            // Check the glyph interval that TextView draws, rather than that allocation width.
            float left=button.getLayout().getLineLeft(line),right=button.getLayout().getLineRight(line);
            assertTrue("Text glyphs exceed the available width: "+button.getText()+" line="+line+" glyphs="+(right-left)+" available="+(textRight-textLeft),right-left<=textRight-textLeft+1);
            assertTrue("Text glyphs are clipped horizontally: "+button.getText()+" line="+line+" drawn="+(textLeft+left)+".."+(textLeft+right)+" clip="+textLeft+".."+textRight,textLeft+left>=textLeft-1&&textLeft+right<=textRight+1);
        }
        assertTrue("Action overflows its real parent: "+button.getText(),button.getLeft()>=0&&button.getRight()<=((View)button.getParent()).getWidth());
    }
    private void paintedBackground(Button button,boolean compact){
        Bitmap image=Bitmap.createBitmap(button.getWidth(),button.getHeight(),Bitmap.Config.ARGB_8888);
        Drawable background=button.getBackground();Rect old=new Rect(background.getBounds());background.setBounds(0,0,image.getWidth(),image.getHeight());background.draw(new Canvas(image));background.setBounds(old);
        int first=-1,last=-1,x=image.getWidth()/2,maximumAlpha=0;
        for(int y=0;y<image.getHeight();y++){
            int alpha=Color.alpha(image.getPixel(x,y));maximumAlpha=Math.max(maximumAlpha,alpha);
            // The M3 disabled fill is 12% opaque (31/255), and is still a real painted surface.
            if(alpha>0){if(first<0)first=y;last=y;}
        }
        if(!button.isEnabled())assertTrue("Disabled fill remains visible and translucent: "+button.getText()+" alpha="+maximumAlpha,maximumAlpha>0&&maximumAlpha<255);
        image.recycle();assertEquals("Top of the actual painted container: "+button.getText(),8,first);
        assertEquals("Bottom of the actual painted container: "+button.getText(),8,button.getHeight()-1-last);
        if(compact)assertEquals("Normal-font visible action height: "+button.getText(),32,last-first+1);
        else assertTrue("Large-font surface must be able to grow",last-first+1>=32);
    }
    private void material(Button button,boolean compact){
        assertTrue("Real pages must use the official MaterialButton: "+button.getText(),button instanceof MaterialButton);
        MaterialButton material=(MaterialButton)button;assertEquals(8,material.getCornerRadius());assertEquals(8,material.getInsetTop());assertEquals(8,material.getInsetBottom());
        assertEquals(18,material.getIconSize());assertEquals(4,material.getIconPadding());readable(button);paintedBackground(button,compact);
    }
    private void light(Button button){
        assertTrue("Light actions still use official MaterialButton",button instanceof MaterialButton);readable(button);
        MaterialButton material=(MaterialButton)button;assertNotNull(material.getBackgroundTintList());
        assertEquals("Grouped rows and icon actions have no solid button surface",0,Color.alpha(material.getBackgroundTintList().getDefaultColor()));
    }
    private void playerSettings(View root){
        LinearLayout tabs=root.findViewWithTag("playerSettingTabs");assertEquals(3,tabs.getChildCount());
        View previous=null;for(int i=0;i<tabs.getChildCount();i++){
            ViewGroup cell=(ViewGroup)tabs.getChildAt(i);Button tab=(Button)cell.getChildAt(0);light(tab);
            assertTrue(cell.getRight()<=tabs.getWidth());if(previous!=null)assertTrue(cell.getLeft()>=previous.getRight());previous=cell;
        }
        ViewGroup groups=root.findViewWithTag("playerSettingActions");assertTrue(groups.getChildCount()>0);
        for(int i=0;i<groups.getChildCount();i++){
            ViewGroup group=(ViewGroup)groups.getChildAt(i);View before=null;
            for(int j=0;j<group.getChildCount();j++){
                View row=group.getChildAt(j);if(!(row instanceof PlayerChrome.SettingRow))continue;
                light(((PlayerChrome.SettingRow)row).action);if(before!=null)assertTrue("Rows separated by a divider",row.getTop()>before.getBottom());before=row;
            }
        }
    }
    private ScrollView scroll(View view){if(view instanceof ScrollView)return (ScrollView)view;if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){ScrollView found=scroll(group.getChildAt(i));if(found!=null)return found;}}return null;}
    private void footer(AlertDialog dialog){
        List<Button> buttons=new ArrayList<>();
        for(int which:new int[]{AlertDialog.BUTTON_NEGATIVE,AlertDialog.BUTTON_NEUTRAL,AlertDialog.BUTTON_POSITIVE}){
            Button button=dialog.getButton(which);if(button!=null&&button.getVisibility()==View.VISIBLE){readable(button);paintedBackground(button,false);buttons.add(button);
                if(which==AlertDialog.BUTTON_POSITIVE&&button.isEnabled()){
                    Bitmap painted=Bitmap.createBitmap(button.getWidth(),button.getHeight(),Bitmap.Config.ARGB_8888);button.draw(new Canvas(painted));
                    int actual=painted.getPixel(button.getWidth()/2,9);painted.recycle();
                    assertEquals("Enabled primary action must keep its theme surface; view="+button.getClass().getName()+" states="+java.util.Arrays.toString(button.getDrawableState())+" background="+java.util.Arrays.toString(button.getBackground().getState())+" tint="+button.getBackgroundTintList(),net.lumen.media.ui.theme.NativeActionTokens.container(true,1,false),actual);
                }
            }
        }
        for(int i=0;i<buttons.size();i++)for(int j=i+1;j<buttons.size();j++){
            Rect a=inRoot(dialog.getWindow().getDecorView(),buttons.get(i)),b=inRoot(dialog.getWindow().getDecorView(),buttons.get(j));
            if(a.top<b.bottom&&b.top<a.bottom){int distance=a.left<b.left?b.left-a.right:a.left-b.right;assertTrue("Platform dialog actions need a visible external gap, got "+distance,distance>=12);}
            assertFalse("Dialog action slots overlap",Rect.intersects(a,b));
        }
    }
    private Rect inRoot(View root,View child){Rect result=new Rect(0,0,child.getWidth(),child.getHeight());((ViewGroup)root).offsetDescendantRectToMyCoords(child,result);return result;}
    private void tap(View root,float x,float y){
        long now=SystemClock.uptimeMillis();MotionEvent down=MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,x,y,0),up=MotionEvent.obtain(now,now+32,MotionEvent.ACTION_UP,x,y,0);
        root.dispatchTouchEvent(down);root.dispatchTouchEvent(up);down.recycle();up.recycle();shadowOf(Looper.getMainLooper()).idle();
    }
    private void edgeTap(View root,Button action){Rect bounds=inRoot(root,action);tap(root,bounds.exactCenterX(),bounds.top+2);}
    private void snapshot(View root,String name)throws Exception{
        String directory=System.getenv("LUMEN_ACTION_SCREENSHOTS");if(directory==null||directory.isEmpty())return;
        Bitmap image=Bitmap.createBitmap(root.getWidth(),root.getHeight(),Bitmap.Config.ARGB_8888);root.draw(new Canvas(image));
        File file=new File(directory,name);assertTrue(file.getParentFile().isDirectory()||file.getParentFile().mkdirs());try(FileOutputStream stream=new FileOutputStream(file)){assertTrue(image.compress(Bitmap.CompressFormat.PNG,100,stream));}image.recycle();
    }

    private final class Fixture implements AutoCloseable {
        final MockWebServer server=new MockWebServer();final Set<String> requested=ConcurrentHashMap.newKeySet();final JSONObject work;
        Fixture()throws Exception{
            Bitmap bitmap=Bitmap.createBitmap(240,360,Bitmap.Config.ARGB_8888);Drawable coast=ContextCompat.getDrawable(RuntimeEnvironment.getApplication(),R.drawable.discovery_preview_coast);assertNotNull(coast);coast.setBounds(0,0,240,360);coast.draw(new Canvas(bitmap));ByteArrayOutputStream bytes=new ByteArrayOutputStream();bitmap.compress(Bitmap.CompressFormat.PNG,100,bytes);bitmap.recycle();byte[] poster=bytes.toByteArray();
            work=new JSONObject().put("id",7).put("title",LONG_TITLE).put("kind","movie").put("year",2025).put("file_count",1).put("favorite",0).put("watchlist",0).put("rating",7).put("cover","/api/works/7/cover").put("overview","清晨出发，沿着海岸线探访安静的港口与山林。本测试使用虚构作品。")
                .put("tags",new JSONArray().put("旅行").put("自然纪录片")).put("actors",new JSONArray()).put("files",new JSONArray().put(new JSONObject().put("id",70).put("name","Coast.Journal.mp4").put("duration",3600)));
            String catalog=new JSONObject().put("items",new JSONArray().put(work)).put("total",1).toString();
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){
                String path=request.getPath();requested.add(path);assertEquals("Bearer "+TOKEN,request.getHeader("Authorization"));
                if(path.endsWith("/cover"))return new MockResponse().setHeader("Content-Type","image/png").setBody(new okio.Buffer().write(poster));
                if(path.startsWith("/api/filters"))return new MockResponse().setBody("{\"tags\":[\"旅行\",\"自然纪录片\"],\"actors\":[],\"years\":[2025]}");
                if(path.startsWith("/api/queue-titles"))return new MockResponse().setBody("{\"titles\":{\"7\":\""+LONG_TITLE+"\",\"8\":\"星夜环游\",\"9\":\"群岛来信\"}}");
                if(path.startsWith("/api/tasks")){boolean second=path.contains("offset=30");return new MockResponse().setBody("{\"items\":[{\"id\":\"sample-job\",\"label\":\"资料整理\",\"status_label\":\"完成\",\"work_title\":\""+(second?"星夜环游":"海岸纪行")+"\",\"reason\":\"虚构作品的资料整理任务\",\"updated\":\"2026-11-11T03:00:00+00:00\"}],\"total\":31}");}
                if(path.startsWith("/api/continue"))return new MockResponse().setBody("{\"items\":[]}");
                if(path.equals("/api/works/7"))return new MockResponse().setBody(work.toString());
                return new MockResponse().setBody(catalog);
            }});server.start();
        }
        Api api()throws Exception{return new Api(new Connection(server.url("/").toString(),TOKEN));}
        void connect(MainActivity activity)throws Exception{activity.api=api();field(activity,"utilityPage","");field(activity,"mainPage","library");activity.kind="movie";}
        @Override public void close()throws Exception{server.close();}
    }

    @Test public void realMineActionsAreCompactSpacedAndTheirInvisibleEdgeLaunchesOnce()throws Exception{
        try(Fixture fixture=new Fixture();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create().start().resume().visible()){
            MainActivity activity=life.get();fixture.connect(activity);call(activity,"showMine");View root=content(activity);layout(root,393,852);
            com.google.android.material.bottomnavigation.BottomNavigationView navigation=root.findViewWithTag("primaryNavigation");
            assertEquals("Mine must stay selected even when a library category was previously active",navigation.getMenu().getItem(3).getItemId(),navigation.getSelectedItemId());
            Button favorite=button(root,"收藏"),wanted=button(root,"想看"),remote=button(root,"电脑遥控");light(favorite);light(wanted);light(remote);
            assertEquals("Quick actions share one row",favorite.getTop(),wanted.getTop());assertTrue("Quick action touch targets must not overlap",wanted.getLeft()>=favorite.getRight());
            ScrollView scroll=(ScrollView)field(activity,"browseScroll");remote.requestRectangleOnScreen(new Rect(0,0,remote.getWidth(),remote.getHeight()),true);layout(root,393,852);
            Rect remoteBounds=inRoot(root,remote),viewport=inRoot(root,scroll);float edgeX=remoteBounds.exactCenterX(),edgeY=remoteBounds.top+2;
            assertTrue("Mine edge touch must lie inside the actual scroll viewport: action="+remoteBounds+" viewport="+viewport+" scrollY="+scroll.getScrollY(),viewport.contains((int)edgeX,(int)edgeY));
            Rect visible=new Rect();assertTrue("The actual action must be visible in the attached activity",remote.getLocalVisibleRect(visible));assertTrue("The transparent upper inset must not be clipped: "+visible,visible.contains(remote.getWidth()/2,2));
            AtomicInteger parentClicks=new AtomicInteger();((View)remote.getParent()).setOnClickListener(v->parentClicks.incrementAndGet());edgeTap(root,remote);
            Intent started=shadowOf(activity).getNextStartedActivity();assertNotNull("The invisible 8dp inset remains clickable: action="+remoteBounds+" viewport="+viewport+" parentClicks="+parentClicks.get(),started);assertEquals(RemoteActivity.class.getName(),started.getComponent().getClassName());assertNull("One edge tap must only dispatch once",shadowOf(activity).getNextStartedActivity());assertEquals("The action must consume its touch",0,parentClicks.get());
            scroll.scrollTo(0,0);layout(root,393,852);snapshot(root,"action-main-mine-393-dark.png");
        }
    }

    @Test public void realLibraryFiltersKeepWatchAndPreferenceGapsAndCompactPlatformFooter()throws Exception{
        try(Fixture fixture=new Fixture();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create().start().resume().visible()){
            MainActivity activity=life.get();fixture.connect(activity);activity.showLibrary();waitFor(()->content(activity).findViewWithTag("card:7")!=null);call(activity,"showFilters");
            AlertDialog dialog=ShadowAlertDialog.getLatestAlertDialog();try{
                View root=dialog.getWindow().getDecorView();dialogLayout(root,393,804);ViewGroup watch=root.findViewWithTag("watchSegments");gap(watch);
                for(View child:visibleChildren(watch))material((Button)child,true);
                Button disliked=root.findViewWithTag("filterDisliked");ViewGroup preferences=(ViewGroup)disliked.getParent();gap(preferences);for(View child:visibleChildren(preferences))material((Button)child,true);
                Button wanted=button(root,"想看");edgeTap(root,wanted);assertTrue("Inset touch must toggle the actual filter",wanted.isSelected());edgeTap(root,wanted);assertFalse(wanted.isSelected());
                footer(dialog);snapshot(root,"action-main-filters-393-dark.png");
                edgeTap(root,dialog.getButton(AlertDialog.BUTTON_NEGATIVE));assertFalse("Platform footer inset remains clickable",dialog.isShowing());
            }finally{dialog.dismiss();}
        }
    }

    @Test public void realQueueReorderAndDetailPersonalActionsUseTheSameNativeStyle()throws Exception{
        try(Fixture fixture=new Fixture();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create().start().resume().visible()){
            MainActivity activity=life.get();fixture.connect(activity);activity.getSharedPreferences("queue",0).edit().putString("ids","[7,8,9]").putInt("index",0).apply();activity.queueEditor();waitFor(()->ShadowAlertDialog.getLatestAlertDialog()!=null&&ShadowAlertDialog.getLatestAlertDialog().isShowing());
            AlertDialog queue=ShadowAlertDialog.getLatestAlertDialog();try{
                View root=queue.getWindow().getDecorView();dialogLayout(root,393,804);LinearLayout actions=root.findViewWithTag("phoneQueueActions");gap(actions);for(View child:visibleChildren(actions))light((Button)child);
                edgeTap(root,button(root,"下移"));assertEquals("[8,7,9]",activity.getSharedPreferences("queue",0).getString("ids",""));footer(queue);snapshot(root,"action-main-queue-393-dark.png");
            }finally{queue.dismiss();}
            Method render=MainActivity.class.getDeclaredMethod("renderDetail",JSONObject.class);render.setAccessible(true);render.invoke(activity,fixture.work);waitFor(activity.imageRequests::idle);View root=content(activity);layout(root,393,852);
            Button favorite=root.findViewWithTag("mark:7:favorite"),score=root.findViewWithTag("rating:7");light(favorite);light(score);
            gap((ViewGroup)favorite.getParent());
            snapshot(root,"action-main-detail-393-dark.png");edgeTap(root,score);AlertDialog rating=ShadowAlertDialog.getLatestAlertDialog();assertTrue(rating.isShowing());assertEquals("我的评分",shadowOf(rating).getTitle());rating.dismiss();
        }
    }

    @Test public void realRemoteActionsHaveExternalGapsAndDisabledPowerCannotFire()throws Exception{
        try(ActivityController<RemoteActivity> life=Robolectric.buildActivity(RemoteActivity.class).create().start().resume().visible()){
            RemoteActivity activity=life.get();call(activity,"buildUi");View root=content(activity);layout(root,393,852);LinearLayout actions=root.findViewWithTag("remoteMediaActions");gap(actions);for(View child:visibleChildren(actions))light((Button)child);
            Button shutdown=button(root,"关闭电脑");light(shutdown);assertFalse(shutdown.isEnabled());AtomicInteger attempts=new AtomicInteger();shutdown.setOnClickListener(v->attempts.incrementAndGet());ScrollView scroll=scroll(root);assertNotNull(scroll);scroll.scrollTo(0,10000);layout(root,393,852);edgeTap(root,shutdown);assertEquals("Disabled actual power action must not run",0,attempts.get());snapshot(root,"action-remote-393-dark.png");
        }
    }

    @Test public void realUpdateActionsRemainCompactAcrossAsyncEnablement()throws Exception{
        try(ActivityController<UpdateActivity> life=Robolectric.buildActivity(UpdateActivity.class)){
            UpdateActivity activity=life.get();activity.fetcher=(url,limit)->{throw new IOException("测试更新源暂不可用");};life.create().start().resume().visible();waitFor(()->{try{return ((Button)field(activity,"check")).isEnabled();}catch(Exception error){return false;}});
            View root=content(activity);layout(root,393,852);LinearLayout actions=root.findViewWithTag("updateActions");assertEquals("No candidate: only check is relevant",1,visibleChildren(actions).size());Button check=button(root,"检查更新");material(check,true);
            Button download=button(root,"下载新版 APK");assertFalse(download.isEnabled());assertEquals(View.GONE,download.getVisibility());AtomicInteger attempts=new AtomicInteger();check.setOnClickListener(v->attempts.incrementAndGet());check.setEnabled(false);edgeTap(root,check);assertEquals(0,attempts.get());check.setEnabled(true);snapshot(root,"action-update-393-dark.png");
        }
    }

    @Test public void realTaskPagingUsesCompactTargetsAndActuallyRequestsTheNextPage()throws Exception{
        try(Fixture fixture=new Fixture();ActivityController<Activity> life=Robolectric.buildActivity(Activity.class).setup()){
            AlertDialog dialog=TaskCenter.show(life.get(),fixture.api());try{
                View root=dialog.getWindow().getDecorView();Button next=root.findViewWithTag("nextTaskPage");waitFor(next::isEnabled);dialogLayout(root,393,788);
                LinearLayout paging=root.findViewWithTag("computerTaskPaging");gap(paging);for(View child:visibleChildren(paging))material((Button)child,true);light(root.findViewWithTag("refreshComputerTasks"));footer(dialog);
                assertFalse(root.findViewWithTag("previousTaskPage").isEnabled());edgeTap(root,next);waitFor(()->fixture.requested.stream().anyMatch(path->path.startsWith("/api/tasks")&&path.contains("offset=30")));waitFor(()->root.findViewWithTag("previousTaskPage").isEnabled());assertFalse(next.isEnabled());dialogLayout(root,393,788);snapshot(root,"action-task-paging-393-dark.png");
            }finally{dialog.dismiss();}
        }
    }

    private void playerUi(PlayerActivity activity)throws Exception{
        Method build=PlayerActivity.class.getDeclaredMethod("buildPlayerUi",android.content.SharedPreferences.class);build.setAccessible(true);build.invoke(activity,activity.getSharedPreferences("playback",0));layout(content(activity),393,852);
    }
    @Test public void realPlayerSettingsUseActionRowsAndColumnsWhilePlaybackControlsStayDistinct()throws Exception{
        try(ActivityController<PlayerActivity> life=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=life.get();playerUi(activity);call(activity,"playbackSettings");AlertDialog dialog=ShadowAlertDialog.getLatestAlertDialog();try{
                View root=dialog.getWindow().getDecorView();dialogLayout(root,393,752);playerSettings(root);footer(dialog);
                edgeTap(root,button(root,"画面"));dialogLayout(root,393,752);assertNotNull(findButton(root,"实时美颜"));playerSettings(root);light(button(root,"屏幕方向"));snapshot(root,"action-player-settings-393-dark.png");
                assertTrue("Transport controls retain their dedicated component",field(activity,"pause") instanceof PlaybackIconButton);
            }finally{dialog.dismiss();}
        }
    }

    @Test @Config(qualifiers="w320dp-h852dp-mdpi") public void actualNarrowLargeFontFilterQueueAndPlayerActionsRemainReadable()throws Exception{
        try(Fixture fixture=new Fixture();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create().start().resume().visible()){
            MainActivity activity=life.get();font(activity,1.5f);fixture.connect(activity);activity.showLibrary();waitFor(()->content(activity).findViewWithTag("card:7")!=null);call(activity,"showFilters");AlertDialog filters=ShadowAlertDialog.getLatestAlertDialog();try{
                View root=filters.getWindow().getDecorView();dialogLayout(root,320,804);ViewGroup watch=root.findViewWithTag("watchSegments");gap(watch);for(View child:visibleChildren(watch))material((Button)child,false);ViewGroup preferences=(ViewGroup)root.findViewWithTag("filterDisliked").getParent();gap(preferences);for(View child:visibleChildren(preferences))material((Button)child,false);footer(filters);snapshot(root,"action-main-filters-320-font150.png");
            }finally{filters.dismiss();}
            activity.getSharedPreferences("queue",0).edit().putString("ids","[7,8,9]").apply();activity.queueEditor();waitFor(()->ShadowAlertDialog.getLatestAlertDialog()!=filters&&ShadowAlertDialog.getLatestAlertDialog().isShowing());AlertDialog queue=ShadowAlertDialog.getLatestAlertDialog();try{
                View root=queue.getWindow().getDecorView();dialogLayout(root,320,804);LinearLayout actions=root.findViewWithTag("phoneQueueActions");gap(actions);for(View child:visibleChildren(actions))light((Button)child);ListView items=root.findViewWithTag("phoneQueueItems");assertTrue(items.getHeight()>48);assertTrue(items.getChildCount()>0);TextView title=(TextView)items.getChildAt(0);assertTrue(title.getText().length()>30);assertTrue(title.getLayout().getLineCount()<=2);assertTrue(title.getBottom()<=items.getHeight());footer(queue);snapshot(root,"action-main-queue-320-font150.png");
            }finally{queue.dismiss();}
        }
        try(ActivityController<PlayerActivity> life=Robolectric.buildActivity(PlayerActivity.class).create()){
            PlayerActivity activity=life.get();font(activity,1.5f);playerUi(activity);layout(content(activity),320,852);call(activity,"playbackSettings");AlertDialog settings=ShadowAlertDialog.getLatestAlertDialog();try{
                View root=settings.getWindow().getDecorView();dialogLayout(root,320,752);playerSettings(root);footer(settings);Rect close=inRoot(root,settings.getButton(AlertDialog.BUTTON_NEGATIVE));assertTrue("Settings footer stays in the window",close.bottom<=root.getHeight());snapshot(root,"action-player-settings-320-font150.png");
            }finally{settings.dismiss();}
        }
    }

    @Test public void sharedLightButtonsKeepRealNativeRippleAndInsetTouchWithoutParentBubbling()throws Exception{
        try(ActivityController<Activity> life=Robolectric.buildActivity(Activity.class).setup()){
            Activity activity=life.get();LinearLayout page=MediaStyle.actionColumn(activity);page.setPadding(16,16,16,16);page.setBackgroundColor(0xfff7fafc);activity.setContentView(page);Button previous=MediaStyle.action(activity,false),next=MediaStyle.action(activity,false);previous.setText("上一页");next.setText("下一页");page.addView(previous);page.addView(next);AtomicInteger clicks=new AtomicInteger(),parent=new AtomicInteger();previous.setOnClickListener(v->clicks.incrementAndGet());page.setOnClickListener(v->parent.incrementAndGet());layout(page,393,240);gap(page);material(previous,true);material(next,true);edgeTap(page,previous);assertEquals(1,clicks.get());assertEquals(0,parent.get());next.setEnabled(false);next.setOnClickListener(v->clicks.incrementAndGet());edgeTap(page,next);assertEquals(1,clicks.get());snapshot(page,"action-shared-light.png");
        }
    }
    @Test public void posterFavoriteUsesACircularScrimInsideTheFullMaterialTouchTarget()throws Exception{
        try(ActivityController<Activity> life=Robolectric.buildActivity(Activity.class).setup().visible()){
            Activity activity=life.get();android.widget.FrameLayout root=new android.widget.FrameLayout(activity);activity.setContentView(root);
            Button favorite=MediaStyle.cardIcon(activity);MediaStyle.cardMark(favorite,"heart",false);root.addView(favorite,new android.widget.FrameLayout.LayoutParams(48,48));layout(root,393,240);
            assertTrue(favorite instanceof MaterialButton);assertEquals(48,favorite.getWidth());assertEquals(48,favorite.getHeight());
            Bitmap background=Bitmap.createBitmap(48,48,Bitmap.Config.ARGB_8888);favorite.getBackground().setBounds(0,0,48,48);favorite.getBackground().draw(new Canvas(background));
            assertEquals(0,Color.alpha(background.getPixel(2,24)));assertEquals(0,Color.alpha(background.getPixel(24,2)));
            assertTrue(Color.alpha(background.getPixel(24,9))>0);assertTrue(Color.alpha(background.getPixel(9,24))>0);background.recycle();
            Bitmap painted=Bitmap.createBitmap(48,48,Bitmap.Config.ARGB_8888);favorite.draw(new Canvas(painted));int iconPixels=0;
            for(int y=8;y<40;y++)for(int x=8;x<40;x++){int pixel=painted.getPixel(x,y);if(Color.red(pixel)>180&&Color.green(pixel)>180&&Color.blue(pixel)>180)iconPixels++;}
            painted.recycle();assertTrue("Favorite glyph must actually draw; bounds="+((MaterialButton)favorite).getIcon().getBounds()+" compound="+favorite.getCompoundPaddingLeft()+","+favorite.getCompoundPaddingRight(),iconPixels>10);
            AtomicInteger clicks=new AtomicInteger();favorite.setOnClickListener(v->clicks.incrementAndGet());tap(root,2,2);assertEquals("Transparent scrim margin remains a real touch target",1,clicks.get());
            MediaStyle.cardMark(favorite,"heart",true);assertTrue(favorite.isSelected());assertEquals(net.lumen.media.ui.theme.NativeActionTokens.onPhotoScrim(true),((MaterialButton)favorite).getIconTint().getDefaultColor());
            favorite.setEnabled(false);tap(root,2,2);assertEquals(1,clicks.get());
        }
    }
}
