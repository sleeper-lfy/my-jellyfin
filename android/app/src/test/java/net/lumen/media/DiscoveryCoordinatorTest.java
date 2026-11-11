package net.lumen.media;

import android.os.Bundle;
import android.os.Looper;
import org.json.*;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.*;
import org.robolectric.annotation.Config;
import org.robolectric.android.controller.ActivityController;
import okhttp3.mockwebserver.*;
import java.lang.reflect.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class) @Config(sdk=33)
public class DiscoveryCoordinatorTest {
    private void set(Object target,String name,Object value)throws Exception{Field f=target.getClass().getDeclaredField(name);f.setAccessible(true);f.set(target,value);}
    private Object get(Object target,String name)throws Exception{Field f=target.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(target);}
    private Object call(Object target,String name)throws Exception{Method m=target.getClass().getDeclaredMethod(name);m.setAccessible(true);return m.invoke(target);}
    private JSONObject detail(MainActivity page){try{return (JSONObject)get(page,"detail");}catch(Exception error){throw new RuntimeException(error);}}
    private void waitFor(java.util.function.BooleanSupplier ready)throws Exception{long until=System.currentTimeMillis()+6000;while(!ready.getAsBoolean()&&System.currentTimeMillis()<until){Thread.sleep(10);Shadows.shadowOf(Looper.getMainLooper()).idle();}assertTrue(ready.getAsBoolean());}
    private String catalog(int count)throws Exception{JSONArray items=new JSONArray();for(int i=0;i<count;i++)items.put(new JSONObject().put("id",7+i).put("title","海岸纪行 · 第 "+(i+1)+" 章").put("kind","movie").put("favorite",0));return new JSONObject().put("items",items).put("total",count).toString();}
    private MockWebServer server(int count)throws Exception{String catalog=catalog(count);MockWebServer server=new MockWebServer();server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){String path=request.getPath();if(path.startsWith("/api/filters"))return new MockResponse().setBody("{\"tags\":[\"旅行\",\"自然\",\"剧情\"],\"actors\":[\"示例演员\"],\"years\":[2024,2020]}");if(path.startsWith("/api/discovery/providers"))return new MockResponse().setBody("{\"items\":[]}");if(path.startsWith("/api/discovery/search/"))return new MockResponse().setBody("{\"status\":\"running\"}");return new MockResponse().setBody(catalog);}});server.start();return server;}
    private MainActivity show(ActivityController<MainActivity> life,MockWebServer server,boolean online)throws Exception{
        MainActivity page=life.get();page.api=new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456"));
        // Match the successful-connection path when injecting its Api directly into the fixture.
        set(page,"utilityPage","");set(page,"mainPage","discover");page.discovery=true;page.discoveryOnline=online;page.showLibrary();return page;
    }
    @Test public void appliedFieldsUseExistingQueryParamsAndSnapshotDraftsStayIndependent()throws Exception{
        try(MockWebServer server=server(3);ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            MainActivity page=show(life,server,false);waitFor(()->page.discoveryCoordinator.snapshot().items.size()==3);DiscoveryUiState before=page.discoveryCoordinator.snapshot();DiscoveryFilters draft=before.filters.copy();draft.tag="旅行";draft.actor="示例演员";draft.yearMin="2020";draft.yearMax="2024";draft.ratingMin="7";draft.tagsAll="旅行,自然";draft.tagsAny="剧情";draft.tagsNot="不想看的类型";page.discoveryCoordinator.onApplyFilters(draft);String path=page.listPath();assertTrue(path.contains("year_min=2020"));assertTrue(path.contains("year_max=2024"));assertTrue(path.contains("rating_min=7"));assertTrue(path.contains("tags_all="+android.net.Uri.encode("旅行,自然")));assertEquals("",before.filters.yearMin);draft.yearMin="1900";assertEquals("2020",page.yearMinFilter);boolean immutable=false;try{before.items.clear();}catch(UnsupportedOperationException expected){immutable=true;}assertTrue(immutable);assertEquals(3,before.items.size());page.discoveryCoordinator.onRemoveChip("all","旅行");assertEquals("自然",page.tagsAllFilter);assertTrue(page.listPath().contains("tags_all="+android.net.Uri.encode("自然")));
        }
    }
    @Test public void manyTagsRemainIndividualChipsAndClearingOnlineFiltersKeepsTheHitSet()throws Exception{
        try(MockWebServer server=server(0);ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            MainActivity page=life.get();page.api=new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456"));set(page,"mainPage","discover");page.discovery=true;page.discoveryOnline=true;page.discoveryResultIds=new JSONArray("[7,8]");page.query="站点片名";page.tagFilter="站点标签";page.discoveryResultTag="结果标签";List<String> selected=new ArrayList<>();for(int i=0;i<16;i++)selected.add("条件"+i);page.tagsAllFilter=android.text.TextUtils.join(",",selected);page.discoverySearchTask="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";page.discoverySearchState="done";page.showLibrary();assertEquals(17,page.discoveryCoordinator.snapshot().chips.size());page.discoveryCoordinator.onRemoveChip("all","条件0");assertEquals(15,page.tagsAllFilter.split(",").length);page.discoveryCoordinator.onClearFilters();assertTrue(page.discoveryOnline);assertEquals("[7,8]",page.discoveryResultIds.toString());assertEquals("站点片名",page.query);assertEquals("站点标签",page.tagFilter);assertEquals("",page.discoveryResultTag);assertTrue(page.listPath().contains("&q=&tag_q="));assertTrue(page.listPath().endsWith("&ids=7,8"));assertTrue(page.discoveryCoordinator.snapshot().chips.isEmpty());
        }
    }
    @Test public void aBusySiteTaskDoesNotAdoptAnUnsubmittedTitleOrTag()throws Exception{
        try(MockWebServer server=server(0);ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            MainActivity page=life.get();page.api=new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456"));set(page,"mainPage","discover");page.discovery=true;page.discoveryOnline=true;page.query="原片名";page.tagFilter="原站点标签";page.discoverySearchTask="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";page.discoverySearchState="running";page.showLibrary();page.discoveryCoordinator.onSubmitSearch("新的未提交片名");page.discoveryCoordinator.onSelectSuggestion("tag","新标签");assertEquals("原片名",page.query);assertEquals("原站点标签",page.tagFilter);assertEquals("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",page.discoverySearchTask);assertTrue(page.discoveryCoordinator.snapshot().busy);
        }
    }
    @Test public void restorationIgnoresTemporaryGridClampsUntilTargetDataExists()throws Exception{
        try(MockWebServer server=server(12);ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            MainActivity page=show(life,server,false);waitFor(()->page.discoveryCoordinator.snapshot().items.size()==12);page.discoveryCoordinator.onScrollPosition(8,24);Bundle saved=(Bundle)call(page,"browseState");Method restore=MainActivity.class.getDeclaredMethod("restoreBrowseState",Bundle.class);restore.setAccessible(true);restore.invoke(page,saved);page.discoveryCoordinator.onScrollPosition(0,0);assertEquals(8,page.discoveryGridIndex);waitFor(()->page.discoveryCoordinator.snapshot().items.size()==12&&!page.discoveryCoordinator.snapshot().loading);page.discoveryCoordinator.onScrollPosition(0,0);assertEquals(8,page.discoveryGridIndex);page.discoveryCoordinator.onScrollPosition(8,24);assertEquals(8,page.discoveryGridIndex);assertEquals(24,page.discoveryGridScroll);assertFalse(page.discoveryCoordinator.snapshot().restoringScroll);saved.putInt("discoveryGridIndex",20);restore.invoke(page,saved);waitFor(()->page.discoveryCoordinator.snapshot().items.size()==12&&!page.discoveryCoordinator.snapshot().loading);page.discoveryCoordinator.onScrollPosition(10,24);assertEquals(10,page.discoveryGridIndex);assertFalse("odd final item restores to its two-column row start",page.discoveryCoordinator.snapshot().restoringScroll);page.onBackPressed();assertFalse(page.discovery);assertEquals("home",get(page,"mainPage"));
        }
    }
    @Test public void favoriteRemovalRebasesAnInFlightPageAndKeepsPublishedSnapshotsImmutable()throws Exception{
        List<String> routes=new CopyOnWriteArrayList<>();AtomicBoolean removed=new AtomicBoolean();CountDownLatch nextRequested=new CountDownLatch(1),releaseNext=new CountDownLatch(1);
        String first="{\"items\":[{\"id\":7,\"title\":\"第一部\",\"favorite\":1},{\"id\":8,\"title\":\"第二部\",\"favorite\":1}],\"total\":4}";
        String following="{\"items\":[{\"id\":9,\"title\":\"第三部\",\"favorite\":1},{\"id\":10,\"title\":\"第四部\",\"favorite\":1}],\"total\":3}";
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request)throws InterruptedException{String route=request.getPath();if(route.startsWith("/api/filters"))return new MockResponse().setBody("{\"tags\":[],\"actors\":[],\"years\":[]}");if(route.endsWith("/personal")){removed.set(true);return new MockResponse().setBody("{\"personal\":{\"favorite\":0,\"liked\":0,\"disliked\":0}}");}routes.add(route);if(route.contains("offset=2")){nextRequested.countDown();releaseNext.await();return new MockResponse().setBody(following);}return new MockResponse().setBody(route.contains("offset=1")?following:first);}});server.start();MainActivity page=life.get();page.api=new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456"));page.discovery=true;page.favorites=true;set(page,"mainPage","discover");page.showLibrary();waitFor(()->page.discoveryCoordinator.snapshot().items.size()==2);DiscoveryUiState before=page.discoveryCoordinator.snapshot();page.discoveryCoordinator.onLoadMore();try{assertTrue(nextRequested.await(3,TimeUnit.SECONDS));page.discoveryCoordinator.onToggleFavorite(7);waitFor(()->removed.get()&&!page.browseRecords.containsKey(7L));}finally{releaseNext.countDown();}waitFor(()->page.discoveryCoordinator.snapshot().items.size()==3);assertTrue(routes.stream().anyMatch(route->route.contains("offset=1")));assertEquals(3,page.offset);assertEquals(3,page.discoveryCoordinator.snapshot().total);assertTrue(before.items.get(0).favorite);assertTrue(page.browseRecords.containsKey(8L));assertTrue(page.browseRecords.containsKey(9L));assertTrue(page.browseRecords.containsKey(10L));
        }
    }
    @Test public void aFailedFavoriteWriteRestoresSelectionAndNeverNavigates()throws Exception{
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){if(request.getPath().endsWith("/personal"))return new MockResponse().setResponseCode(503);return new MockResponse().setBody(request.getPath().startsWith("/api/filters")?"{\"tags\":[],\"actors\":[],\"years\":[]}":"{\"items\":[{\"id\":7,\"title\":\"海岸纪行\",\"favorite\":1}],\"total\":1}");}});server.start();MainActivity page=show(life,server,false);waitFor(()->page.discoveryCoordinator.snapshot().items.size()==1);page.discoveryCoordinator.onToggleFavorite(7);waitFor(()->!page.discoveryCoordinator.snapshot().items.get(0).pending);assertTrue(page.discoveryCoordinator.snapshot().items.get(0).favorite);assertEquals(0,page.detailId);assertTrue(page.browseRecords.containsKey(7L));
        }
    }
    @Test public void favoriteCompletionAfterDetailBackPublishesForTheSameCoordinator()throws Exception{
        CountDownLatch posted=new CountDownLatch(1),finishPost=new CountDownLatch(1);
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request)throws InterruptedException{String route=request.getPath();if(route.endsWith("/personal")){posted.countDown();finishPost.await();return new MockResponse().setBody("{\"personal\":{\"favorite\":1,\"liked\":1,\"disliked\":0}}");}if(route.startsWith("/api/filters"))return new MockResponse().setBody("{\"tags\":[],\"actors\":[],\"years\":[]}");if(route.equals("/api/works/7"))return new MockResponse().setBody("{\"id\":7,\"title\":\"海岸纪行\",\"kind\":\"movie\",\"files\":[],\"tags\":[]}");return new MockResponse().setBody("{\"items\":[{\"id\":7,\"title\":\"海岸纪行\",\"favorite\":0}],\"total\":1}");}});server.start();MainActivity page=show(life,server,false);waitFor(()->page.discoveryCoordinator.snapshot().items.size()==1);DiscoveryCoordinator original=page.discoveryCoordinator;original.onToggleFavorite(7);try{assertTrue(posted.await(3,TimeUnit.SECONDS));original.onOpenMovie(7);page.onBackPressed();assertSame(original,page.discoveryCoordinator);assertEquals(0,page.detailId);assertTrue(original.snapshot().items.get(0).pending);}finally{finishPost.countDown();}waitFor(()->!original.snapshot().items.get(0).pending);assertTrue(original.snapshot().items.get(0).favorite);
        }
    }
    @Test @Config(qualifiers="notnight") public void officialEdgeToEdgeUsesDarkIconsInLightModeAndLegacyPagesRestoreTheirBars()throws Exception{
        try(MockWebServer server=server(0);ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            MainActivity page=show(life,server,false);androidx.core.view.WindowInsetsControllerCompat bars=new androidx.core.view.WindowInsetsControllerCompat(page.getWindow(),page.getWindow().getDecorView());assertTrue(bars.isAppearanceLightStatusBars());assertTrue(bars.isAppearanceLightNavigationBars());page.discoveryCoordinator.onNavigatePrimary("home");assertFalse(bars.isAppearanceLightStatusBars());assertFalse(bars.isAppearanceLightNavigationBars());assertEquals(MediaStyle.BG,page.getWindow().getStatusBarColor());assertEquals(MediaStyle.BG,page.getWindow().getNavigationBarColor());
        }
    }
    @Test @Config(qualifiers="night") public void officialEdgeToEdgeUsesLightIconsInDarkMode()throws Exception{
        try(MockWebServer server=server(0);ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            MainActivity page=show(life,server,false);androidx.core.view.WindowInsetsControllerCompat bars=new androidx.core.view.WindowInsetsControllerCompat(page.getWindow(),page.getWindow().getDecorView());assertFalse(bars.isAppearanceLightStatusBars());assertFalse(bars.isAppearanceLightNavigationBars());
        }
    }

    @Test public void anInPlaceConfigurationChangeKeepsTheCoordinatorAndGridState()throws Exception{
        try(MockWebServer server=server(3);ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            MainActivity page=show(life,server,false);waitFor(()->page.discoveryCoordinator.snapshot().items.size()==3);DiscoveryCoordinator original=page.discoveryCoordinator;original.onScrollPosition(2,24);int generation=page.generation;
            android.content.res.Configuration changed=new android.content.res.Configuration(page.getResources().getConfiguration());changed.fontScale=1.2f;changed.uiMode=(changed.uiMode&~android.content.res.Configuration.UI_MODE_NIGHT_MASK)|android.content.res.Configuration.UI_MODE_NIGHT_NO;page.getResources().updateConfiguration(changed,page.getResources().getDisplayMetrics());page.onConfigurationChanged(changed);page.getWindow().getDecorView().dispatchConfigurationChanged(changed);
            assertSame(original,page.discoveryCoordinator);assertEquals(generation,page.generation);assertEquals(2,page.discoveryGridIndex);assertEquals(24,page.discoveryGridScroll);assertEquals(3,page.discoveryCoordinator.snapshot().items.size());assertTrue(new androidx.core.view.WindowInsetsControllerCompat(page.getWindow(),page.getWindow().getDecorView()).isAppearanceLightStatusBars());
        }
    }

    @Test public void aFavoritePostMergesIntoTheCurrentRecordAfterRefreshReturnsOldPersonalData()throws Exception{favoritePostAfterRefresh(false);}
    @Test public void aFavoritePostDoesNotReviveARowRemovedByRefresh()throws Exception{favoritePostAfterRefresh(true);}
    private void favoritePostAfterRefresh(boolean removedByRefresh)throws Exception{
        CountDownLatch posted=new CountDownLatch(1),finishPost=new CountDownLatch(1);AtomicInteger catalogReads=new AtomicInteger();
        String oldCatalog="{\"items\":[{\"id\":7,\"title\":\"海岸纪行\",\"favorite\":0,\"rating\":4}],\"total\":1}";
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request)throws InterruptedException{
                String route=request.getPath();
                if(route.endsWith("/personal")){posted.countDown();finishPost.await();return new MockResponse().setBody("{\"personal\":{\"favorite\":1,\"liked\":1,\"disliked\":0,\"rating\":4}}");}
                if(route.startsWith("/api/filters"))return new MockResponse().setBody("{\"tags\":[],\"actors\":[],\"years\":[]}");
                int read=catalogReads.incrementAndGet();return new MockResponse().setBody(removedByRefresh&&read>1?"{\"items\":[],\"total\":0}":oldCatalog);
            }});server.start();MainActivity page=show(life,server,false);waitFor(()->page.discoveryCoordinator.snapshot().items.size()==1);DiscoveryCoordinator coordinator=page.discoveryCoordinator;JSONObject originalRecord=page.browseRecords.get(7L);coordinator.onToggleFavorite(7);
            try{
                assertTrue(posted.await(3,TimeUnit.SECONDS));coordinator.onRefresh();
                waitFor(()->catalogReads.get()>=2&&!coordinator.snapshot().refreshing&&!coordinator.snapshot().loading&&(removedByRefresh?!page.browseRecords.containsKey(7L):page.browseRecords.get(7L)!=originalRecord));
                if(!removedByRefresh){assertEquals(0,page.browseRecords.get(7L).optInt("favorite"));assertTrue(coordinator.snapshot().items.get(0).favorite);assertTrue(coordinator.snapshot().items.get(0).pending);}
            }finally{finishPost.countDown();}
            waitFor(()->{try{return ((Map<?,?>)get(coordinator,"favorites")).isEmpty();}catch(Exception error){throw new RuntimeException(error);}});
            if(removedByRefresh){assertFalse(page.browseRecords.containsKey(7L));assertTrue(coordinator.snapshot().items.isEmpty());assertEquals(0,coordinator.snapshot().total);}else{assertNotSame(originalRecord,page.browseRecords.get(7L));assertEquals(1,page.browseRecords.get(7L).optInt("favorite"));assertEquals(1,page.browseRecords.get(7L).optInt("liked"));assertEquals(4,page.browseRecords.get(7L).optInt("rating"));assertTrue(coordinator.snapshot().items.get(0).favorite);assertFalse(coordinator.snapshot().items.get(0).pending);}
        }
    }

    @Test public void aFavoriteConfirmedWhileOldDetailIsVisibleSurvivesBack()throws Exception{favoritePostDuringDetail(false);}
    @Test public void aDetailReadStartedBeforeFavoriteConfirmationCannotRestoreItsOldSnapshot()throws Exception{favoritePostDuringDetail(true);}
    private void favoritePostDuringDetail(boolean delayDetail)throws Exception{
        CountDownLatch posted=new CountDownLatch(1),finishPost=new CountDownLatch(1),detailRequested=new CountDownLatch(1),finishDetail=new CountDownLatch(1);
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request)throws InterruptedException{
                String route=request.getPath();
                if(route.endsWith("/personal")){posted.countDown();finishPost.await();return new MockResponse().setBody("{\"personal\":{\"favorite\":1,\"liked\":1,\"disliked\":0,\"watchlist\":0,\"rating\":4}}");}
                if(route.startsWith("/api/filters"))return new MockResponse().setBody("{\"tags\":[],\"actors\":[],\"years\":[]}");
                if(route.equals("/api/works/7")){detailRequested.countDown();if(delayDetail)finishDetail.await();return new MockResponse().setBody("{\"id\":7,\"title\":\"海岸纪行\",\"kind\":\"movie\",\"favorite\":0,\"liked\":0,\"disliked\":0,\"rating\":4,\"files\":[],\"tags\":[],\"actors\":[]}");}
                return new MockResponse().setBody("{\"items\":[{\"id\":7,\"title\":\"海岸纪行\",\"favorite\":0,\"rating\":4}],\"total\":1}");
            }});server.start();MainActivity page=show(life,server,false);waitFor(()->page.discoveryCoordinator.snapshot().items.size()==1);DiscoveryCoordinator coordinator=page.discoveryCoordinator;coordinator.onToggleFavorite(7);
            try{
                assertTrue(posted.await(3,TimeUnit.SECONDS));coordinator.onOpenMovie(7);assertTrue(detailRequested.await(3,TimeUnit.SECONDS));
                if(!delayDetail){waitFor(()->page.renderedDetailId==7);assertEquals(0,detail(page).optInt("favorite"));}
                finishPost.countDown();waitFor(()->{try{return ((Map<?,?>)get(coordinator,"favorites")).isEmpty();}catch(Exception error){throw new RuntimeException(error);}});assertEquals(1,page.browseRecords.get(7L).optInt("favorite"));
                finishDetail.countDown();waitFor(()->page.renderedDetailId==7&&detail(page).optInt("favorite")==1);assertEquals(1,detail(page).optInt("liked"));assertEquals(4,detail(page).optInt("rating"));
                android.widget.Button favorite=page.getWindow().getDecorView().findViewWithTag("mark:7:favorite");assertEquals("取消收藏",favorite.getContentDescription());page.onBackPressed();assertSame(coordinator,page.discoveryCoordinator);assertEquals(0,page.detailId);assertEquals(1,page.browseRecords.get(7L).optInt("favorite"));assertTrue(coordinator.snapshot().items.get(0).favorite);assertFalse(coordinator.snapshot().items.get(0).pending);
            }finally{finishPost.countDown();finishDetail.countDown();}
        }
    }

    @Test public void newerDetailFavoriteAndRatingEditsWinOverAnOlderFullPersonalResponse()throws Exception{
        CountDownLatch posted=new CountDownLatch(1),finishPost=new CountDownLatch(1);AtomicInteger writes=new AtomicInteger();JSONObject canonical=new JSONObject("{\"favorite\":0,\"liked\":0,\"disliked\":0,\"watchlist\":0,\"rating\":4}");
        try(MockWebServer server=new MockWebServer();ActivityController<MainActivity> life=Robolectric.buildActivity(MainActivity.class).create()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request)throws InterruptedException{
                String route=request.getPath();
                if(route.endsWith("/personal")){
                    if(writes.incrementAndGet()==1){posted.countDown();finishPost.await();return new MockResponse().setBody("{\"personal\":{\"favorite\":1,\"liked\":1,\"disliked\":0,\"watchlist\":0,\"rating\":4}}");}
                    try{synchronized(canonical){JSONObject patch=new JSONObject(request.getBody().readUtf8());if(patch.has("rating"))canonical.put("rating",patch.get("rating"));if(patch.has("favorite")){int value=patch.optBoolean("favorite")?1:0;canonical.put("favorite",value).put("liked",value).put("disliked",0);}return new MockResponse().setBody(new JSONObject().put("personal",canonical).toString());}}catch(JSONException error){return new MockResponse().setResponseCode(500);}
                }
                if(route.startsWith("/api/filters"))return new MockResponse().setBody("{\"tags\":[],\"actors\":[],\"years\":[]}");
                if(route.equals("/api/works/7"))return new MockResponse().setBody("{\"id\":7,\"title\":\"海岸纪行\",\"kind\":\"movie\",\"favorite\":0,\"liked\":0,\"disliked\":0,\"watchlist\":0,\"rating\":4,\"files\":[],\"tags\":[],\"actors\":[]}");
                return new MockResponse().setBody("{\"items\":[{\"id\":7,\"title\":\"海岸纪行\",\"favorite\":0,\"rating\":4}],\"total\":1}");
            }});server.start();MainActivity page=show(life,server,false);waitFor(()->page.discoveryCoordinator.snapshot().items.size()==1);DiscoveryCoordinator coordinator=page.discoveryCoordinator;coordinator.onToggleFavorite(7);
            try{
                assertTrue(posted.await(3,TimeUnit.SECONDS));coordinator.onOpenMovie(7);waitFor(()->page.renderedDetailId==7);android.widget.Button favorite=page.getWindow().getDecorView().findViewWithTag("mark:7:favorite");favorite.performClick();waitFor(()->favorite.isEnabled()&&detail(page).optInt("favorite")==1);favorite.performClick();waitFor(()->favorite.isEnabled()&&detail(page).optInt("favorite")==0);
                android.widget.Button score=page.getWindow().getDecorView().findViewWithTag("rating:7");score.performClick();android.app.AlertDialog rating=org.robolectric.shadows.ShadowAlertDialog.getLatestAlertDialog();rating.getListView().performItemClick(null,8,8);waitFor(()->detail(page).optInt("rating")==8);finishPost.countDown();waitFor(()->{try{return ((Map<?,?>)get(coordinator,"favorites")).isEmpty();}catch(Exception error){throw new RuntimeException(error);}});
                assertEquals(0,detail(page).optInt("favorite"));assertEquals(0,detail(page).optInt("liked"));assertEquals(8,detail(page).optInt("rating"));assertEquals("加入收藏",favorite.getContentDescription());assertEquals("8 分",score.getText().toString());page.onBackPressed();assertEquals(0,page.browseRecords.get(7L).optInt("favorite"));assertEquals(8,page.browseRecords.get(7L).optInt("rating"));assertFalse(coordinator.snapshot().items.get(0).favorite);assertFalse(coordinator.snapshot().items.get(0).pending);
            }finally{finishPost.countDown();}
        }
    }

}
