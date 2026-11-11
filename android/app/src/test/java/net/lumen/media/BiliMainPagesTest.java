package net.lumen.media;

import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.graphics.*;
import android.graphics.drawable.BitmapDrawable;
import android.os.Looper;
import android.view.*;
import android.widget.*;
import com.google.android.material.tabs.TabLayout;
import java.io.*;
import java.lang.reflect.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BooleanSupplier;
import okhttp3.mockwebserver.*;
import org.json.*;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.*;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.*;
import org.robolectric.shadows.ShadowAlertDialog;
import static org.junit.Assert.*;

/** Real native destinations use approved information hierarchy and existing scoped APIs. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk=33,qualifiers="w393dp-h852dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
public class BiliMainPagesTest {
    private static final String TOKEN="abcdefghijklmnopqrstuvwxyz123456";
    private Object read(Object target,String name){try{Field f=target.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(target);}catch(Exception error){throw new RuntimeException(error);}}
    private void set(Object target,String name,Object value)throws Exception{Field f=target.getClass().getDeclaredField(name);f.setAccessible(true);f.set(target,value);}
    private void call(Object target,String name)throws Exception{Method m=target.getClass().getDeclaredMethod(name);m.setAccessible(true);m.invoke(target);}
    private View root(MainActivity activity){return (View)read(activity,"root");}
    private void layout(View root,int width,int height){for(int i=0;i<3;i++){root.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(height,View.MeasureSpec.EXACTLY));root.layout(0,0,width,height);}}
    private void dialogLayout(AlertDialog dialog,int width,int maximumHeight){View root=dialog.getWindow().getDecorView();for(int i=0;i<3;i++){root.measure(View.MeasureSpec.makeMeasureSpec(width,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(maximumHeight,View.MeasureSpec.AT_MOST));root.layout(0,0,width,root.getMeasuredHeight());}}
    private void waitFor(BooleanSupplier ready)throws Exception{long until=System.currentTimeMillis()+6500;while(!ready.getAsBoolean()&&System.currentTimeMillis()<until){Thread.sleep(10);Shadows.shadowOf(Looper.getMainLooper()).idle();}assertTrue("Page did not reach expected real data state",ready.getAsBoolean());}
    private void snapshot(View root,String name)throws Exception{String dir=System.getenv("LUMEN_BILI_MAIN_SCREENSHOTS");if(dir==null)return;File out=new File(dir,"bilibili-main-"+name+".png");out.getParentFile().mkdirs();Bitmap bitmap=Bitmap.createBitmap(root.getWidth(),root.getHeight(),Bitmap.Config.ARGB_8888);root.draw(new Canvas(bitmap));try(FileOutputStream stream=new FileOutputStream(out)){bitmap.compress(Bitmap.CompressFormat.PNG,100,stream);}bitmap.recycle();}
    private TextView text(View root,String label){if(root instanceof TextView&&((TextView)root).getText().toString().equals(label))return (TextView)root;if(root instanceof ViewGroup){ViewGroup group=(ViewGroup)root;for(int i=0;i<group.getChildCount();i++){TextView found=text(group.getChildAt(i),label);if(found!=null)return found;}}return null;}
    private Button findButton(View root,String label){if(root instanceof Button&&((Button)root).getText().toString().equals(label))return (Button)root;if(root instanceof ViewGroup){ViewGroup group=(ViewGroup)root;for(int i=0;i<group.getChildCount();i++){Button found=findButton(group.getChildAt(i),label);if(found!=null)return found;}}return null;}
    private Button button(View root,String label){Button value=findButton(root,label);assertNotNull("Missing action "+label,value);return value;}
    private ImageView image(View root){if(root instanceof ImageView)return (ImageView)root;if(root instanceof ViewGroup){ViewGroup group=(ViewGroup)root;for(int i=0;i<group.getChildCount();i++){ImageView found=image(group.getChildAt(i));if(found!=null)return found;}}return null;}
    private String value(View root,String tag){TextView view=root.findViewWithTag(tag);return view==null?"":view.getText().toString();}
    private void scale(MainActivity activity,float scale){Configuration cfg=new Configuration(activity.getResources().getConfiguration());cfg.fontScale=scale;activity.getResources().updateConfiguration(cfg,activity.getResources().getDisplayMetrics());}
    private void connect(MainActivity activity,Fixture fixture)throws Exception{set(activity,"api",fixture.api());set(activity,"utilityPage","");}
    private void catalog(MainActivity activity)throws Exception{waitFor(()->root(activity).findViewWithTag("card:7")!=null);waitFor(()->activity.imageRequests.idle());}

    private static final class Fixture implements AutoCloseable {
        final MockWebServer server=new MockWebServer();final List<String> requested=new CopyOnWriteArrayList<>();final List<String> listPosts=new CopyOnWriteArrayList<>();
        volatile CountDownLatch titleArrived,titleRelease;volatile boolean failTotals;
        final Map<String,okio.Buffer> pictures=new HashMap<>();
        Fixture()throws Exception{
            pictures.put("/api/poster-coast",picture(360,540,0xff466e84));pictures.put("/api/poster-stars",picture(360,540,0xff344d7a));pictures.put("/api/poster-snow",picture(360,540,0xff738b9d));pictures.put("/api/poster-signal",picture(360,540,0xff9b7177));pictures.put("/api/files/70/thumbnail",picture(640,360,0xff497f99));pictures.put("/api/actor-photo",picture(240,240,0xff6a8792));
            server.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request)throws InterruptedException{
                String path=request.getPath();requested.add(path);String route=request.getRequestUrl().encodedPath();okio.Buffer picture=pictures.get(route);if(picture!=null)return new MockResponse().setHeader("Content-Type","image/png").setBody(picture.clone());
                try{
                    if(route.equals("/api/continue"))return json(new JSONObject().put("items",new JSONArray().put(work(7).put("cover","/api/unused-resume-poster").put("resume",new JSONObject().put("file_id",70).put("thumbnail","/api/files/70/thumbnail").put("name","S02E03 · Coast.Journal.2160p.HEVC.mkv").put("label","S02E03 · 海岛来信").put("position",2308).put("duration",3600)))));
                    if(route.equals("/api/works/7"))return json(work(7).put("files",new JSONArray().put(new JSONObject().put("id",70).put("name","Coast.Journal.2160p.HEVC.mkv").put("duration",6480))).put("resume_file_id",70).put("resume",new JSONObject().put("position",2308).put("label","已看38分钟，剩余70分钟")).put("actors",new JSONArray().put(new JSONObject().put("name","林夏").put("photo","/api/actor-photo"))).put("tags",new JSONArray().put("纪录片").put("自然")).put("overview","沿着海岸线，从晨雾中的渔港到暮色下的悬崖，记录旅途中的风景与故事。"));
                    if(route.equals("/api/works")||route.equals("/api/recommendations")){
                        String limit=request.getRequestUrl().queryParameter("limit");boolean favorite="true".equals(request.getRequestUrl().queryParameter("favorite")),watchlist="true".equals(request.getRequestUrl().queryParameter("watchlist"));String list=request.getRequestUrl().queryParameter("list");
                        if(failTotals&&"1".equals(limit))return new MockResponse().setResponseCode(503).setBody("{}");
                        int total=list!=null&&!list.isEmpty()?28:favorite?36:watchlist?12:128;JSONArray works=new JSONArray();for(int i=7;i<=10;i++)works.put(work(i));return json(new JSONObject().put("items",works).put("total",total));
                    }
                    if(route.equals("/api/filters"))return json(new JSONObject().put("tags",new JSONArray().put("自然").put("纪录片").put("旅行").put("航拍").put("宇宙")).put("actors",new JSONArray().put("林夏").put("苏晴")).put("years",new JSONArray().put("2025").put("2024")));
                    if(route.equals("/api/actresses")){JSONArray people=new JSONArray();for(String name:new String[]{"林夏","苏晴","沈宁","周念","许安","顾雨","叶遥","唐茉","陆晚"})people.put(new JSONObject().put("name",name).put("photo","/api/actor-photo").put("count",12).put("average",8.1).put("rated",6));return json(new JSONObject().put("items",people));}
                    if(route.equals("/api/stats"))return json(new JSONObject().put("seconds",311040).put("valid",128).put("sessions",184).put("movies",42).put("series",12).put("days",new JSONObject().put("2026-11-11",3600)).put("actors",new JSONArray().put(new JSONObject().put("name","林夏").put("seconds",7200))));
                    if(route.equals("/api/lists")){
                        if(request.getMethod().equals("POST")){listPosts.add(request.getBody().readUtf8());return json(new JSONObject().put("ok",true));}
                        return json(new JSONObject().put("items",new JSONArray().put(new JSONObject().put("name","高分未看").put("filters",new JSONObject().put("rating_min",8).put("watch_state","unwatched").put("sort","rating").put("descending",true))).put(new JSONObject().put("name","自然纪录").put("filters",new JSONObject().put("tags_all",new JSONArray().put("自然").put("纪录片")))).put(new JSONObject().put("name","我的4K收藏").put("filters",new JSONObject().put("favorite",true)))));
                    }
                    if(route.equals("/api/queue-titles")){CountDownLatch arrived=titleArrived,release=titleRelease;if(arrived!=null)arrived.countDown();if(release!=null)release.await(5,TimeUnit.SECONDS);return json(new JSONObject().put("titles",new JSONObject().put("7","海岸纪行：沿着海风走向群岛深处，穿过清晨港口与安静山林的漫长旅程").put("8","星夜环游").put("9","雪山之上")));}
                    if(route.equals("/api/info"))return json(new JSONObject().put("api_version",1));
                    return json(new JSONObject().put("items",new JSONArray()).put("total",0));
                }catch(Exception error){throw new RuntimeException(error);}
            }});server.start();
        }
        private static JSONObject work(int id)throws Exception{String[] titles={"海岸纪行","星夜环游","雪山之上","深空回响"},covers={"coast","stars","snow","signal"};return new JSONObject().put("id",id).put("title",titles[id-7]).put("kind",id==8?"vr":"movie").put("year",id==8?2024:2025).put("cover","/api/poster-"+covers[id-7]).put("favorite",id==8?1:0).put("watchlist",0).put("rating",8).put("file_count",1);}
        private static MockResponse json(JSONObject body){return new MockResponse().setHeader("Content-Type","application/json").setBody(body.toString());}
        private static okio.Buffer picture(int width,int height,int color){Bitmap bitmap=Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);Canvas canvas=new Canvas(bitmap);Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);paint.setShader(new LinearGradient(0,0,width,height,color,0xff14273a,Shader.TileMode.CLAMP));canvas.drawRect(0,0,width,height,paint);paint.setShader(null);paint.setColor(0xffd9e7e1);canvas.drawCircle(width*.72f,height*.2f,width*.15f,paint);paint.setColor(0xff41665d);Path mountain=new Path();mountain.moveTo(0,height*.8f);mountain.lineTo(width*.45f,height*.3f);mountain.lineTo(width,height*.9f);mountain.lineTo(width,height);mountain.lineTo(0,height);mountain.close();canvas.drawPath(mountain,paint);paint.setColor(0xff98c9c6);canvas.drawRect(0,height*.85f,width,height,paint);okio.Buffer bytes=new okio.Buffer();bitmap.compress(Bitmap.CompressFormat.PNG,100,bytes.outputStream());bitmap.recycle();return bytes;}
        Api api()throws Exception{return new Api(new Connection(server.url("/").toString(),TOKEN));}
        @Override public void close()throws IOException{if(titleRelease!=null)titleRelease.countDown();server.close();}
    }

    @Test public void homeHasSmallExactFileResumeSingleSearchAndVisibleGlobalShuffle()throws Exception{
        try(Fixture fixture=new Fixture();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create().start().resume().visible()){
            MainActivity activity=life.get();connect(activity,fixture);activity.showLibrary();catalog(activity);waitFor(()->root(activity).findViewWithTag("continueCard:70")!=null);waitFor(()->image(root(activity).findViewWithTag("continueArtwork:70")).getDrawable() instanceof BitmapDrawable);
            View root=root(activity);LinearLayout card=root.findViewWithTag("continueCard:70");assertEquals(LinearLayout.HORIZONTAL,card.getOrientation());ImageView thumbnail=image(root.findViewWithTag("continueArtwork:70"));assertTrue(thumbnail.getTag().toString().endsWith("/api/files/70/thumbnail"));assertEquals(640,((BitmapDrawable)thumbnail.getDrawable()).getBitmap().getWidth());assertEquals(ImageView.ScaleType.FIT_CENTER,thumbnail.getScaleType());assertFalse(fixture.requested.stream().anyMatch(path->path.contains("unused-resume-poster")));assertTrue(value(root,"continueTime:70").contains("0:38:28"));assertTrue(value(root,"continueTime:70").contains("0:21:32"));assertTrue(value(root,"continueIdentity:70").contains("S02E03"));assertNotNull(root.findViewWithTag("globalShuffle"));for(int width:new int[]{393,320,500,393}){layout(root,width,852);View surface=(View)card.getParent(),viewport=(View)surface.getParent().getParent();assertTrue("Resume card must follow measured window width="+width,surface.getWidth()<=viewport.getWidth());RectF bounds=new RectF(0,0,640,360);thumbnail.getImageMatrix().mapRect(bounds);assertTrue(bounds.left>=-.01f&&bounds.top>=-.01f);assertTrue(bounds.right<=thumbnail.getWidth()+.01f&&bounds.bottom<=thumbnail.getHeight()+.01f);}assertTrue(card.getHeight()<220);snapshot(root,"home-393");
            root.findViewWithTag("continuePlay:70").performClick();android.content.Intent intent=Shadows.shadowOf(activity).getNextStartedActivity();assertEquals(70,intent.getLongExtra("file_id",0));assertEquals(7,intent.getLongExtra("work_id",0));
            root.findViewWithTag("globalShuffle").performClick();AlertDialog shuffle=ShadowAlertDialog.getLatestAlertDialog();assertTrue(shuffle.isShowing());dialogLayout(shuffle,393,788);snapshot(shuffle.getWindow().getDecorView(),"shuffle-393");shuffle.getButton(AlertDialog.BUTTON_NEGATIVE).performClick();assertFalse(fixture.requested.stream().anyMatch(path->path.startsWith("/api/queue/from-browse")));
            activity.openDetail(7);waitFor(()->root(activity).findViewWithTag("detailPlay")!=null);waitFor(()->activity.imageRequests.idle());assertEquals(3,((ViewGroup)root(activity).findViewWithTag("detailPersonalActions")).getChildCount());layout(root(activity),393,852);snapshot(root(activity),"detail-393");activity.getOnBackPressedDispatcher().onBackPressed();
            scale(activity,1.5f);activity.showLibrary();catalog(activity);waitFor(()->root(activity).findViewWithTag("continueCard:70")!=null);waitFor(()->activity.imageRequests.idle());layout(root(activity),320,804);snapshot(root(activity),"home-320-font150");
        }
    }

    @Test public void libraryKeepsAllSevenCategoriesAndPeopleUsesRealPortraitsAndMovieScope()throws Exception{
        try(Fixture fixture=new Fixture();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create().start().resume().visible()){
            MainActivity activity=life.get();connect(activity,fixture);set(activity,"mainPage","library");activity.showLibrary();catalog(activity);TabLayout tabs=root(activity).findViewWithTag("libraryCategory");assertEquals(7,tabs.getTabCount());assertEquals("Fans",tabs.getTabAt(4).getText());assertEquals("女演员",tabs.getTabAt(6).getText());layout(root(activity),393,852);snapshot(root(activity),"library-393");
            String[] types={"","movie","series","vr","fans","other"};for(int index=1;index<types.length;index++){tabs=root(activity).findViewWithTag("libraryCategory");tabs.getTabAt(index).select();assertEquals(types[index],activity.kind);}
            tabs=root(activity).findViewWithTag("libraryCategory");tabs.getTabAt(6).select();waitFor(()->root(activity).findViewWithTag("actor:林夏")!=null);waitFor(()->activity.imageRequests.idle());layout(root(activity),393,852);snapshot(root(activity),"people-393");root(activity).findViewWithTag("actor:林夏").performClick();catalog(activity);assertEquals("林夏",activity.actorFilter);assertEquals("movie",activity.kind);assertTrue(fixture.requested.stream().anyMatch(path->path.contains("actor=")&&path.contains("kind=movie")));layout(root(activity),393,852);snapshot(root(activity),"actor-works-393");
            ImageView original=image(root(activity).findViewWithTag("actorIdentity"));assertTrue(original.getDrawable() instanceof BitmapDrawable);activity.actorFilter="苏晴";activity.showLibrary();catalog(activity);ImageView changed=image(root(activity).findViewWithTag("actorIdentity"));assertFalse("Changing actor must not retain the previous actor's photo",changed.getDrawable() instanceof BitmapDrawable);
            scale(activity,1.5f);activity.showLibrary();catalog(activity);layout(root(activity),320,804);snapshot(root(activity),"actor-works-320-font150");activity.actorFilter="";activity.kind="";set(activity,"actresses",true);activity.showLibrary();waitFor(()->root(activity).findViewWithTag("actor:林夏")!=null);waitFor(()->activity.imageRequests.idle());layout(root(activity),320,804);snapshot(root(activity),"people-320-font150");
        }
    }

    @Test public void mineUsesRealCountsAndUtilitiesReturnWithoutChangingThePreviousFilters()throws Exception{
        try(Fixture fixture=new Fixture();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create().start().resume().visible()){
            MainActivity activity=life.get();connect(activity,fixture);activity.kind="vr";activity.query="旅行";activity.tagsNotFilter="恐怖";activity.watchFilter="progress";call(activity,"showMine");waitFor(()->value(root(activity),"mineTotal:all").equals("128")&&value(root(activity),"mineTotal:favorite").equals("36")&&value(root(activity),"mineTotal:watchlist").equals("12"));ViewGroup quick=root(activity).findViewWithTag("mineQuickGrid");assertEquals(4,quick.getChildCount());assertNotNull(root(activity).findViewWithTag("globalShuffle"));layout(root(activity),393,852);snapshot(root(activity),"mine-393");
            button(root(activity),"观影统计").performClick();waitFor(()->text(root(activity),"86.4 小时")!=null);assertNotNull(text(root(activity),"184"));assertNotNull(text(root(activity),"42"));layout(root(activity),393,852);snapshot(root(activity),"stats-393");button(root(activity),"详细统计").performClick();AlertDialog details=ShadowAlertDialog.getLatestAlertDialog();String complete=Shadows.shadowOf(details).getMessage().toString();assertTrue(complete.contains("days"));assertTrue(complete.contains("2026-11-11"));assertTrue(complete.contains("actors"));assertTrue(complete.contains("林夏"));details.getButton(AlertDialog.BUTTON_POSITIVE).performClick();activity.getOnBackPressedDispatcher().onBackPressed();assertNotNull(root(activity).findViewWithTag("mineProfile"));assertEquals("vr",activity.kind);assertEquals("旅行",activity.query);assertEquals("恐怖",activity.tagsNotFilter);assertEquals("progress",activity.watchFilter);
            button(root(activity),"智能片单").performClick();waitFor(()->root(activity).findViewWithTag("smartList:高分未看")!=null&&root(activity).findViewWithTag("playlistCount:高分未看")!=null);waitFor(()->activity.imageRequests.idle());layout(root(activity),393,852);snapshot(root(activity),"playlists-393");root(activity).findViewWithTag("smartList:高分未看").performClick();catalog(activity);assertEquals("高分未看",activity.savedList);assertEquals("rating",activity.sortField);
            call(activity,"showMine");Api previous=activity.api;call(activity,"showConnection");assertNull(activity.api);layout(root(activity),393,852);snapshot(root(activity),"connection-393");activity.getOnBackPressedDispatcher().onBackPressed();assertSame(previous,activity.api);assertNotNull(root(activity).findViewWithTag("mineProfile"));
            fixture.failTotals=true;call(activity,"showMine");waitFor(()->fixture.requested.stream().filter(path->path.contains("limit=1")).count()>=9);Shadows.shadowOf(Looper.getMainLooper()).idle();assertEquals("—",value(root(activity),"mineTotal:all"));
        }
    }

    @Test public void newSmartListAppliesTheRealFilterDraftBeforeSaving()throws Exception{
        try(Fixture fixture=new Fixture();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create().start().resume().visible()){
            MainActivity activity=life.get();connect(activity,fixture);call(activity,"smartLists");waitFor(()->root(activity).findViewWithTag("newSmartList")!=null);root(activity).findViewWithTag("newSmartList").performClick();AlertDialog filters=ShadowAlertDialog.getLatestAlertDialog();View panel=filters.getWindow().getDecorView();waitFor(()->text(panel,"输入搜索或下拉选择，多个条件同时生效。")!=null);button(panel,"未看").performClick();panel.findViewWithTag("filterDisliked").performClick();
            TextView tagLabel=text(panel,"标签");LinearLayout form=(LinearLayout)tagLabel.getParent();ViewGroup row=(ViewGroup)form.getChildAt(form.indexOfChild(tagLabel)+1);((EditText)row.getChildAt(0)).setText("自然");dialogLayout(filters,393,788);ViewGroup suggestions=panel.findViewWithTag("filterTagSuggestions");assertTrue(suggestions.getChildCount()>0);com.google.android.material.chip.Chip suggestion=(com.google.android.material.chip.Chip)suggestions.getChildAt(0);assertEquals(net.lumen.media.ui.theme.NativeActionTokens.surfaceContainerHigh(true),suggestion.getChipBackgroundColor().getDefaultColor());assertEquals(net.lumen.media.ui.theme.NativeActionTokens.onSurface(true),suggestion.getCurrentTextColor());assertEquals(0f,suggestion.getChipStrokeWidth(),0f);assertTrue(suggestion.getHeight()>=48);snapshot(panel,"filters-393");filters.getButton(AlertDialog.BUTTON_POSITIVE).performClick();AlertDialog save=ShadowAlertDialog.getLatestAlertDialog();assertNotSame(filters,save);EditText input=findEdit(save.getWindow().getDecorView());assertNotNull(input);input.setText("自然未看");save.getButton(AlertDialog.BUTTON_POSITIVE).performClick();waitFor(()->fixture.listPosts.size()==1);JSONObject stored=new JSONObject(fixture.listPosts.get(0));assertEquals("自然未看",stored.getString("name"));JSONObject conditions=stored.getJSONObject("filters");assertEquals("unwatched",conditions.getString("watch_state"));assertTrue(conditions.getBoolean("disliked"));assertEquals("自然",conditions.getJSONArray("tags_all").getString(0));scale(activity,1.5f);call(activity,"showFilters");AlertDialog enlarged=ShadowAlertDialog.getLatestAlertDialog();waitFor(()->text(enlarged.getWindow().getDecorView(),"输入搜索或下拉选择，多个条件同时生效。")!=null);dialogLayout(enlarged,320,752);snapshot(enlarged.getWindow().getDecorView(),"filters-320-font150");enlarged.getButton(AlertDialog.BUTTON_NEGATIVE).performClick();
        }
    }
    private EditText findEdit(View root){if(root instanceof EditText)return (EditText)root;if(root instanceof ViewGroup){ViewGroup group=(ViewGroup)root;for(int i=0;i<group.getChildCount();i++){EditText found=findEdit(group.getChildAt(i));if(found!=null)return found;}}return null;}

    private DragEvent drag(int action,float x,float y,int index)throws Exception{Constructor<DragEvent> constructor=DragEvent.class.getDeclaredConstructor();constructor.setAccessible(true);DragEvent event=constructor.newInstance();org.robolectric.util.ReflectionHelpers.setField(event,"mAction",action);org.robolectric.util.ReflectionHelpers.setField(event,"mX",x);org.robolectric.util.ReflectionHelpers.setField(event,"mY",y);org.robolectric.util.ReflectionHelpers.setField(event,"mLocalState",Integer.valueOf(index));return event;}
    private AlertDialog queue(MainActivity activity)throws Exception{activity.queueEditor();waitFor(()->{AlertDialog dialog=ShadowAlertDialog.getLatestAlertDialog();return dialog!=null&&dialog.isShowing()&&dialog.getWindow().getDecorView().findViewWithTag("phoneQueueItems")!=null;});return ShadowAlertDialog.getLatestAlertDialog();}
    @Test public void queueDragReallyReordersAndRetainsThePlayingIdAndAccessibleButtons()throws Exception{
        try(Fixture fixture=new Fixture();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create().start().resume().visible()){
            MainActivity activity=life.get();connect(activity,fixture);SharedPreferences prefs=activity.getSharedPreferences("queue",0);prefs.edit().putString("ids","[7,8,9]").putInt("index",1).apply();AlertDialog dialog=queue(activity);dialogLayout(dialog,393,788);ListView list=dialog.getWindow().getDecorView().findViewWithTag("phoneQueueItems");assertEquals(3,list.getChildCount());list.performItemClick(list.getChildAt(0),0,list.getAdapter().getItemId(0));View target=list.getChildAt(2);assertTrue(list.dispatchDragEvent(drag(DragEvent.ACTION_DRAG_STARTED,0,0,0)));assertTrue(list.dispatchDragEvent(drag(DragEvent.ACTION_DROP,list.getWidth()/2f,target.getTop()+target.getHeight()/2f,0)));list.dispatchDragEvent(drag(DragEvent.ACTION_DRAG_ENDED,0,0,0));assertEquals("[8,9,7]",prefs.getString("ids",""));assertEquals("Playing #8 must stay selected as the playing item",0,prefs.getInt("index",-1));
            button(dialog.getWindow().getDecorView(),"上移").performClick();assertEquals("[8,7,9]",prefs.getString("ids",""));assertEquals(0,prefs.getInt("index",-1));dialogLayout(dialog,393,788);snapshot(dialog.getWindow().getDecorView(),"queue-393");dialog.dismiss();scale(activity,1.5f);dialog=queue(activity);dialogLayout(dialog,320,752);ViewGroup controls=dialog.getWindow().getDecorView().findViewWithTag("phoneQueueActions");for(int i=0;i<controls.getChildCount();i++){Button action=(Button)controls.getChildAt(i);assertNull(((com.google.android.material.button.MaterialButton)action).getIcon());assertEquals("Narrow enlarged queue action must stay on one line: "+action.getText(),1,action.getLayout().getLineCount());assertTrue(action.getPaint().measureText(action.getText().toString())<=action.getWidth()-action.getCompoundPaddingLeft()-action.getCompoundPaddingRight());assertTrue(action.getWidth()>=48);assertTrue(action.getHeight()>=48);}snapshot(dialog.getWindow().getDecorView(),"queue-320-font150");dialog.dismiss();
        }
    }

    @Test public void queueTitleArrivalAndOpenEditorCannotOverwriteAReplacedQueue()throws Exception{
        try(Fixture fixture=new Fixture();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create().start().resume().visible()){
            MainActivity activity=life.get();connect(activity,fixture);SharedPreferences prefs=activity.getSharedPreferences("queue",0);prefs.edit().putString("ids","[7,8,9]").putInt("index",1).apply();fixture.titleArrived=new CountDownLatch(1);fixture.titleRelease=new CountDownLatch(1);activity.queueEditor();assertTrue(fixture.titleArrived.await(2,TimeUnit.SECONDS));prefs.edit().putString("ids","[90,91]").putInt("index",1).apply();fixture.titleRelease.countDown();waitFor(()->"手机队列已更新，请重新打开队列".equals(org.robolectric.shadows.ShadowToast.getTextOfLatestToast()));assertEquals("[90,91]",prefs.getString("ids",""));AlertDialog old=ShadowAlertDialog.getLatestAlertDialog();assertTrue(old==null||!old.isShowing());
            fixture.titleArrived=null;fixture.titleRelease=null;prefs.edit().putString("ids","[7,8,9]").putInt("index",1).apply();AlertDialog editor=queue(activity);prefs.edit().putString("ids","[90,91]").putInt("index",1).apply();button(editor.getWindow().getDecorView(),"下移").performClick();assertFalse(editor.isShowing());assertEquals("[90,91]",prefs.getString("ids",""));assertEquals(1,prefs.getInt("index",-1));
        }
    }
}
