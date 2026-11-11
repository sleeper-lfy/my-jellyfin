package net.lumen.media;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.os.Bundle;
import android.text.InputType;
import android.util.LruCache;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends androidx.activity.ComponentActivity {
    private static final int BG=MediaStyle.BG, BLUE=MediaStyle.ACCENT, MUTED=MediaStyle.MUTED;
    final android.os.Handler downloadUpdates=new android.os.Handler(android.os.Looper.getMainLooper());
    final ExecutorService network=Executors.newFixedThreadPool(4);
    private final LruCache<String,Bitmap> pictures=new LruCache<String,Bitmap>(24*1024) {
        @Override protected int sizeOf(String key,Bitmap image){return image.getByteCount()/1024;}
    };
    final ImageRequests imageRequests=new ImageRequests(pictures);
    Api api;
    private LinearLayout root,content;
    private PosterGrid posters;
    private ScrollView detailScroll;
    String kind="",query="",tagFilter="",actorFilter="",yearMinFilter="",yearMaxFilter="",ratingMinFilter="",tagsAllFilter="",tagsAnyFilter="",tagsNotFilter="";
    private boolean actresses=false;
    boolean favorites=false,recommended=false,discovery=false,watchlistOnly=false,dislikedOnly=false;
    private String mainPage="home";
    private boolean mineLanding=false;
    private String utilityPage="",actorPhoto="",actorPhotoName="";
    private boolean creatingSmartList;
    private Api connectionReturn;
    private android.view.ViewGroup peopleGrid;
    private static final String[] GLOBAL_SHUFFLE_KINDS={"","movie","series","vr","fans","other"};
    private int shuffleRequest;
    int offset=0,generation=0;
    long detailId=0,renderedDetailId=0;
    private boolean returned=false;
    private JSONObject detail;
    private static final String[] PERSONAL_FIELDS={"favorite","liked","disliked","watchlist","rating"};
    private Api personalClient;
    private long personalIntent,personalConfirmation;
    private final java.util.Map<Long,PersonalState> personalStates=new java.util.HashMap<>();
    private static final class PersonalState {
        final java.util.Map<String,Long> intents=new java.util.HashMap<>();
        final java.util.Map<String,PersonalValue> confirmed=new java.util.HashMap<>();
    }
    private static final class PersonalValue {
        final Object value;final long intent,confirmation;
        PersonalValue(Object value,long intent,long confirmation){this.value=value;this.intent=intent;this.confirmation=confirmation;}
    }
    private LinearLayout browseRoot;
    final java.util.Map<Long,JSONObject> browseRecords=new java.util.HashMap<>();
    String sortField="added",watchFilter="",savedList="";
    private boolean sortDescending=true;
    private static final String[] DISCOVERY_SORT_KEYS={"discovered","site_added","title","year","community_rating"};
    private static final String[] DISCOVERY_SORT_NAMES={"首次发现","网站收录时间","影片名称","发行年份","来源评分"};
    String discoverySort="discovered";
    boolean discoveryDescending=true;
    boolean discoveryOnline=false,discoveryProvidersLoaded=false;
    String discoveryProvider="",discoverySearchTask="",discoverySearchState="",discoverySearchMessage="",discoverySearchErrors="";
    JSONArray discoveryProviders=new JSONArray(),discoveryResultIds;
    String discoveryResultTag="";
    private int discoverySubmission=0;
    final java.util.Map<Long,Integer> browsePositions=new java.util.HashMap<>();
    private final java.util.ArrayDeque<NavigationState> navigationHistory=new java.util.ArrayDeque<>();
    private ScrollView browseScroll;
    int restoreOffset=0,restoreScroll=0;
    private TextView browseLoading,catalogCount;
    private LinearLayout continuePanel;
    DiscoveryCoordinator discoveryCoordinator;
    DiscoveryFilters discoveryNextSearchFilters;
    int discoveryGridIndex,discoveryGridScroll;
    boolean discoveryRestoreScroll;
    private androidx.activity.OnBackPressedCallback navigationBack;
    private static final class NavigationState {
        String kind,query,tag,actor,year,yearMin,yearMax,ratingMin,tagsAll,tagsAny,tagsNot,sort,watch,list,discoverySort,discoveryProvider,searchTask,searchState,searchMessage,searchErrors,resultIds,resultTag;
        boolean favorites,recommended,discovery,actresses,descending,discoveryDescending,discoveryOnline,watchlistOnly,dislikedOnly,nextSearchFilters;
        String mainPage,actorPhoto,actorPhotoName;
        int offset,scroll,detailScroll,gridIndex,gridScroll;
        JSONObject detail;
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        navigationBack=new androidx.activity.OnBackPressedCallback(true){@Override public void handleOnBackPressed(){
            if(detailId>0)returnLibrary();else if(!utilityPage.isEmpty())returnUtility();else if(!navigationHistory.isEmpty())restoreNavigation();else if(!mainPage.equals("home"))navigatePrimary("home");else{setEnabled(false);try{getOnBackPressedDispatcher().onBackPressed();}finally{setEnabled(true);}}
        }};getOnBackPressedDispatcher().addCallback(navigationBack);
        sortField=getSharedPreferences("catalog",0).getString("sort","added");sortDescending=getSharedPreferences("catalog",0).getBoolean("descending",true);
        discoverySort=getSharedPreferences("discovery",0).getString("sort","discovered");discoveryDescending=getSharedPreferences("discovery",0).getBoolean("descending",true);
        if(!java.util.Arrays.asList(DISCOVERY_SORT_KEYS).contains(discoverySort))discoverySort="discovered";
        Connection connection=Connection.load(this);
        if(connection==null)showConnection();else {api=new Api(connection);if(state!=null&&state.containsKey("browse"))restoreBrowseState(state.getBundle("browse"));else showLibrary();}
    }
    @Override protected void onStop() {if(discoveryCoordinator!=null)discoveryCoordinator.setActive(false);imageRequests.cancelPage();super.onStop();}
    @Override protected void onStart() {super.onStart();if(discoveryCoordinator!=null&&discovery&&detailId==0)discoveryCoordinator.setActive(true);if(api!=null&&root!=null)imageRequests.restore(api,root);}
    @Override protected void onResume() {
        super.onResume();
        if(returned && api!=null) { if(detailId>0)openDetail(detailId);else if(continuePanel!=null)loadContinue(); }
        returned=true;
    }
    @Override public void onConfigurationChanged(Configuration configuration) {
        super.onConfigurationChanged(configuration);
        if(api!=null&&discovery&&detailId==0&&discoveryCoordinator!=null){
            // Compose handles configuration in place, preserving modal drafts and grid state.
            discoveryEdgeToEdge();discoveryCoordinator.publish();return;
        }
        if(api!=null) { try {if(detailId>0 && detail!=null)renderDetail(detail);else {Bundle state=browseState();restoreBrowseState(state);}} catch(Exception e){message(e.getMessage());} }
    }
    @Override protected void onSaveInstanceState(Bundle state) {
        state.putBundle("browse",browseState());super.onSaveInstanceState(state);
    }
    private Bundle browseState() {
        Bundle state=new Bundle();
        String[] keys={"kind","query","tag","actor","yearMin","yearMax","ratingMin","tagsAll","tagsAny","tagsNot","sort","watch","list","discoverySort","provider","task","searchState","searchMessage","searchErrors","resultTag"};
        String[] values={kind,query,tagFilter,actorFilter,yearMinFilter,yearMaxFilter,ratingMinFilter,tagsAllFilter,tagsAnyFilter,tagsNotFilter,sortField,watchFilter,savedList,discoverySort,discoveryProvider,discoverySearchTask,discoverySearchState,discoverySearchMessage,discoverySearchErrors,discoveryResultTag};
        for(int i=0;i<keys.length;i++)state.putString(keys[i],values[i]);
        state.putString("utilityPage",utilityPage);state.putString("actorPhoto",actorPhoto);state.putString("actorPhotoName",actorPhotoName);state.putString("mainPage",mainPage);state.putBoolean("mineLanding",mineLanding);state.putBoolean("watchlistOnly",watchlistOnly);state.putBoolean("dislikedOnly",dislikedOnly);
        state.putBoolean("favorites",favorites);state.putBoolean("recommended",recommended);state.putBoolean("discovery",discovery);state.putBoolean("actresses",actresses);
        state.putBoolean("descending",sortDescending);state.putBoolean("discoveryDescending",discoveryDescending);state.putBoolean("online",discoveryOnline);
        state.putString("results",discoveryResultIds==null?null:discoveryResultIds.toString());state.putBoolean("nextSearchFilters",discoveryNextSearchFilters!=null);state.putInt("discoveryGridIndex",discoveryGridIndex);state.putInt("discoveryGridScroll",discoveryGridScroll);
        state.putInt("offset",Math.max(offset,restoreOffset));state.putInt("scroll",browseScroll==null?restoreScroll:browseScroll.getScrollY());
        return state;
    }
    private void restoreBrowseState(Bundle state) {
        if(state==null){showLibrary();return;}
        kind=state.getString("kind","");query=state.getString("query","");tagFilter=state.getString("tag","");actorFilter=state.getString("actor","");
        yearMinFilter=state.getString("yearMin","");yearMaxFilter=state.getString("yearMax","");ratingMinFilter=state.getString("ratingMin","");tagsAllFilter=state.getString("tagsAll","");tagsAnyFilter=state.getString("tagsAny","");tagsNotFilter=state.getString("tagsNot","");
        sortField=state.getString("sort","added");watchFilter=state.getString("watch","");savedList=state.getString("list","");discoverySort=state.getString("discoverySort","discovered");
        discoveryProvider=state.getString("provider","");discoverySearchTask=state.getString("task","");discoverySearchState=state.getString("searchState","idle");discoverySearchMessage=state.getString("searchMessage","");discoverySearchErrors=state.getString("searchErrors","");discoveryResultTag=state.getString("resultTag","");
        mainPage=state.getString("mainPage","home");watchlistOnly=state.getBoolean("watchlistOnly");dislikedOnly=state.getBoolean("dislikedOnly");
        favorites=state.getBoolean("favorites");recommended=state.getBoolean("recommended");discovery=state.getBoolean("discovery");actresses=state.getBoolean("actresses");
        sortDescending=state.getBoolean("descending",true);discoveryDescending=state.getBoolean("discoveryDescending",true);discoveryOnline=state.getBoolean("online");
        try{String results=state.getString("results");discoveryResultIds=results==null?null:new JSONArray(results);}catch(Exception ignored){discoveryResultIds=null;}
        discoveryGridIndex=state.getInt("discoveryGridIndex",0);discoveryGridScroll=state.getInt("discoveryGridScroll",0);discoveryRestoreScroll=discovery;
        discoveryNextSearchFilters=state.getBoolean("nextSearchFilters")?discoveryFilterState():null;
        actorPhoto=state.getString("actorPhoto","");actorPhotoName=state.getString("actorPhotoName","");String utility=state.getString("utilityPage","");if(utility.equals("stats")){showStats();return;}if(utility.equals("lists")){smartLists();return;}if(utility.equals("connection")){showConnection();return;}
        if(state.getBoolean("mineLanding")){showMine();return;}
        showLibrary();restoreOffset=Math.max(1,state.getInt("offset"));restoreScroll=state.getInt("scroll");
    }
    @Override protected void onDestroy() {if(navigationBack!=null)navigationBack.remove();if(discoveryCoordinator!=null)discoveryCoordinator.dispose();downloadUpdates.removeCallbacksAndMessages(null);imageRequests.close();network.shutdownNow();super.onDestroy();}
    private int dp(float value){return Math.round(value*getResources().getDisplayMetrics().density);}
    private TextView text(String value,int size,int color) {
        TextView view=new TextView(this);view.setText(value);view.setTextSize(size);if(size>=20)view.setTypeface(android.graphics.Typeface.DEFAULT,android.graphics.Typeface.BOLD);view.setTextColor(color);view.setFontFeatureSettings("kern");view.setPadding(0,dp(5),0,dp(5));return view;
    }
    private Button button(String title,Runnable action) {
        Button button=MediaStyle.action(this);button.setText(title);
        button.setOnClickListener(v->action.run());return button;
    }
    private AlertDialog showDialog(AlertDialog.Builder builder){
        AlertDialog dialog=builder.show();MediaStyle.dialogActions(dialog);return dialog;
    }
    private void base() {
        if(discoveryCoordinator!=null){discoveryCoordinator.setActive(false);if(detailId==0&&browseRoot==null){discoveryCoordinator.dispose();discoveryCoordinator=null;}}
        androidx.core.view.WindowCompat.setDecorFitsSystemWindows(getWindow(),true);
        getWindow().setStatusBarColor(MediaStyle.BG);getWindow().setNavigationBarColor(MediaStyle.BG);
        androidx.core.view.WindowInsetsControllerCompat bars=new androidx.core.view.WindowInsetsControllerCompat(getWindow(),getWindow().getDecorView());bars.setAppearanceLightStatusBars(false);bars.setAppearanceLightNavigationBars(false);
        imageRequests.cancelPage();
        root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(BG);root.setFitsSystemWindows(true);setContentView(root);
    }
    void message(String value){if(!isDestroyed()){if(discovery&&detailId==0&&discoveryCoordinator!=null)discoveryCoordinator.message(value);else Toast.makeText(this,value,Toast.LENGTH_LONG).show();}}
    interface Work {JSONObject run() throws Exception;}
    interface Result {void accept(JSONObject result) throws Exception;}
    void request(Work work,Result result) {
        request(work,result,null);
    }
    void request(Work work,Result result,java.util.function.Consumer<String> failed) {
        final int ticket=generation;
        network.execute(()->{
            try {JSONObject value=work.run();runOnUiThread(()->{if(isDestroyed() || ticket!=generation)return;try{result.accept(value);}catch(Exception e){message(e.getMessage());}});}
            catch(Exception e){runOnUiThread(()->{if(!isDestroyed() && ticket==generation){if(failed!=null)failed.accept(e.getMessage());else message("连接失败："+e.getMessage());}});}
        });
    }
    private void showConnection() {
        if(api!=null)connectionReturn=api;generation++;utilityPage="connection";mineLanding=false;detailId=0;api=null;navigationHistory.clear();discovery=false;discoveryProvidersLoaded=false;discoveryProviders=new JSONArray();clearDiscoverySearch();base();header("连接管理",connectionReturn!=null);
        LinearLayout panel=BiliMainUi.vertical(this);panel.setPadding(dp(16),dp(8),dp(16),dp(24));ScrollView connectionScroll=new ScrollView(this);connectionScroll.setFillViewport(true);connectionScroll.addView(panel);root.addView(connectionScroll,new LinearLayout.LayoutParams(-1,0,1));
        Connection saved=Connection.load(this);LinearLayout identity=BiliMainUi.group(this);Button current=BiliMainUi.settingsRow(this,saved==null?"连接你的家庭媒体库":"当前保存的媒体库","server",()->message("手机与电脑连接同一局域网后，填写电脑地址和访问密钥"));identity.addView(current);if(saved!=null)identity.addView(text(saved.base,13,MUTED));panel.addView(BiliMainUi.groupCard(this,identity));
        panel.addView(BiliMainUi.section(this,"服务器地址"));AutoCompleteTextView address=new SearchDropdown(this);address.setSingleLine(true);address.setHint("http://192.168.1.10:8097");address.setContentDescription("服务器地址");address.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);address.setText(getSharedPreferences("connection",0).getString("base",""));MediaStyle.field(address);
        ArrayAdapter<ServerDiscovery.Server> servers=new ArrayAdapter<>(this,android.R.layout.simple_dropdown_item_1line);address.setAdapter(servers);address.setOnItemClickListener((parent,view,position,id)->address.setText(servers.getItem(position).address,false));LinearLayout addressRow=MediaStyle.row(this);addressRow.addView(address,new LinearLayout.LayoutParams(0,dp(48),1));Button choose=button("⌄",()->{address.requestFocus();address.showDropDown();});BiliMainUi.lightAction(choose,"",false);addressRow.addView(choose,new LinearLayout.LayoutParams(dp(48),dp(48)));panel.addView(addressRow);
        panel.addView(BiliMainUi.section(this,"访问密钥"));EditText token=new EditText(this);token.setSingleLine(true);token.setHint("电脑端访问密钥");token.setContentDescription("访问密钥");token.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);if(saved!=null)token.setText(saved.token);MediaStyle.field(token);panel.addView(token,new LinearLayout.LayoutParams(-1,dp(48)));
        TextView status=text("",13,MUTED);panel.addView(status);Button connect=button("连接服务器",()->{
            try{Connection candidate=new Connection(address.getText().toString(),token.getText().toString());Api client=new Api(candidate);status.setText("正在连接…");request(()->client.get("/api/info"),info->{if(info.optInt("api_version")!=1)throw new Exception("服务端协议版本不兼容");candidate.save(this);api=client;connectionReturn=null;utilityPage="";pictures.evictAll();resetBrowseFilters();mainPage="home";showLibrary();},error->status.setText("连接失败："+error+"\n请检查电脑服务、地址和访问密钥，然后重试。"));}catch(Exception error){status.setText(error.getMessage());}
        });MediaStyle.button(connect,true,false,false);panel.addView(connect,new LinearLayout.LayoutParams(-1,-2));
        TextView discoveryStatus=text("正在发现同一局域网内的服务端…",13,MUTED);Button discover=button("发现服务器",()->{});BiliMainUi.lightAction(discover,"server",false);panel.addView(discover);panel.addView(BiliMainUi.section(this,"已发现服务器"));panel.addView(discoveryStatus);LinearLayout found=BiliMainUi.group(this);panel.addView(BiliMainUi.groupCard(this,found));
        Runnable scan=()->{final int ticket=generation;discover.setEnabled(false);servers.clear();found.removeAllViews();discoveryStatus.setText("正在发现同一局域网内的服务端…");network.execute(()->{String failure="";try{ServerDiscovery.scan(server->runOnUiThread(()->{if(!isDestroyed()&&ticket==generation){servers.add(server);servers.notifyDataSetChanged();found.addView(BiliMainUi.settingsRow(this,server.name+"\n"+server.address,"remote",()->{address.setText(server.address,false);discoveryStatus.setText("已选择 "+server.name);}));discoveryStatus.setText("发现 "+servers.getCount()+" 个服务端");}}));}catch(Exception error){failure="发现失败，可手动输入地址";}final String problem=failure;runOnUiThread(()->{if(!isDestroyed()&&ticket==generation){discover.setEnabled(true);discoveryStatus.setText(!problem.isEmpty()?problem:servers.isEmpty()?"未发现服务端。可重试或手动输入；请检查电脑服务和防火墙 UDP 8098。":"发现 "+servers.getCount()+" 个服务端，点击选择");}});});};discover.setOnClickListener(v->scan.run());scan.run();
        panel.addView(text("地址使用电脑的局域网 IPv4。电脑休眠或服务关闭时无法播放。",12,MUTED));panel.addView(BiliMainUi.settingsRow(this,"检查客户端更新","check",()->startActivity(new Intent(this,UpdateActivity.class))));
    }
    private void header(String title, boolean back) {
        LinearLayout row=MediaStyle.actionRow(this);row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(dp(16),dp(6),dp(16),dp(6));
        if(back||!navigationHistory.isEmpty()){Button previous=button("",this::onBackPressed);MediaStyle.quiet(previous,"back","返回上一页");row.addView(previous,new LinearLayout.LayoutParams(dp(48),dp(48)));}
        TextView brand=text(title,24,Color.WHITE);brand.setSingleLine(true);brand.setEllipsize(android.text.TextUtils.TruncateAt.END);brand.setMinHeight(dp(52));row.addView(brand,new LinearLayout.LayoutParams(0,-2,1));
        if(detailId>0&&detail!=null){
            Button more=button("",()->{});more.setTag("detailMore");MediaStyle.quiet(more,"more","当前影片操作");more.setOnClickListener(this::showDetailActions);row.addView(more,new LinearLayout.LayoutParams(dp(48),dp(48)));
        }else if(!utilityPage.equals("connection")){
            Button tasks=button("",mineLanding?this::showConnection:this::showTasks);MediaStyle.quiet(tasks,mineLanding?"server":"more",mineLanding?"连接管理":"电脑任务中心");row.addView(tasks,new LinearLayout.LayoutParams(dp(48),dp(48)));
        }
        root.addView(row);
    }
    private void showTasks(){if(api!=null)TaskCenter.show(this,api);}
    private void addToPhoneQueue(long workId){
        try{android.content.SharedPreferences prefs=getSharedPreferences("queue",0);JSONArray ids=new JSONArray(prefs.getString("ids","[]"));boolean found=false;for(int i=0;i<ids.length();i++)if(ids.optLong(i)==workId)found=true;if(!found)ids.put(workId);prefs.edit().putString("ids",ids.toString()).apply();message("已加入手机播放队列");}catch(Exception error){message(error.getMessage());}
    }
    private void restartCurrent(long workId,long fileId){
        if(fileId<=0){message("没有可播放的视频");return;}
        request(()->api.post("/api/works/"+workId+"/watched",new JSONObject().put("state","unwatched").put("file_id",fileId)),result->{if(detailId==workId)startPlayer(fileId,false);});
    }
    private void showDetailActions(View anchor){
        if(detail==null)return;
        final JSONObject work=detail;final long workId=work.optLong("id"),fileId=work.optLong("resume_file_id");
        LinearLayout actions=MediaStyle.actionColumn(this);actions.setPadding(dp(16),dp(8),dp(16),dp(12));
        ScrollView scroll=new ScrollView(this);scroll.addView(actions);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("当前影片操作").setView(scroll).setNegativeButton("关闭",null).create();
        actions.addView(text("播放",16,MUTED));
        Button restart=button("从头播放",()->{dialog.dismiss();restartCurrent(workId,fileId);});restart.setEnabled(fileId>0);actions.addView(restart);
        Button remote=button("在电脑上播放",()->{dialog.dismiss();Intent intent=new Intent(this,RemoteActivity.class);intent.putExtra("work_id",workId);intent.putExtra("file_id",fileId);startActivity(intent);});remote.setEnabled(fileId>0);actions.addView(remote);
        actions.addView(button("加入手机播放队列",()->{addToPhoneQueue(workId);dialog.dismiss();}));
        actions.addView(text("观看记录",16,MUTED));actions.addView(button("修改观看状态",()->{dialog.dismiss();watchAction(workId,null);}));
        actions.addView(text("电脑端任务",16,MUTED));actions.addView(button("此影片的电脑任务",()->{dialog.dismiss();TaskCenter.show(this,api,workId);}));dialog.show();MediaStyle.sheet(dialog);
    }
    private void resetBrowseFilters(){
        kind="";query="";tagFilter="";actorFilter="";yearMinFilter="";yearMaxFilter="";ratingMinFilter="";tagsAllFilter="";tagsAnyFilter="";tagsNotFilter="";watchFilter="";savedList="";
        favorites=false;watchlistOnly=false;dislikedOnly=false;recommended=false;discovery=false;actresses=false;navigationHistory.clear();clearDiscoverySearch();
    }
    void navigatePrimary(String page){
        utilityPage="";resetBrowseFilters();mainPage=page;
        if(page.equals("mine")){showMine();return;}
        discovery=page.equals("discover");showLibrary();
    }
    private void bottomNavigation(){
        String active=mineLanding||!utilityPage.isEmpty()?"mine":discovery?"discover":favorites||watchlistOnly||!savedList.isEmpty()?"mine":!kind.isEmpty()||actresses?"library":mainPage;
        root.addView(NativeBottomNavigation.create(this,active,this::navigatePrimary),new LinearLayout.LayoutParams(-1,-2));
    }
    private void returnUtility(){
        if(utilityPage.equals("connection")&&connectionReturn!=null){api=connectionReturn;connectionReturn=null;}utilityPage="";if(api!=null)showMine();else finish();
    }
    private LinearLayout utility(String id,String title){
        generation++;utilityPage=id;mineLanding=false;mainPage="mine";detailId=0;renderedDetailId=0;browseRoot=null;continuePanel=null;detailScroll=null;browseLoading=null;base();header(title,true);
        ScrollView scroll=new ScrollView(this);LinearLayout page=BiliMainUi.vertical(this);page.setPadding(dp(16),dp(4),dp(16),dp(24));scroll.addView(page);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));browseScroll=scroll;bottomNavigation();return page;
    }
    private void showMine(){
        generation++;utilityPage="";mineLanding=true;mainPage="mine";detailId=0;renderedDetailId=0;browseRoot=null;continuePanel=null;detailScroll=null;browseLoading=null;base();header("我的",false);
        ScrollView scroll=new ScrollView(this);LinearLayout page=BiliMainUi.vertical(this);page.setTag("mineActions");page.setPadding(dp(16),0,dp(16),dp(24));scroll.addView(page);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));browseScroll=scroll;
        View profile=BiliMainUi.profile(this);page.addView(profile);String[] keys={"all","favorite","watchlist"};String[] paths={"/api/works?offset=0&limit=1","/api/works?offset=0&limit=1&favorite=true","/api/works?offset=0&limit=1&watchlist=true"};
        for(int i=0;i<keys.length;i++){final String key=keys[i],path=paths[i];TextView total=profile.findViewWithTag("mineTotal:"+key);request(()->api.get(path),reply->{total.setText(reply.has("total")?Integer.toString(reply.optInt("total")):"—");},error->{total.setText("—");total.setContentDescription("暂未取得数量，点击重新读取");total.setOnClickListener(v->showMine());});}
        page.addView(BiliMainUi.section(this,"我的影片"));
        Button favorite=button("收藏",()->openCollection(false)),wanted=button("想看",()->openCollection(true)),lists=button("智能片单",this::smartLists),stats=button("观影统计",this::showStats);
        Button[] shortcuts={favorite,wanted,lists,stats};String[] icons={"heart","bookmark","smart_playlist","statistics"};for(int i=0;i<shortcuts.length;i++)BiliMainUi.lightAction(shortcuts[i],icons[i],false);page.addView(BiliMainUi.quickGrid(this,shortcuts));
        LinearLayout devicesHeader=MediaStyle.row(this);devicesHeader.addView(BiliMainUi.section(this,"播放与设备"),new LinearLayout.LayoutParams(0,-2,1));devicesHeader.addView(globalShuffleButton());page.addView(devicesHeader);
        LinearLayout devices=BiliMainUi.group(this);devices.addView(BiliMainUi.settingsRow(this,"手机播放队列","phone_queue",this::queueEditor));devices.addView(BiliMainUi.settingsRow(this,"电脑遥控","remote",()->startActivity(new Intent(this,RemoteActivity.class))));devices.addView(BiliMainUi.settingsRow(this,"电脑任务中心","tasks",this::showTasks));page.addView(BiliMainUi.groupCard(this,devices));
        page.addView(BiliMainUi.section(this,"应用设置"));LinearLayout settings=BiliMainUi.group(this);settings.addView(BiliMainUi.settingsRow(this,"连接管理","server",this::showConnection));settings.addView(BiliMainUi.settingsRow(this,"检查客户端更新","check",()->startActivity(new Intent(this,UpdateActivity.class))));page.addView(BiliMainUi.groupCard(this,settings));bottomNavigation();
    }
    private String mineIcon(String label){
        switch(label){
            case "收藏":return "heart";
            case "想看":return "bookmark";
            case "智能片单":return "smart_playlist";
            case "观影统计":return "statistics";
            case "手机播放队列":return "phone_queue";
            case "电脑遥控":return "remote";
            case "电脑任务中心":return "tasks";
            case "连接管理":return "server";
            default:return "check";
        }
    }
    private void openCollection(boolean watchlist){resetBrowseFilters();mainPage="mine";watchlistOnly=watchlist;favorites=!watchlist;showLibrary();}
    private void browseCategories(){
        String[] labels={"全部","电影","剧集","VR","Fans","其他","女演员"},types={"","movie","series","vr","fans","other","actresses"};
        int selected=actresses?6:Math.max(0,java.util.Arrays.asList(types).indexOf(kind));
        View tabs=BiliMainUi.tabs(this,labels,selected,index->{String current=actresses?"actresses":kind;if(types[index].equals(current))return;resetBrowseFilters();mainPage="library";actresses=index==6;kind=actresses?"":types[index];showLibrary();});tabs.setTag("libraryCategory");tabs.setContentDescription("媒体分类，包含Fans与女演员");root.addView(tabs,new LinearLayout.LayoutParams(-1,-2));
    }
    private void showListActions(View anchor){
        PopupMenu menu=new PopupMenu(this,anchor);if(savedList.isEmpty())menu.getMenu().add("保存当前筛选为片单");menu.getMenu().add("随机播放当前列表");menu.getMenu().add("手机播放队列");
        menu.setOnMenuItemClickListener(item->{switch(item.getTitle().toString()){case "保存当前筛选为片单":saveSmartList();break;case "随机播放当前列表":shuffle();break;default:queueEditor();}return true;});menu.show();
    }
    void showLibrary() {
        if(discovery){showDiscoveryPage();return;}
        generation++;catalogCount=null;mineLanding=false;browseRoot=null;continuePanel=null;detailId=0;renderedDetailId=0;detailScroll=null;browseLoading=null;offset=0;restoreOffset=0;restoreScroll=0;browsePositions.clear();browseRecords.clear();base();utilityPage="";if(!mainPage.equals("home"))header(actresses?"女演员":!actorFilter.isEmpty()?"演员作品":favorites?"收藏":watchlistOnly?"想看":!savedList.isEmpty()?savedList:"媒体库",false);
        boolean home=mainPage.equals("home")&&kind.isEmpty()&&!favorites&&!watchlistOnly&&!dislikedOnly&&!recommended&&!discovery&&!actresses&&query.isEmpty()&&tagFilter.isEmpty()&&actorFilter.isEmpty()&&yearMinFilter.isEmpty()&&yearMaxFilter.isEmpty()&&ratingMinFilter.isEmpty()&&tagsAllFilter.isEmpty()&&tagsAnyFilter.isEmpty()&&tagsNotFilter.isEmpty()&&watchFilter.isEmpty()&&savedList.isEmpty();
        LinearLayout searchRow=MediaStyle.row(this);searchRow.setGravity(Gravity.CENTER_VERTICAL);searchRow.setPadding(dp(16),0,dp(16),dp(8));if(mainPage.equals("home")){TextView brand=text("Lumen",22,BLUE);brand.setTypeface(android.graphics.Typeface.DEFAULT,android.graphics.Typeface.BOLD);searchRow.addView(brand);}
        EditText search=new EditText(this);search.setTextColor(Color.WHITE);search.setHintTextColor(MUTED);search.setHint(discovery?"按影片名称搜索":actresses?"搜索女演员":"搜索媒体库");search.setContentDescription(discovery?"发现影片名称搜索":actresses?"女演员搜索":"媒体库搜索");search.setSingleLine(true);search.setText(query);search.setImeOptions(EditorInfo.IME_ACTION_SEARCH);
        Runnable applySearch=()->{if(discovery&&discoveryOnline){startDiscoverySearch(search);return;}query=search.getText().toString().trim();showLibrary();};
        search.setOnEditorActionListener((view,action,event)->{if(action==EditorInfo.IME_ACTION_SEARCH){applySearch.run();return true;}return false;});
        search.setBackground(MediaStyle.surface(this,0xff15212c,0xff2c414f,8));search.setPadding(dp(12),0,dp(8),0);
        android.graphics.drawable.Drawable glass=getDrawable(R.drawable.design_system_search).mutate();glass.setTint(MUTED);glass.setBounds(0,0,dp(18),dp(18));search.setCompoundDrawables(glass,null,null,null);search.setCompoundDrawablePadding(dp(8));search.setContentDescription(actresses?"女演员搜索":"媒体库搜索");searchRow.addView(search,new LinearLayout.LayoutParams(0,dp(48),1));
        String activeTag=discovery&&discoveryOnline?discoveryResultTag:tagFilter;
        int count=(watchFilter.isEmpty()?0:1)+(savedList.isEmpty()?0:1)+(activeTag.isEmpty()?0:1)+(actorFilter.isEmpty()?0:1)+(yearMinFilter.isEmpty()?0:1)+(yearMaxFilter.isEmpty()?0:1)+(ratingMinFilter.isEmpty()?0:1)+(tagsAllFilter.isEmpty()?0:1)+(tagsAnyFilter.isEmpty()?0:1)+(tagsNotFilter.isEmpty()?0:1)+(favorites?1:0)+(watchlistOnly?1:0)+(dislikedOnly?1:0);
        Button filters=button("筛选"+(count>0?" · "+count:""),this::showFilters);filters.setContentDescription("筛选媒体库");MediaStyle.quiet(filters,"filter","筛选媒体库"+(count>0?"，已选 "+count+" 项":""));searchRow.addView(filters,new LinearLayout.LayoutParams(dp(48),dp(48)));root.addView(searchRow);
        if(mainPage.equals("home")){LinearLayout feed=MediaStyle.row(this);feed.setPadding(dp(16),0,dp(16),0);feed.addView(BiliMainUi.tabs(this,new String[]{"推荐","最近"},recommended?0:1,index->{boolean next=index==0;if(next==recommended)return;resetBrowseFilters();mainPage="home";recommended=next;showLibrary();}),new LinearLayout.LayoutParams(0,-2,1));feed.addView(globalShuffleButton());root.addView(feed);}
        if(!mainPage.equals("home")&&!discovery&&!favorites&&!watchlistOnly&&savedList.isEmpty()&&actorFilter.isEmpty())browseCategories();
        ScrollView scroll=new ScrollView(this);browseScroll=scroll;scroll.setOnScrollChangeListener((View.OnScrollChangeListener)(v,x,y,oldX,oldY)->imageRequests.prioritizeVisible());content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);content.setPadding(dp(16),dp(8),dp(16),dp(16));scroll.addView(content);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        ChipLayout selectedFilters=MediaStyle.actionFlow(this);selectedFilters.setTag("activeFilters");selectedFilters.setPadding(0,dp(4),0,dp(8));
        if(!activeTag.isEmpty())selectedFilters.addView(filterChip(activeTag,()->{if(discovery&&discoveryOnline)discoveryResultTag="";else tagFilter="";showLibrary();}));
        if(!actorFilter.isEmpty())selectedFilters.addView(filterChip(actorFilter,()->{actorFilter="";showLibrary();}));
        if(!yearMinFilter.isEmpty()||!yearMaxFilter.isEmpty())selectedFilters.addView(filterChip("年份 "+yearMinFilter+"–"+yearMaxFilter,()->{yearMinFilter="";yearMaxFilter="";showLibrary();}));
        if(!ratingMinFilter.isEmpty())selectedFilters.addView(filterChip("评分 ≥ "+ratingMinFilter,()->{ratingMinFilter="";showLibrary();}));
        if(!tagsAllFilter.isEmpty())selectedFilters.addView(filterChip("标签:"+tagsAllFilter,()->{tagsAllFilter="";showLibrary();}));
        if(!tagsAnyFilter.isEmpty())selectedFilters.addView(filterChip("任一："+tagsAnyFilter,()->{tagsAnyFilter="";showLibrary();}));
        if(!tagsNotFilter.isEmpty())selectedFilters.addView(filterChip("排除："+tagsNotFilter,()->{tagsNotFilter="";showLibrary();}));
        if(!watchFilter.isEmpty())selectedFilters.addView(filterChip(watchFilter.equals("completed")?"已完成":watchFilter.equals("progress")?"观看中":"未开始",()->{watchFilter="";showLibrary();}));
        if(!savedList.isEmpty())selectedFilters.addView(filterChip("片单："+savedList,()->{savedList="";showLibrary();}));
        if(favorites)selectedFilters.addView(filterChip("已收藏",()->{favorites=false;showLibrary();}));
        if(watchlistOnly)selectedFilters.addView(filterChip("想看",()->{watchlistOnly=false;showLibrary();}));
        if(dislikedOnly)selectedFilters.addView(filterChip("不喜欢",()->{dislikedOnly=false;showLibrary();}));
        if(count>0)content.addView(selectedFilters);
        if(mainPage.equals("home")&&query.isEmpty()&&kind.isEmpty()){continuePanel=new LinearLayout(this);continuePanel.setOrientation(LinearLayout.VERTICAL);content.addView(continuePanel);loadContinue();}
        if(!actorFilter.isEmpty()){LinearLayout actorHeader=MediaStyle.row(this);actorHeader.setTag("actorIdentity");ImageView face=BiliMainUi.avatar(this,72);loadImage(face,actorFilter.equals(actorPhotoName)?actorPhoto:"");actorHeader.addView(face,new LinearLayout.LayoutParams(dp(72),dp(72)));LinearLayout identity=BiliMainUi.vertical(this);identity.addView(text(actorFilter,24,MediaStyle.TEXT));identity.addView(text("本地演员作品",13,MUTED));actorHeader.addView(identity,new LinearLayout.LayoutParams(0,-2,1));content.addView(actorHeader);}
        LinearLayout listHeading=MediaStyle.actionRow(this);listHeading.setGravity(Gravity.CENTER_VERTICAL);listHeading.setPadding(0,dp(16),0,dp(8));listHeading.setTag("listHeading");
        String title=recommended?"为我推荐":discovery?"影片发现":actresses?"女演员墙":favorites?"收藏":watchlistOnly?"想看":!savedList.isEmpty()?savedList:query.isEmpty()?(home?"最近入库":"媒体库"):"搜索结果";
        catalogCount=text(mainPage.equals("home")?title:actresses?"本地演员":"正在读取数量…",mainPage.equals("home")?19:14,MediaStyle.TEXT);catalogCount.setTag("catalogCount");listHeading.addView(catalogCount,new LinearLayout.LayoutParams(0,-2,1));
        if(!actresses){Button sort=button("排序 ↓",this::sorting);BiliMainUi.lightAction(sort,"sort",false);listHeading.addView(sort);Button listMore=button("",()->{});listMore.setContentDescription("当前列表操作");MediaStyle.quiet(listMore,"more","当前列表操作");listMore.setOnClickListener(this::showListActions);listHeading.addView(listMore,new LinearLayout.LayoutParams(dp(48),dp(48)));}content.addView(listHeading);
        posters=new PosterGrid(this);if(actresses){peopleGrid=BiliMainUi.actorGrid(this);content.addView(peopleGrid);}else content.addView(posters);bottomNavigation();
        if(actresses){loadActresses();return;}
        if(discovery&&discoveryOnline&&discoveryResultIds==null){content.addView(text(discoverySearchState.equals("running")||discoverySearchState.equals("queued")?"正在搜索站点，完成后显示本次结果。":"输入影片名称或标签，点击“搜索站点”。",15,MUTED));}else loadPage();
        if(discovery&&discoveryOnline&&!discoverySearchTask.isEmpty()&&(discoverySearchState.equals("running")||discoverySearchState.equals("queued")))pollDiscoverySearch(discoverySearchTask,generation);
    }
    private void discoveryEdgeToEdge(){
        androidx.activity.SystemBarStyle dark=androidx.activity.SystemBarStyle.dark(Color.TRANSPARENT);
        androidx.activity.EdgeToEdge.enable(this,dark,dark);
    }
    /** Only this destination is Compose; existing native pages keep their layout. */
    void showDiscoveryPage(){
        generation++;catalogCount=null;mineLanding=false;browseRoot=null;continuePanel=null;detailId=0;renderedDetailId=0;detailScroll=null;browseLoading=null;
        offset=0;restoreOffset=0;restoreScroll=0;browsePositions.clear();browseRecords.clear();browseScroll=null;content=null;
        if(!discoveryRestoreScroll){discoveryGridIndex=0;discoveryGridScroll=0;}base();
        root.setFitsSystemWindows(false);discoveryEdgeToEdge();
        discoveryCoordinator=new DiscoveryCoordinator(this);root.addView(discoveryCoordinator.getView(),new LinearLayout.LayoutParams(-1,-1));discoveryCoordinator.start();discoveryRestoreScroll=false;
        if(discoveryOnline&&!discoverySearchTask.isEmpty()&&discoverySearchBusy())pollDiscoverySearch(discoverySearchTask,generation);
    }
    DiscoveryFilters discoveryFilterState(){
        DiscoveryFilters initial=new DiscoveryFilters();initial.tag=discoveryOnline?discoveryResultTag:tagFilter;initial.searchTag=tagFilter;initial.hasResults=discoveryOnline&&discoveryResultIds!=null;initial.actor=actorFilter;initial.yearMin=yearMinFilter;initial.yearMax=yearMaxFilter;initial.ratingMin=ratingMinFilter;initial.tagsAll=tagsAllFilter;initial.tagsAny=tagsAnyFilter;initial.tagsNot=tagsNotFilter;initial.watch=watchFilter;initial.favorite=favorites;initial.wanted=watchlistOnly;initial.disliked=dislikedOnly;initial.online=discoveryOnline;initial.provider=discoveryProvider;return initial;
    }
    void applyDiscoveryFilters(DiscoveryFilters next,String queryText){

            boolean queryChanged=!queryText.trim().equals(query);boolean modeChanged=next.online!=discoveryOnline;boolean providerChanged=!next.provider.equals(discoveryProvider);boolean sourceTagChanged=!next.searchTag.equals(tagFilter);if(discoveryOnline&&next.online&&discoverySearchBusy()&&(queryChanged||providerChanged||sourceTagChanged)){message(getString(R.string.discovery_controller_busy_source_edit));return;}query=queryText.trim();if(modeChanged){if(!next.online)clearDiscoverySearch();else {discoveryOnline=true;discoveryResultIds=null;discoveryResultTag="";}}
            discoveryOnline=next.online;discoveryProvider=next.provider;if(discoveryOnline){tagFilter=next.searchTag;discoveryResultTag=next.tag;if(queryChanged||modeChanged||providerChanged||sourceTagChanged||discoveryResultIds==null)discoveryNextSearchFilters=next.copy();}else{tagFilter=next.tag;discoveryNextSearchFilters=null;}
            actorFilter=next.actor;yearMinFilter=next.yearMin;yearMaxFilter=next.yearMax;ratingMinFilter=next.ratingMin;tagsAllFilter=next.tagsAll;tagsAnyFilter=next.tagsAny;tagsNotFilter=next.tagsNot;watchFilter=next.watch;favorites=next.favorite;watchlistOnly=next.wanted;dislikedOnly=next.disliked;
            showLibrary();if(discoveryOnline&&(queryChanged||modeChanged||providerChanged||sourceTagChanged)&&(!query.isEmpty()||!tagFilter.isEmpty()))discoveryCoordinator.startSearchWhenReady();
    }
    private String continueTime(double seconds){long n=(long)Math.max(0,seconds);return String.format(java.util.Locale.ROOT,"%d:%02d:%02d",n/3600,n/60%60,n%60);}
    private void loadContinue() {
        final LinearLayout panel=continuePanel;if(panel==null)return;
        request(()->api.get("/api/continue?limit=24"),result->{
            if(panel!=continuePanel)return;panel.removeAllViews();JSONArray items=result.optJSONArray("items");if(items==null||items.length()==0){panel.setVisibility(View.GONE);return;}panel.setVisibility(View.VISIBLE);
            panel.addView(BiliMainUi.section(this,"继续观看"));HorizontalScrollView scroll=BiliMainUi.resumeStrip(this);LinearLayout row=MediaStyle.row(this);scroll.addView(row);panel.addView(scroll);
            for(int i=0;i<items.length();i++){
                JSONObject work=items.getJSONObject(i),resume=work.optJSONObject("resume");if(resume==null)continue;long workId=work.optLong("id"),fileId=resume.optLong("file_id");
                LinearLayout card=MediaStyle.row(this);card.setGravity(Gravity.CENTER_VERTICAL);card.setPadding(dp(8),dp(8),dp(12),dp(8));card.setTag("continueCard:"+fileId);
                int cardWidth=dp(Math.min(384,Math.max(260,getResources().getConfiguration().screenWidthDp-32)));View surface=BiliMainUi.groupCard(this,card);row.addView(surface,new LinearLayout.LayoutParams(cardWidth,-2));
                FrameLayout artwork=new FrameLayout(this);artwork.setTag("continueArtwork:"+fileId);ImageView cover=new ImageView(this);MediaStyle.artwork(cover);artwork.setClipToOutline(true);artwork.setBackground(MediaStyle.surface(this,MediaStyle.BG,0,8));artwork.addView(cover,new FrameLayout.LayoutParams(-1,-1));card.addView(artwork,new LinearLayout.LayoutParams(dp(132),dp(92)));
                String thumbnail=resume.optString("thumbnail","");cover.setContentDescription("视频缩略图："+work.optString("title"));loadImage(cover,thumbnail);if(thumbnail.isEmpty()){TextView missing=text("暂无视频缩略图",11,MUTED);missing.setGravity(Gravity.CENTER);missing.setTag("continueThumbnailMissing:"+fileId);artwork.addView(missing,new FrameLayout.LayoutParams(-1,-1));}
                LinearLayout body=BiliMainUi.vertical(this);card.addView(body,new LinearLayout.LayoutParams(0,-2,1));TextView title=text(work.optString("title"),15,MediaStyle.TEXT);title.setMaxLines(2);title.setEllipsize(android.text.TextUtils.TruncateAt.END);LinearLayout titleRow=MediaStyle.row(this);titleRow.addView(title,new LinearLayout.LayoutParams(0,-2,1));body.addView(titleRow);
                String filename=resume.optString("name",resume.optString("file_name",resume.optString("label")));TextView description=text(filename,11,MUTED);description.setTag("continueIdentity:"+fileId);description.setMaxLines(1);description.setEllipsize(android.text.TextUtils.TruncateAt.END);description.setOnClickListener(v->showDialog(new AlertDialog.Builder(this).setTitle(work.optString("title")).setMessage(resume.optString("label",filename)).setPositiveButton("关闭",null)));body.addView(description);
                double duration=resume.optDouble("duration",0),position=resume.optDouble("position",0);TextView times=text("已看 "+continueTime(position)+(duration>0?" / "+continueTime(duration)+"\n剩余 "+continueTime(Math.max(0,duration-position)):" · 时长未知"),11,MUTED);times.setTag("continueTime:"+fileId);body.addView(times);
                if(duration>0){ProgressBar progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);progress.setProgressTintList(android.content.res.ColorStateList.valueOf(BLUE));progress.setMax(1000);progress.setProgress((int)Math.max(0,Math.min(1000,position/duration*1000)));progress.setContentDescription("观看进度");body.addView(progress,new LinearLayout.LayoutParams(-1,dp(3)));}
                PlaybackIconButton play=new PlaybackIconButton(this,"play",position>0?"继续播放":"播放下一集");play.setTag("continuePlay:"+fileId);play.setOnClickListener(view->{Intent intent=new Intent(this,PlayerActivity.class);intent.putExtra("work_id",workId);intent.putExtra("file_id",fileId);intent.putExtra("queue",false);startActivity(intent);});play.setContentDescription("续播："+work.optString("title")+" · "+resume.optString("label"));
                // Keep the hit target independent from the thumbnail so no part of its subject is covered.
                titleRow.addView(play,new LinearLayout.LayoutParams(dp(48),dp(48)));cover.setOnClickListener(view->openDetail(workId));title.setOnClickListener(view->openDetail(workId));
            }
        },error->{if(panel!=continuePanel)return;panel.removeAllViews();panel.setVisibility(View.VISIBLE);panel.addView(button("续播读取失败，点击重试",this::loadContinue));});
    }
    String listPath() {
        String path=recommended?"/api/recommendations?":discovery?"/api/discover?":"/api/works?";
        boolean onlineResult=discovery&&discoveryOnline;
        String ids="";if(onlineResult){java.util.ArrayList<String> selected=new java.util.ArrayList<>();if(discoveryResultIds!=null)for(int i=0;i<discoveryResultIds.length();i++)selected.add(Long.toString(discoveryResultIds.optLong(i)));ids="&ids="+android.text.TextUtils.join(",",selected);}
        return path+"offset="+offset+"&limit=30&kind="+kind+"&favorite="+favorites+"&watchlist="+watchlistOnly+(dislikedOnly?"&disliked=true":"")+"&q="+android.net.Uri.encode(onlineResult?"":query)+(discovery?"&tag_q=":"&tag=")+android.net.Uri.encode(onlineResult?discoveryResultTag:tagFilter)+"&actor="+android.net.Uri.encode(actorFilter)+"&year_min="+android.net.Uri.encode(yearMinFilter)+"&year_max="+android.net.Uri.encode(yearMaxFilter)+"&rating_min="+android.net.Uri.encode(ratingMinFilter)+"&tags_all="+android.net.Uri.encode(tagsAllFilter)+"&tags_any="+android.net.Uri.encode(tagsAnyFilter)+"&tags_not="+android.net.Uri.encode(tagsNotFilter)+"&sort="+(discovery?discoverySort:sortField)+"&direction="+((discovery?discoveryDescending:sortDescending)?"desc":"asc")+"&watch_state="+watchFilter+"&list="+android.net.Uri.encode(savedList)+ids;
    }
    void saveDiscoverySort(){getSharedPreferences("discovery",0).edit().putString("sort",discoverySort).putBoolean("descending",discoveryDescending).apply();}
    void clearDiscoverySearch(){
        discoveryNextSearchFilters=null;discoverySubmission++;discoveryOnline=false;discoverySearchTask="";discoverySearchState="";discoverySearchMessage="";discoverySearchErrors="";discoveryResultIds=null;discoveryResultTag="";
    }
    boolean discoverySearchBusy(){return discoverySearchState.equals("queued")||discoverySearchState.equals("running");}
    void startDiscoverySearch(EditText search){
        if(discoverySearchBusy())return;
        if(search!=null)query=search.getText().toString().trim();
        if(query.isEmpty()&&tagFilter.isEmpty()){message(getString(R.string.discovery_controller_enter_query));return;}
        if(!discoveryProvidersLoaded||discoveryProviders.length()==0){message(getString(R.string.discovery_controller_choose_provider));return;}
        if(!tagFilter.isEmpty()&&!discoveryProvider.isEmpty())for(int i=0;i<discoveryProviders.length();i++){
            JSONObject provider=discoveryProviders.optJSONObject(i);
            if(provider!=null&&provider.optString("id").equals(discoveryProvider)&&!provider.optBoolean("supports_tags")){
                discoverySearchTask="";discoverySearchState="failed";discoveryResultIds=null;discoverySearchMessage=getString(R.string.discovery_controller_source_unsupported_tag);discoverySearchErrors="";showLibrary();return;
            }
        }
        // A new site search uses only its explicit name/tag/provider inputs;
        // old local-library conditions must not silently discard site matches.
        kind="";actorFilter="";yearMinFilter="";yearMaxFilter="";ratingMinFilter="";tagsAllFilter="";tagsAnyFilter="";tagsNotFilter="";favorites=false;watchlistOnly=false;dislikedOnly=false;watchFilter="";savedList="";discoveryResultTag="";
        // Only an explicitly applied sheet draft carries result conditions into a
        // new site task. Conditions left behind by other pages never do.
        if(discoveryNextSearchFilters!=null){DiscoveryFilters selected=discoveryNextSearchFilters;discoveryResultTag=selected.tag;actorFilter=selected.actor;yearMinFilter=selected.yearMin;yearMaxFilter=selected.yearMax;ratingMinFilter=selected.ratingMin;tagsAllFilter=selected.tagsAll;tagsAnyFilter=selected.tagsAny;tagsNotFilter=selected.tagsNot;watchFilter=selected.watch;favorites=selected.favorite;watchlistOnly=selected.wanted;dislikedOnly=selected.disliked;discoveryNextSearchFilters=null;}
        final JSONObject payload=new JSONObject();
        try{payload.put("query",query).put("tag",tagFilter).put("plugin",discoveryProvider);}catch(Exception error){message(error.getMessage());return;}
        savedList="";discoveryResultIds=null;discoverySearchTask="";discoverySearchState="queued";discoverySearchMessage=getString(R.string.discovery_controller_submitting);discoverySearchErrors="";showLibrary();
        final int submission=++discoverySubmission;final Api client=api;
        network.execute(()->{
            try{
                String task=client.post("/api/discovery/search",payload).getString("task_id");
                runOnUiThread(()->{if(isDestroyed()||submission!=discoverySubmission||api!=client)return;
                    discoverySearchTask=task;discoverySearchState="queued";discoverySearchMessage=getString(R.string.discovery_controller_queued);
                    if(discovery&&discoveryOnline&&detailId==0)showLibrary();
                });
            }catch(Exception error){runOnUiThread(()->{if(isDestroyed()||submission!=discoverySubmission||api!=client)return;
                discoverySearchState="failed";discoverySearchMessage=getString(R.string.discovery_controller_submit_failed);discoverySearchErrors=error.getMessage()==null?error.toString():error.getMessage();
                if(discovery&&discoveryOnline&&detailId==0)showLibrary();
            });}
        });
    }
    private void pollDiscoverySearch(String task,int ticket){
        if(isDestroyed()||ticket!=generation||!discovery||!discoveryOnline||!task.equals(discoverySearchTask))return;
        request(()->api.get("/api/discovery/search/"+task),state->{
            String phase=state.optString("status");JSONObject result=state.optJSONObject("result");
            if(phase.equals("done")||phase.equals("failed")||phase.equals("cancelled")){
                discoverySearchState=phase;discoverySearchErrors=discoveryErrors(result);
                if(phase.equals("done")){
                    discoveryResultIds=result==null?new JSONArray():result.optJSONArray("ids");if(discoveryResultIds==null)discoveryResultIds=new JSONArray();
                    discoverySearchMessage=getString(R.string.discovery_controller_search_done,discoveryResultIds.length());
                }else{
                    discoveryResultIds=null;discoverySearchMessage=phase.equals("cancelled")?getString(R.string.discovery_controller_cancelled):getString(R.string.discovery_controller_failed);
                    if(!state.isNull("error")&&!state.optString("error").isEmpty())discoverySearchErrors=state.optString("error")+(discoverySearchErrors.isEmpty()?"":"\n"+discoverySearchErrors);
                }
                showLibrary();return;
            }
            discoverySearchState=phase;discoverySearchMessage=phase.equals("queued")?getString(R.string.discovery_controller_waiting):getString(R.string.discovery_controller_running);
            if(discoveryCoordinator!=null)discoveryCoordinator.publish();
            downloadUpdates.postDelayed(()->pollDiscoverySearch(task,ticket),750);
        },error->{
            discoverySearchState="interrupted";discoverySearchMessage=getString(R.string.discovery_controller_poll_failed);discoverySearchErrors=error;showLibrary();
        });
    }
    private String discoveryErrors(JSONObject result){
        JSONArray errors=result==null?null:result.optJSONArray("errors");java.util.ArrayList<String> messages=new java.util.ArrayList<>();
        if(errors!=null)for(int i=0;i<errors.length();i++){
            JSONObject error=errors.optJSONObject(i);if(error!=null)messages.add(error.optString("name",error.optString("plugin"))+"："+error.optString("message"));
        }
        return android.text.TextUtils.join("\n",messages);
    }
    private Button filterChip(String text,Runnable remove){
        Button chip=button(text,remove);chip.setTextSize(13);chip.setMaxWidth(dp(230));chip.setMaxLines(1);chip.setEllipsize(android.text.TextUtils.TruncateAt.END);
        MediaStyle.button(chip,false,true,false);MediaStyle.icon(chip,"close",false);chip.setContentDescription("移除筛选："+text);return chip;
    }
    private AutoCompleteTextView filterInput(LinearLayout form,String label,String value){
        form.addView(text(label,13,MUTED));
        AutoCompleteTextView input=new SearchDropdown(this);input.setSingleLine(true);input.setTextColor(Color.WHITE);input.setHintTextColor(MUTED);
        input.setHint(label.contains("演员")?"搜索演员":label.startsWith("年份")?"输入年份":label.contains("标签")?"搜索标签":"输入条件");input.setText(value);MediaStyle.field(input);
        LinearLayout row=MediaStyle.row(this);row.addView(input,new LinearLayout.LayoutParams(0,dp(48),1));
        row.addView(button("⌄",()->{input.requestFocus();input.showDropDown();}),new LinearLayout.LayoutParams(dp(48),dp(48)));form.addView(row);
        return input;
    }
    private void showFilters(){
        if(discovery){if(discoveryCoordinator!=null)discoveryCoordinator.onOpenFilters();return;}
        LinearLayout form=new LinearLayout(this);form.setOrientation(LinearLayout.VERTICAL);form.setPadding(dp(16),dp(12),dp(16),dp(12));
        final boolean[] onlyFavorites={favorites},onlyDisliked={dislikedOnly};
        Button collection=button("已收藏",()->{});
        Button disliked=button("不喜欢",()->{});disliked.setTag("filterDisliked");
        MediaStyle.icon(collection,"heart",favorites);MediaStyle.button(collection,false,favorites,true);
        MediaStyle.icon(disliked,"ban",dislikedOnly);MediaStyle.button(disliked,false,dislikedOnly,false);
        collection.setOnClickListener(view->{
            onlyFavorites[0]=!onlyFavorites[0];collection.setText("已收藏");MediaStyle.icon(collection,"heart",onlyFavorites[0]);MediaStyle.button(collection,false,onlyFavorites[0],true);
            if(onlyFavorites[0]){onlyDisliked[0]=false;MediaStyle.icon(disliked,"ban",false);MediaStyle.button(disliked,false,false,false);}
        });
        disliked.setOnClickListener(view->{
            onlyDisliked[0]=!onlyDisliked[0];MediaStyle.icon(disliked,"ban",onlyDisliked[0]);MediaStyle.button(disliked,false,onlyDisliked[0],false);
            if(onlyDisliked[0]){onlyFavorites[0]=false;collection.setText("已收藏");MediaStyle.icon(collection,"heart",false);MediaStyle.button(collection,false,false,true);}
        });
        form.addView(text("我的偏好",14,MediaStyle.TEXT));
        ChipLayout preferences=MediaStyle.actionFlow(this);preferences.setTag("filterPreferences");
        Button wanted=button("想看",()->{});final boolean[] onlyWanted={watchlistOnly};MediaStyle.icon(wanted,"bookmark",onlyWanted[0]);MediaStyle.button(wanted,false,onlyWanted[0],false);
        wanted.setOnClickListener(v->{onlyWanted[0]=!onlyWanted[0];MediaStyle.button(wanted,false,onlyWanted[0],false);MediaStyle.icon(wanted,"bookmark",onlyWanted[0]);});
        for(Button option:new Button[]{collection,wanted,disliked}){option.setTextSize(12);preferences.addView(option);}form.addView(preferences);
        AutoCompleteTextView tag=filterInput(form,"标签",discovery&&discoveryOnline?discoveryResultTag:tagFilter),actor=filterInput(form,"演员",actorFilter),multiTag=filterInput(form,"多个标签（逗号分隔，需全部包含）",tagsAllFilter);
        AutoCompleteTextView anyTags=filterInput(form,"包含任一标签",tagsAnyFilter),notTags=filterInput(form,"排除标签／不想看的类型",tagsNotFilter);
        AutoCompleteTextView yearFrom=filterInput(form,"年份从",yearMinFilter),yearTo=filterInput(form,"年份到",yearMaxFilter);
        yearFrom.setTag("filterYearFrom");yearTo.setTag("filterYearTo");
        yearFrom.setInputType(InputType.TYPE_CLASS_NUMBER);yearTo.setInputType(InputType.TYPE_CLASS_NUMBER);
        ChipLayout tagSuggestions=new ChipLayout(this);tagSuggestions.setTag("filterTagSuggestions");int tagIndex=form.indexOfChild((View)tag.getParent());form.addView(tagSuggestions,tagIndex+1);
        AutoCompleteTextView rating=filterInput(form,"最低评分（0–10）",ratingMinFilter);rating.setInputType(InputType.TYPE_CLASS_NUMBER);
        String[] states={"","unwatched","progress","completed"};final int[] watching={Math.max(0,java.util.Arrays.asList(states).indexOf(watchFilter))};
        ChipLayout watchRow=MediaStyle.actionFlow(this);watchRow.setTag("watchSegments");
        String[] watchLabels={"全部","未看","观看中","已看完"};
        Runnable refreshWatch=()->{for(int i=0;i<watchRow.getChildCount();i++){Button option=(Button)watchRow.getChildAt(i);MediaStyle.button(option,watching[0]==i,watching[0]==i,false);option.setTextSize(12);}};
        for(int i=0;i<watchLabels.length;i++){final int index=i;Button option=button(watchLabels[i],()->{watching[0]=index;refreshWatch.run();});watchRow.addView(option);}refreshWatch.run();form.addView(watchRow,0);form.addView(text("观看状态",14,MediaStyle.TEXT),0);
        LinearLayout yearPair=MediaStyle.row(this);yearPair.setOrientation(LinearLayout.HORIZONTAL);yearPair.setPadding(0,0,0,dp(8));
        for(AutoCompleteTextView input:new AutoCompleteTextView[]{yearFrom,yearTo}){View parent=(View)input.getParent();int index=form.indexOfChild(parent);View label=form.getChildAt(index-1);form.removeView(label);form.removeView(parent);((android.view.ViewGroup)parent).removeView(input);LinearLayout cell=new LinearLayout(this);cell.setOrientation(LinearLayout.VERTICAL);cell.addView(label);cell.addView(input,new LinearLayout.LayoutParams(-1,dp(48)));LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,-2,1);yearPair.addView(cell,lp);}form.addView(yearPair);
        LinearLayout advanced=new LinearLayout(this);advanced.setOrientation(LinearLayout.VERTICAL);advanced.setTag("advancedFilterFields");
        for(AutoCompleteTextView input:new AutoCompleteTextView[]{multiTag,anyTags,notTags,rating}){View parent=(View)input.getParent();int index=form.indexOfChild(parent);View label=form.getChildAt(index-1);form.removeView(label);form.removeView(parent);advanced.addView(label);advanced.addView(parent);}
        advanced.setVisibility(tagsAllFilter.isEmpty()&&tagsAnyFilter.isEmpty()&&tagsNotFilter.isEmpty()&&ratingMinFilter.isEmpty()?View.GONE:View.VISIBLE);
        Button moreFilters=button("更多条件 · 标签组合、排除、评分",()->advanced.setVisibility(advanced.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE));form.addView(moreFilters);form.addView(advanced);
        TextView status=text("正在读取筛选选项…",13,MUTED);form.addView(status);
        ScrollView scroll=new ScrollView(this);scroll.addView(form);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("筛选媒体库").setView(scroll)
            .setPositiveButton("应用",null).setNegativeButton("取消",null).setNeutralButton("重置",(d,which)->{tagFilter="";actorFilter="";yearMinFilter="";yearMaxFilter="";ratingMinFilter="";tagsAllFilter="";favorites=false;showLibrary();}).create();
        dialog.show();MediaStyle.sheet(dialog);dialog.setOnDismissListener(d->creatingSmartList=false);
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view->{
            String from=yearFrom.getText().toString().trim(),to=yearTo.getText().toString().trim(),score=rating.getText().toString().trim();
            if(!from.isEmpty()&&(!from.matches("[0-9]{4}")||Integer.parseInt(from)<1800||Integer.parseInt(from)>2200)){yearFrom.setError("请输入 1800–2200 的年份");return;}
            if(!to.isEmpty()&&(!to.matches("[0-9]{4}")||Integer.parseInt(to)<1800||Integer.parseInt(to)>2200)){yearTo.setError("请输入 1800–2200 的年份");return;}
            if(!score.isEmpty()&&(!score.matches("[0-9]{1,2}")||Integer.parseInt(score)>10)){rating.setError("评分范围 0–10");return;}
            if(!from.isEmpty()&&!to.isEmpty()&&Integer.parseInt(from)>Integer.parseInt(to)){yearFrom.setError("起始年份不能晚于结束");return;}
            if(discovery&&discoveryOnline)discoveryResultTag=tag.getText().toString().trim();else tagFilter=tag.getText().toString().trim();
            actorFilter=actor.getText().toString().trim();tagsAllFilter=multiTag.getText().toString().trim();tagsAnyFilter=anyTags.getText().toString().trim();tagsNotFilter=notTags.getText().toString().trim();
            yearMinFilter=from;yearMaxFilter=to;ratingMinFilter=score;favorites=onlyFavorites[0];dislikedOnly=onlyDisliked[0];watchlistOnly=onlyWanted[0];watchFilter=states[watching[0]];boolean createList=creatingSmartList;creatingSmartList=false;dialog.dismiss();showLibrary();if(createList)saveSmartList();
        });
        dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(view->{
            tag.setText("");actor.setText("");multiTag.setText("");anyTags.setText("");notTags.setText("");yearFrom.setText("");yearTo.setText("");rating.setText("");watching[0]=0;refreshWatch.run();onlyWanted[0]=false;MediaStyle.button(wanted,false,false,false);MediaStyle.icon(wanted,"bookmark",false);onlyFavorites[0]=false;onlyDisliked[0]=false;disliked.setText("不喜欢");MediaStyle.icon(disliked,"ban",false);MediaStyle.button(disliked,false,false,false);
            collection.setText("已收藏");MediaStyle.icon(collection,"heart",false);MediaStyle.button(collection,false,false,true);
        });
        MediaStyle.button(dialog.getButton(AlertDialog.BUTTON_POSITIVE),true,false,false);
        MediaStyle.button(dialog.getButton(AlertDialog.BUTTON_NEGATIVE),false,false,false);MediaStyle.button(dialog.getButton(AlertDialog.BUTTON_NEUTRAL),false,false,false);
        request(()->api.get("/api/filters?kind="+android.net.Uri.encode(kind)+"&discover="+discovery),options->{
            if(!dialog.isShowing())return;
            JSONArray suggested=options.optJSONArray("tags");if(suggested!=null)for(int i=0;i<Math.min(6,suggested.length());i++){String value=suggested.optString(i);tagSuggestions.addView(BiliMainUi.suggestionChip(this,value,()->tag.setText(value)));}
            AutoCompleteTextView[] inputs={tag,actor,multiTag,yearFrom,yearTo,anyTags,notTags};String[] keys={"tags","actors","tags","years","years","tags","tags"};
            for(int i=0;i<inputs.length;i++){
                JSONArray values=options.getJSONArray(keys[i]);java.util.ArrayList<String> choices=new java.util.ArrayList<>();
                for(int j=0;j<values.length();j++)choices.add(values.optString(j));
                inputs[i].setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_dropdown_item_1line,choices));
            }
            status.setText("输入搜索或下拉选择，多个条件同时生效。");
        });
    }
    private void loadPage() {
        if(discovery){if(discoveryCoordinator!=null)discoveryCoordinator.loadPage();return;}
        TextView loading=text("正在读取媒体库…",14,MUTED);browseLoading=loading;content.addView(loading);String path=listPath();
        request(()->api.get(path),result->{
            content.removeView(loading);if(browseLoading==loading)browseLoading=null;JSONArray items=result.getJSONArray("items");int total=result.optInt("total");if(catalogCount!=null)catalogCount.setText(mainPage.equals("home")?(recommended?"为我推荐":"最近入库"):"共 "+total+" 部");
            if(total==0)content.addView(text(discovery?(discoveryOnline?"本次站点搜索没有匹配结果，可更换名称、标签或来源重试。":"暂无匹配的发现资料，可调整名称、标签或切换在线搜索站点。"):"暂无内容。请先在电脑端导入媒体，或调整搜索条件。",16,MUTED));
            int columns=Math.max(2,getResources().getConfiguration().screenWidthDp/165);
            int width=(getResources().getDisplayMetrics().widthPixels-dp(32))/columns;
            width=(getResources().getDisplayMetrics().widthPixels-dp(32)-(columns-1)*dp(6))/columns;
            for(int i=0;i<items.length();i++) {
                JSONObject work=items.getJSONObject(i);long id=work.getLong("id");browseRecords.put(id,work);browsePositions.put(id,offset+i);
                LinearLayout card=new LinearLayout(this);card.setTag("card:"+id);card.setOrientation(LinearLayout.VERTICAL);card.setPadding(0,dp(4),0,dp(10));
                FrameLayout cover=new FrameLayout(this);cover.setBackground(MediaStyle.surface(this,0xff172a35,0,12));cover.setClipToOutline(true);
                boolean cinema=work.optString("kind").equals("movie")||work.optString("kind").equals("vr");
                ImageView poster=cinema?new CatalogPoster(work.optString("title")):new ImageView(this);MediaStyle.artwork(poster);if(cinema||(mainPage.equals("home")&&!recommended))poster.setScaleType(ImageView.ScaleType.CENTER_CROP);cover.addView(poster,new FrameLayout.LayoutParams(-1,-1));
                Button favorite=markButton(work,"favorite",true);FrameLayout.LayoutParams badge=new FrameLayout.LayoutParams(dp(48),dp(48),Gravity.TOP|Gravity.RIGHT);badge.setMargins(0,dp(6),dp(6),0);cover.addView(favorite,badge);
                card.addView(cover,new LinearLayout.LayoutParams(-1,(int)((width-dp(6))*1.5)));loadImage(poster,work.optString("cover",""));
                TextView title=text(work.optString("title"),15,Color.WHITE);title.setMaxLines(2);title.setEllipsize(android.text.TextUtils.TruncateAt.END);title.setMinHeight(dp(48));card.addView(title);
                String community=work.isNull("community_rating")?"":"  ★ "+String.format(java.util.Locale.ROOT,"%.1f",work.optDouble("community_rating"));
                TextView meta=text((work.isNull("year")?"":work.optString("year"))+community,12,MUTED);card.addView(meta);
                if(!work.isNull("rating"))card.addView(text("我的评分 "+work.optInt("rating"),12,0xffadb8c8));
                card.setOnClickListener(view->openDetail(id));poster.setOnClickListener(view->openDetail(id));posters.addView(card,new android.view.ViewGroup.LayoutParams(width,-2));
            }
            offset+=items.length();
            if(offset<restoreOffset&&offset<total&&items.length()>0){loadPage();return;}
            if(restoreOffset>0){restoreOffset=0;final int position=restoreScroll;ScrollView target=browseScroll;target.post(()->target.scrollTo(0,position));}
            if(offset<total) {Button more=button("加载更多  ·  "+offset+" / "+total,()->{});more.setOnClickListener(v->{content.removeView(more);loadPage();});content.addView(more);}
        },error->{
            content.removeView(loading);if(browseLoading==loading)browseLoading=null;
            TextView failure=text("读取失败："+error,14,MUTED);content.addView(failure);
            Button retry=button("重试读取媒体库",()->{});
            retry.setOnClickListener(view->{content.removeView(failure);content.removeView(retry);loadPage();});
            content.addView(retry);
        });
    }
    private void loadActresses() {
        TextView loading=text("正在读取女演员墙…",14,MUTED);browseLoading=loading;content.addView(loading);
        String path="/api/actresses?minimum=0&sort=average"+(query.isEmpty()?"":"&q="+android.net.Uri.encode(query));
        request(()->api.get(path),result->{
            content.removeView(loading);if(browseLoading==loading)browseLoading=null;
            JSONArray items=result.getJSONArray("items");
            if(items.length()==0)content.addView(text("还没有女演员资料。影片刮削演员后，这里会按出演数量与评分汇总。",16,MUTED));
            if(catalogCount!=null)catalogCount.setText("本地演员 · 共 "+items.length()+" 位");
            for(int i=0;i<items.length();i++){
                JSONObject actor=items.getJSONObject(i);LinearLayout card=BiliMainUi.vertical(this);card.setGravity(Gravity.CENTER_HORIZONTAL);card.setTag("actor:"+actor.optString("name"));ImageView photo=BiliMainUi.avatar(this,96);card.addView(photo,new LinearLayout.LayoutParams(dp(96),dp(96)));loadImage(photo,actor.optString("photo",""));
                TextView name=text(actor.optString("name"),15,MediaStyle.TEXT);name.setMaxLines(1);name.setEllipsize(android.text.TextUtils.TruncateAt.END);name.setGravity(Gravity.CENTER);card.addView(name,new LinearLayout.LayoutParams(-1,-2));TextView number=text(actor.optInt("count")+" 部作品",12,MUTED);number.setGravity(Gravity.CENTER);card.addView(number,new LinearLayout.LayoutParams(-1,-2));
                String average=actor.isNull("average")?"暂无评分":"均分 "+String.format(java.util.Locale.ROOT,"%.1f",actor.optDouble("average"));TextView rating=text(average+" · 已评分 "+actor.optInt("rated"),10,MUTED);rating.setGravity(Gravity.CENTER);card.addView(rating);
                card.setOnClickListener(view->{actorFilter=actor.optString("name");actorPhoto=actor.optString("photo");actorPhotoName=actor.optString("name");actresses=false;kind="movie";savedList="";query="";navigationHistory.clear();showLibrary();});peopleGrid.addView(card);
            }
        });
    }
    private void loadImage(ImageView view,String path) {
        if(view.getBackground()==null)view.setBackground(new MediaStyle.ArtworkPlaceholder());
        if(api!=null)imageRequests.load(api,view,path);
    }
    /** Movie/VR cards keep poster geometry while the existing image loader reports availability. */
    private final class CatalogPoster extends androidx.appcompat.widget.AppCompatImageView implements ImageRequests.TargetState {
        private final String title;
        CatalogPoster(String title){super(MainActivity.this);this.title=title;onImageLoading();}
        @Override public void onImageLoading(){setImageDrawable(new MediaStyle.ArtworkPlaceholder());setContentDescription(getString(R.string.catalog_poster_loading,title));}
        @Override public void onImageLoaded(){setContentDescription(getString(R.string.catalog_poster_description,title));}
        @Override public void onImageFailed(){setImageDrawable(new MediaStyle.ArtworkPlaceholder());setContentDescription(getString(R.string.catalog_poster_unavailable,title));}
    }
    void openDetail(long id) {
        if(detailId==0){browseRoot=root;if(discoveryCoordinator!=null)discoveryCoordinator.setActive(false);}
        generation++;detailId=id;
        Api client=api;long version=personalReadVersion(client);
        request(()->client.get("/api/works/"+id),work->{mergePersonalRead(client,id,version,work);renderDetail(work);});
    }
    private void renderDetail(JSONObject work) throws Exception {
        int previousScroll=renderedDetailId==work.optLong("id")&&detailScroll!=null?detailScroll.getScrollY():0;
        detail=work;detailId=work.getLong("id");renderedDetailId=detailId;base();header("详情",true);
        ScrollView scroll=new ScrollView(this);LinearLayout page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);page.setPadding(dp(16),0,dp(16),dp(24));scroll.addView(page);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        detailScroll=scroll;scroll.post(()->scroll.scrollTo(0,previousScroll));
        LinearLayout hero=new LinearLayout(this);hero.setGravity(Gravity.TOP);hero.setPadding(0,dp(8),0,dp(16));
        ImageView poster=new ImageView(this);poster.setScaleType(ImageView.ScaleType.FIT_CENTER);poster.setBackground(MediaStyle.surface(this,0xff101b24,0,6));poster.setClipToOutline(true);poster.setContentDescription("海报："+work.optString("title"));
        hero.addView(poster,new LinearLayout.LayoutParams(dp(128),dp(192)));loadImage(poster,work.optString("cover",""));
        String coverPath=work.optString("cover","");
        poster.setContentDescription("放大封面："+work.optString("title"));
        poster.setOnClickListener(view->{if(!coverPath.isEmpty()&&!coverPath.equals("null"))showGallery(new JSONArray().put(coverPath),0);else message("此影片暂无封面");});
        LinearLayout info=new LinearLayout(this);info.setOrientation(LinearLayout.VERTICAL);info.setPadding(dp(16),0,0,0);
        TextView title=text(work.optString("title"),22,MediaStyle.TEXT);title.setMaxLines(4);title.setEllipsize(android.text.TextUtils.TruncateAt.END);title.setContentDescription(work.optString("title"));
        title.setOnClickListener(view->title.setMaxLines(title.getMaxLines()==4?Integer.MAX_VALUE:4));info.addView(title);
        String category=work.optString("kind").equals("series")?"电视剧":work.optString("kind").equals("vr")?"VR 电影":work.optString("kind").equals("fans")?"Fans视频":work.optString("kind").equals("movie")?"电影":"视频";
        info.addView(text((work.isNull("year")?"":work.optString("year")+"  ·  ")+category,14,MUTED));
        info.addView(text(work.optInt("file_count")==0?"未入库":work.optInt("file_count")+" 个视频",13,MUTED));
        if(!work.isNull("community_rating"))info.addView(text("★ "+String.format(java.util.Locale.ROOT,"%.1f",work.optDouble("community_rating"))+"  来源评分",14,0xffe7c567));
        hero.addView(info,new LinearLayout.LayoutParams(0,-2,1));page.addView(hero);
        JSONObject resume=work.optJSONObject("resume");
        Button play=button(resume!=null&&resume.optDouble("position",work.optDouble("position"))>0||work.optDouble("position")>0?"继续播放":"播放",()->startPlayer(work.optLong("resume_file_id"),false));
        play.setTag("detailPlay");MediaStyle.button(play,true,false,false);MediaStyle.icon(play,"play",true);play.setEnabled(work.optInt("file_count")>0);page.addView(play,new LinearLayout.LayoutParams(-1,-2));
        if(resume!=null&&!resume.optString("label").isEmpty()){TextView resumeInfo=text(resume.optString("label"),13,MUTED);resumeInfo.setTag("detailResumeInfo");page.addView(resumeInfo);}
        LinearLayout personal=MediaStyle.actionRow(this);personal.setTag("detailPersonalActions");personal.setPadding(0,dp(8),0,dp(8));
        Button favoriteAction=markButton(work,"favorite",false),watchlistAction=markButton(work,"watchlist",false);personal.addView(favoriteAction,new LinearLayout.LayoutParams(0,-2,1));personal.addView(watchlistAction,new LinearLayout.LayoutParams(0,-2,1));
        Button score=button(work.isNull("rating")?"评分":work.optInt("rating")+" 分",()->{
            String[] scores={"清除评分","1 分","2 分","3 分","4 分","5 分","6 分","7 分","8 分","9 分","10 分"};
            showDialog(new AlertDialog.Builder(this).setTitle("我的评分").setSingleChoiceItems(scores,work.optInt("rating",0),(dialog,index)->{dialog.dismiss();personal("rating",index==0?JSONObject.NULL:index);}).setNegativeButton("取消",null));
        });score.setContentDescription("我的评分");score.setTag("rating:"+work.optLong("id"));detailAction(score,"star",!work.isNull("rating"));personal.addView(score,new LinearLayout.LayoutParams(0,-2,1));page.addView(personal);
        LinearLayout metadataSection=new LinearLayout(this);metadataSection.setOrientation(LinearLayout.VERTICAL);
        JSONArray tags=work.optJSONArray("tags");JSONArray actors=work.optJSONArray("actors");
        ChipLayout metadata=MediaStyle.actionFlow(this);metadata.setPadding(0,0,0,dp(12));
        if(tags!=null)for(int i=0;i<tags.length();i++){
            String tag=tags.optString(i);Button tagAction=button(tag,()->filterMetadata("tag",tag));BiliMainUi.lightAction(tagAction,"",false);metadata.addView(tagAction);
        }
        if(metadata.getChildCount()>0)metadataSection.addView(metadata);
        ChipLayout cast=new ChipLayout(this);cast.setPadding(0,0,0,dp(12));
        if(actors!=null&&actors.length()>0){TextView caption=text("主演",13,MUTED);caption.setMinHeight(dp(48));caption.setGravity(Gravity.CENTER_VERTICAL);cast.addView(caption);}
        if(actors!=null)for(int i=0;i<actors.length();i++){
            String actor=actors.optJSONObject(i)==null?"":actors.optJSONObject(i).optString("name");if(actor.isEmpty())continue;
            JSONObject person=actors.optJSONObject(i);String photo=person.optString("photo","");
            if(!photo.isEmpty()&&!photo.equals("null")){
                LinearLayout personCard=new LinearLayout(this);personCard.setOrientation(LinearLayout.VERTICAL);
                ImageView face=new ImageView(this);face.setScaleType(ImageView.ScaleType.CENTER_CROP);face.setContentDescription("演员头像："+actor);
                personCard.addView(face,new LinearLayout.LayoutParams(dp(104),dp(132)));loadImage(face,photo);
                face.setOnClickListener(view->filterMetadata("actor",actor));
                face.setOnLongClickListener(view->{String credit=person.optString("photo_attribution","")+"\n"+person.optString("photo_license","")+"\n"+person.optString("photo_page",person.optString("photo_source_url",""));showDialog(new AlertDialog.Builder(this).setTitle(actor+" · 头像来源 / 许可").setMessage(credit.trim().isEmpty()?"来源未提供署名资料":credit.trim()).setPositiveButton("关闭",null));return true;});
                Button actorName=button(actor,()->filterMetadata("actor",actor));actorName.setTag("actorName:"+actor);personCard.addView(actorName,new LinearLayout.LayoutParams(dp(104),-2));cast.addView(personCard);
            }else cast.addView(button(actor,()->filterMetadata("actor",actor)));
        }
        if(cast.getChildCount()>0)metadataSection.addView(cast);
        TextView overview=text(work.optString("overview","暂无简介"),15,MUTED);overview.setTag("detailOverview");overview.setMaxLines(4);overview.setEllipsize(android.text.TextUtils.TruncateAt.END);overview.setContentDescription("简介，点击展开或收起");overview.setOnClickListener(v->overview.setMaxLines(overview.getMaxLines()==4?Integer.MAX_VALUE:4));metadataSection.addView(overview);
        JSONArray files=work.getJSONArray("files");page.addView(text(work.optString("kind").equals("series")?"季与集":work.optString("kind").equals("fans")?"作者视频":"视频文件",21,Color.WHITE));
        LinearLayout episodes=MediaStyle.actionColumn(this);episodes.setTag("detailFileActions");
        android.widget.Spinner seasons=new android.widget.Spinner(this);java.util.ArrayList<Integer> seasonValues=new java.util.ArrayList<>();seasonValues.add(-1);
        java.util.TreeSet<Integer> available=new java.util.TreeSet<>();for(int j=0;j<files.length();j++)available.add(files.getJSONObject(j).optInt("season",1));seasonValues.addAll(available);
        java.util.ArrayList<String> seasonNames=new java.util.ArrayList<>();seasonNames.add("全部季");for(int j=1;j<seasonValues.size();j++)seasonNames.add(seasonValues.get(j)==0?"特别篇":"第 "+seasonValues.get(j)+" 季");
        seasons.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,seasonNames));if(work.optString("kind").equals("series"))page.addView(seasons);page.addView(episodes);
        seasons.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener(){public void onNothingSelected(android.widget.AdapterView<?> p){}public void onItemSelected(android.widget.AdapterView<?> p,View v,int pos,long id){int selected=seasonValues.get(pos);for(int j=0;j<episodes.getChildCount();j++){View child=episodes.getChildAt(j);child.setVisibility(selected==-1||Integer.valueOf(selected).equals(child.getTag())?View.VISIBLE:View.GONE);}}});
        for(int i=0;i<files.length();i++) {
            JSONObject file=files.getJSONObject(i);long id=file.getLong("id");String name=file.optString("name");
            if(work.optString("kind").equals("series")&&!file.isNull("season")&&!file.isNull("episode"))name=String.format(java.util.Locale.ROOT,"S%02d E%02d  ·  ",file.optInt("season"),file.optInt("episode"))+name;
            LinearLayout episode=new LinearLayout(this);episode.setOrientation(LinearLayout.VERTICAL);episode.setTag(file.optInt("season",1));episodes.addView(episode);
            Button playEpisode=BiliMainUi.settingsRow(this,name+"  ·  "+(int)(file.optDouble("duration")/60)+" 分钟","play",()->startPlayer(id,false));playEpisode.setOnLongClickListener(v->{watchAction(work.optLong("id"),id);return true;});episode.addView(playEpisode);
            if(!file.optString("overview").isEmpty())episode.addView(text(file.optString("overview"),14,MUTED));
            JSONArray episodeStills=file.optJSONArray("stills");
            if(episodeStills!=null&&episodeStills.length()>0){
                HorizontalScrollView shots=new HorizontalScrollView(this);LinearLayout images=new LinearLayout(this);
                for(int j=0;j<episodeStills.length();j++){
                    ImageView shot=new ImageView(this);shot.setScaleType(ImageView.ScaleType.FIT_CENTER);
                    images.addView(shot,new LinearLayout.LayoutParams(dp(240),dp(150)));loadImage(shot,episodeStills.optString(j));final int shotIndex=j;shot.setOnClickListener(v->showGallery(episodeStills,shotIndex));
                }
                shots.addView(images);episode.addView(shots);
            }
        }
        page.addView(metadataSection);
        JSONArray bookmarks=work.optJSONArray("bookmarks");
        if(bookmarks!=null&&bookmarks.length()>0){
            page.addView(text("时间点书签",21,Color.WHITE));
            LinearLayout bookmarkEntries=MediaStyle.actionColumn(this);bookmarkEntries.setTag("detailBookmarkActions");page.addView(bookmarkEntries);
            for(int i=0;i<bookmarks.length();i++){
                JSONObject mark=bookmarks.optJSONObject(i);if(mark==null)continue;
                LinearLayout entry=new LinearLayout(this);entry.setOrientation(LinearLayout.VERTICAL);bookmarkEntries.addView(entry);
                if(i<12&&!mark.isNull("image")){ImageView preview=new ImageView(this);preview.setScaleType(ImageView.ScaleType.FIT_CENTER);entry.addView(preview,new LinearLayout.LayoutParams(-1,dp(140)));loadImage(preview,mark.optString("image"));}
                entry.addView(button(String.format(java.util.Locale.ROOT,"%d:%02d · %s",mark.optInt("position")/60,mark.optInt("position")%60,mark.optString("title")),()->{
                    Intent intent=playerIntent(mark.optLong("file_id"),false);intent.putExtra("start_position",mark.optDouble("position"));startActivity(intent);
                }));if(!mark.optString("note").isEmpty())entry.addView(text(mark.optString("note"),14,MUTED));
            }
        }
        JSONArray stills=work.optJSONArray("stills");
        if(stills!=null&&stills.length()>0){
            page.addView(text("剧照",21,Color.WHITE));
            HorizontalScrollView gallery=new HorizontalScrollView(this);LinearLayout images=new LinearLayout(this);
            ImageView expanded=new ImageView(this);expanded.setScaleType(ImageView.ScaleType.FIT_CENTER);expanded.setVisibility(View.GONE);
            for(int i=0;i<stills.length();i++){
                String path=stills.optString(i);ImageView image=new ImageView(this);image.setScaleType(ImageView.ScaleType.FIT_CENTER);
                LinearLayout.LayoutParams size=new LinearLayout.LayoutParams(dp(280),dp(180));size.setMargins(0,0,dp(12),0);images.addView(image,size);loadImage(image,path);
                final int imageIndex=i;image.setOnClickListener(v->showGallery(stills,imageIndex));
            }
            gallery.addView(images);page.addView(gallery);page.addView(expanded,new LinearLayout.LayoutParams(-1,dp(300)));
        }
        JSONArray downloads=work.optJSONArray("download_url");
        if(downloads!=null&&downloads.length()>0){
            page.addView(text("下载资源",21,Color.WHITE));
            TextView directory=text("保存到电脑："+work.optString("download_directory","分类默认目录"),13,MUTED);page.addView(directory);
            page.addView(button("更改本片在电脑上的下载目录",()->{
                EditText input=new EditText(this);input.setSingleLine(true);input.setText(work.optString("download_directory"));
                showDialog(new AlertDialog.Builder(this).setTitle("电脑端保存目录").setMessage("填写电脑上的完整路径；留空恢复分类默认目录。").setView(input)
                    .setPositiveButton("保存",(dialog,which)->request(()->api.post("/api/works/"+work.optLong("id")+"/download-directory",new JSONObject().put("directory",input.getText().toString().trim())),result->{
                        work.put("download_directory",result.getString("directory"));directory.setText("保存到电脑："+result.getString("directory"));
                    })).setNegativeButton("取消",null));
            }));
            TextView status=text("HTTP 下载完成后自动加入当前影视资料；磁力由电脑端配置的外部下载器处理。",13,MUTED);page.addView(status);
            LinearLayout downloadActions=MediaStyle.actionColumn(this);downloadActions.setTag("detailDownloadActions");page.addView(downloadActions);
            for(int i=0;i<downloads.length();i++){
                JSONObject entry=downloads.optJSONObject(i);if(entry==null)continue;final int index=i;
                downloadActions.addView(button(entry.optString("description","下载"),()->request(
                    ()->api.post("/api/works/"+work.optLong("id")+"/downloads",new JSONObject().put("index",index)),result->{
                        String task=result.getString("task_id");status.setText("已加入电脑端下载队列…");
                        getSharedPreferences("download-tasks",0).edit().putString(Long.toString(work.optLong("id")),task).apply();
                        pollDownload(task,work.optLong("id"),status,generation);
                    })));
            }
            downloadActions.addView(button("外部下载完成，检查文件并入库",()->request(
                ()->api.post("/api/works/"+work.optLong("id")+"/import-downloads",new JSONObject().put("check",true)),result->{
                    String taskId=result.getString("task_id");
                    getSharedPreferences("download-tasks",0).edit().putString(Long.toString(work.optLong("id")),taskId).apply();
                    pollDownload(taskId,work.optLong("id"),status,generation);
                })));

            String task=getSharedPreferences("download-tasks",0).getString(Long.toString(work.optLong("id")),"");
            if(!task.isEmpty())pollDownload(task,work.optLong("id"),status,generation);
        }
        JSONArray sources=work.optJSONArray("sources");
        if(sources!=null&&sources.length()>0)page.addView(text("信息来源",21,Color.WHITE));
        if(sources!=null)for(int i=0;i<sources.length();i++) {
            JSONObject source=sources.getJSONObject(i);String url=source.optString("url");
            page.addView(button(source.optString("site")+"  ↗",()->{PrivateBrowserActivity.open(this,url);}));
        }
    }
    private void pollDownload(String task,long workId,TextView status,int ticket){
        if(isDestroyed()||generation!=ticket||detailId!=workId)return;
        request(()->api.get("/api/downloads/"+task),state->{
            String phase=state.optString("status");JSONObject payload=state.optJSONObject("payload"),result=state.optJSONObject("result");
            if(phase.equals("done")){
                getSharedPreferences("download-tasks",0).edit().remove(Long.toString(workId)).apply();
                JSONArray errors=result==null?null:result.optJSONArray("errors");
                message(errors!=null&&errors.length()>0?"检查完成，部分文件尚未入库，请确认下载器已完成下载":"下载文件已加入影视库");openDetail(workId);return;
            }
            if(phase.equals("external")){
                String directory=result==null?"":result.optString("directory");
                status.setText("已交给电脑端下载器，目录："+directory+(result!=null&&!result.optBoolean("directory_sent")?"\n"+result.optString("message"):"")+"\n外部下载完成后，点击下方检查入库。");return;
            }
            if(phase.equals("failed")||phase.equals("partial")||phase.equals("cancelled")){status.setText("下载未完成："+state.optString("error","请检查电脑端任务"));return;}
            status.setText(phase.equals("paused")?"电脑端已暂停后台队列…":phase.equals("queued")?"等待电脑端下载…":phase.equals("importing")?"视频已保存，正在补充影视资料…":payload==null?"电脑端正在下载…":payload.optString("message","电脑端正在下载…"));
            downloadUpdates.postDelayed(()->pollDownload(task,workId,status,ticket),1000);
        });
    }
    private void filterMetadata(String field,String value){
        NavigationState state=new NavigationState();
        state.kind=kind;state.query=query;state.tag=tagFilter;state.actor=actorFilter;state.yearMin=yearMinFilter;state.yearMax=yearMaxFilter;state.ratingMin=ratingMinFilter;state.tagsAll=tagsAllFilter;
        state.tagsAny=tagsAnyFilter;state.tagsNot=tagsNotFilter;state.sort=sortField;state.watch=watchFilter;state.list=savedList;state.descending=sortDescending;
        state.discoverySort=discoverySort;state.discoveryDescending=discoveryDescending;
        state.discoveryOnline=discoveryOnline;state.discoveryProvider=discoveryProvider;state.searchTask=discoverySearchTask;state.searchState=discoverySearchState;state.searchMessage=discoverySearchMessage;state.searchErrors=discoverySearchErrors;state.resultIds=discoveryResultIds==null?null:discoveryResultIds.toString();
        state.resultTag=discoveryResultTag;state.nextSearchFilters=discoveryNextSearchFilters!=null;
        state.mainPage=mainPage;state.actorPhoto=actorPhoto;state.actorPhotoName=actorPhotoName;state.watchlistOnly=watchlistOnly;state.dislikedOnly=dislikedOnly;state.favorites=favorites;state.recommended=recommended;state.discovery=discovery;state.actresses=actresses;
        state.gridIndex=discoveryGridIndex;state.gridScroll=discoveryGridScroll;state.offset=offset;state.scroll=browseScroll==null?0:browseScroll.getScrollY();
        state.detailScroll=detailScroll==null?0:detailScroll.getScrollY();
        try{state.detail=detailId>0&&detail!=null?new JSONObject(detail.toString()):null;}catch(Exception ignored){}
        navigationHistory.addLast(state);while(navigationHistory.size()>20)navigationHistory.removeFirst();
        savedList="";watchFilter="";tagFilter=field.equals("tag")?value:"";actorFilter=field.equals("actor")?value:"";
        yearMinFilter="";yearMaxFilter="";ratingMinFilter="";tagsAllFilter="";tagsAnyFilter="";tagsNotFilter="";discoveryNextSearchFilters=null;favorites=false;watchlistOnly=false;dislikedOnly=false;mainPage="library";recommended=false;discovery=state.discovery;actresses=false;discoveryOnline=false;query="";kind="";showLibrary();
    }
    private void restoreNavigation(){
        NavigationState state=navigationHistory.removeLast();actorPhoto=state.actorPhoto==null?"":state.actorPhoto;actorPhotoName=state.actorPhotoName==null?"":state.actorPhotoName;
        kind=state.kind;query=state.query;tagFilter=state.tag;actorFilter=state.actor;yearMinFilter=state.yearMin;yearMaxFilter=state.yearMax;ratingMinFilter=state.ratingMin;tagsAllFilter=state.tagsAll;
        tagsAnyFilter=state.tagsAny==null?"":state.tagsAny;tagsNotFilter=state.tagsNot==null?"":state.tagsNot;sortField=state.sort;watchFilter=state.watch;savedList=state.list;sortDescending=state.descending;
        discoverySort=state.discoverySort;discoveryDescending=state.discoveryDescending;
        discoveryOnline=state.discoveryOnline;discoveryProvider=state.discoveryProvider;discoverySearchTask=state.searchTask;discoverySearchState=state.searchState;discoverySearchMessage=state.searchMessage;discoverySearchErrors=state.searchErrors;
        discoveryResultTag=state.resultTag;
        try{discoveryResultIds=state.resultIds==null?null:new JSONArray(state.resultIds);}catch(Exception ignored){discoveryResultIds=null;}
        mainPage=state.mainPage;watchlistOnly=state.watchlistOnly;dislikedOnly=state.dislikedOnly;favorites=state.favorites;recommended=state.recommended;discovery=state.discovery;actresses=state.actresses;
        discoveryNextSearchFilters=state.nextSearchFilters?discoveryFilterState():null;discoveryGridIndex=state.gridIndex;discoveryGridScroll=state.gridScroll;discoveryRestoreScroll=discovery;showLibrary();restoreOffset=Math.max(1,state.offset);restoreScroll=state.scroll;
        if(state.detail!=null){
            browseRoot=root;
            try{renderDetail(state.detail);ScrollView target=detailScroll;target.post(()->target.scrollTo(0,state.detailScroll));}
            catch(Exception error){message(error.getMessage());}
        }
    }
    private void returnLibrary(){
        if(browseRoot!=null&&detail!=null){
            long id=detail.optLong("id");JSONObject record=browseRecords.get(id);
            if(record!=null){
                try{for(String field:new String[]{"favorite","watchlist","rating","watch_state","liked","disliked"})record.put(field,detail.opt(field));}catch(Exception ignored){}
                if(discovery&&discoveryCoordinator!=null)discoveryCoordinator.personalChanged(id,record);else{
                Button favorite=browseRoot.findViewWithTag("mark:"+id+":favorite");
                if(favorite!=null){markStyle(favorite,record,"favorite",record.optInt("favorite")==1,true);favorite.setEnabled(true);}
                if((favorites&&record.optInt("favorite")==0)||(watchlistOnly&&record.optInt("watchlist")==0)||(dislikedOnly&&record.optInt("disliked")==0)||(!watchFilter.isEmpty()&&!watchFilter.equals(record.optString("watch_state")))){
                    View card=browseRoot.findViewWithTag("card:"+id);if(card!=null&&card.getParent() instanceof android.view.ViewGroup){((android.view.ViewGroup)card.getParent()).removeView(card);offset=Math.max(0,offset-1);int position=browsePositions.getOrDefault(id,-1);browsePositions.remove(id);for(Long key:new java.util.ArrayList<>(browsePositions.keySet()))if(browsePositions.get(key)>position)browsePositions.put(key,browsePositions.get(key)-1);}
                }
                }
            }
        }
        detailId=0;renderedDetailId=0;detailScroll=null;generation++;
        if(browseRoot!=null){root=browseRoot;setContentView(root);if(discovery&&discoveryCoordinator!=null){discoveryEdgeToEdge();discoveryCoordinator.setActive(true);}imageRequests.restore(api,root);browseRoot=null;if(browseLoading!=null){content.removeView(browseLoading);browseLoading=null;loadPage();}if(discovery&&discoveryOnline&&!discoverySearchTask.isEmpty()&&discoverySearchBusy())pollDiscoverySearch(discoverySearchTask,generation);}else showLibrary();
    }
    private void sorting(){
        if(discovery){
            if(discoveryCoordinator!=null)discoveryCoordinator.onSelectSort(discoverySort);return;
        }
        showDialog(new AlertDialog.Builder(this).setTitle("排序").setItems(new String[]{"入库时间","名称","年份","个人评分","时长","切换升序 / 降序"},(d,index)->{
            if(index==5)sortDescending=!sortDescending;else sortField=new String[]{"added","title","year","rating","duration"}[index];
            getSharedPreferences("catalog",0).edit().putString("sort",sortField).putBoolean("descending",sortDescending).apply();showLibrary();
        }));
    }
    private void smartLists(){
        LinearLayout page=utility("lists","智能片单");LinearLayout tools=MediaStyle.row(this);TextView subtitle=text("按保存的筛选条件组织影片",14,MUTED);tools.addView(subtitle,new LinearLayout.LayoutParams(0,-2,1));Button create=button("＋ 新建",()->{resetBrowseFilters();mainPage="library";creatingSmartList=true;showLibrary();showFilters();});BiliMainUi.lightAction(create,"",false);create.setTag("newSmartList");tools.addView(create);page.addView(tools);
        TextView loading=text("正在读取片单…",14,MUTED);page.addView(loading);
        request(()->api.get("/api/lists"),result->{
            page.removeView(loading);JSONArray lists=result.getJSONArray("items");if(lists.length()==0){page.addView(text("还没有片单。进入媒体库筛选影片后，在当前列表操作中保存片单。",15,MUTED));return;}
            for(int i=0;i<lists.length();i++){
                JSONObject list=lists.getJSONObject(i);String name=list.optString("name");JSONObject filters=list.optJSONObject("filters");String summary=listSummary(filters);View card=BiliMainUi.playlistCard(this,name,summary,()->openSmartList(name,filters));card.setTag("smartList:"+name);LinearLayout.LayoutParams size=new LinearLayout.LayoutParams(-1,-2);size.setMargins(0,dp(12),0,0);page.addView(card,size);
                card.setOnLongClickListener(v->{showDialog(new AlertDialog.Builder(this).setTitle(name).setMessage(summary).setPositiveButton("打开片单",(d,which)->openSmartList(name,filters)).setNegativeButton("关闭",null));return true;});
                request(()->api.get("/api/works?offset=0&limit=3&list="+android.net.Uri.encode(name)),reply->{FrameLayout art=card.findViewWithTag("playlistArtwork");JSONArray works=reply.optJSONArray("items");if(works!=null&&works.length()>0){art.removeAllViews();for(int j=0;j<Math.min(3,works.length());j++){ImageView poster=new ImageView(this);poster.setScaleType(ImageView.ScaleType.CENTER_CROP);FrameLayout.LayoutParams image=new FrameLayout.LayoutParams(dp(56),dp(84));image.leftMargin=dp(j*18);image.topMargin=dp(12-j*5);art.addView(poster,image);loadImage(poster,works.optJSONObject(j).optString("cover"));}}TextView count=text("共 "+reply.optInt("total")+" 部",12,MUTED);count.setTag("playlistCount:"+name);card.setContentDescription(name+" · "+reply.optInt("total")+" 部 · "+summary);if(card instanceof android.view.ViewGroup){android.view.ViewGroup row=(android.view.ViewGroup)((android.view.ViewGroup)card).getChildAt(0);android.view.ViewGroup labels=(android.view.ViewGroup)row.getChildAt(1);labels.addView(count,1);}},error->{});
            }
            page.addView(text("从媒体库筛选后，可在当前列表操作中保存为智能片单",13,MUTED));
        },error->{loading.setText("读取失败："+error);page.addView(button("重试",this::smartLists));});
    }
    private void openSmartList(String name,JSONObject stored){
        utilityPage="";resetBrowseFilters();mainPage="mine";savedList=name;if(stored!=null){String sort=stored.optString("sort","added");sortField=java.util.Arrays.asList("added","title","year","rating","duration").contains(sort)?sort:"added";sortDescending=stored.optBoolean("descending",true);}showLibrary();
    }
    private String listSummary(JSONObject filters){
        if(filters==null)return "已保存的筛选条件";java.util.ArrayList<String> labels=new java.util.ArrayList<>();if(filters.optBoolean("favorite"))labels.add("已收藏");if(filters.optBoolean("watchlist"))labels.add("想看");if(filters.optBoolean("disliked"))labels.add("不喜欢");if(filters.has("rating_min"))labels.add("评分 ≥ "+filters.optInt("rating_min"));if(!filters.optString("watch_state").isEmpty())labels.add(filters.optString("watch_state").equals("unwatched")?"未看":filters.optString("watch_state").equals("completed")?"已完成":"观看中");for(String key:new String[]{"tags_all","tags_any","tags_not"}){JSONArray tags=filters.optJSONArray(key);if(tags!=null&&tags.length()>0)labels.add((key.equals("tags_not")?"排除 ":key.equals("tags_any")?"任一 ":"")+android.text.TextUtils.join("、",jsonStrings(tags)));}if(!filters.optString("actor").isEmpty())labels.add(filters.optString("actor"));return labels.isEmpty()?"已保存的筛选条件":android.text.TextUtils.join(" · ",labels);
    }
    private java.util.List<String> jsonStrings(JSONArray array){java.util.ArrayList<String> values=new java.util.ArrayList<>();for(int i=0;i<array.length();i++)values.add(array.optString(i));return values;}
    void saveSmartList(){
        EditText input=new EditText(this);input.setSingleLine(true);input.setHint("片单名称（同名会覆盖）");
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("保存当前筛选为片单").setView(input).setPositiveButton("保存",null).setNegativeButton("取消",null).create();dialog.show();MediaStyle.sheet(dialog);
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view->{
            if(input.getText().toString().trim().isEmpty()){input.setError("请输入片单名称");return;}
            try{
                JSONObject filters=new JSONObject().put("query",query).put("sort",sortField).put("descending",sortDescending);
                if(!kind.isEmpty())filters.put("kinds",new JSONArray().put(kind));if(favorites)filters.put("favorite",true);if(watchlistOnly)filters.put("watchlist",true);if(dislikedOnly)filters.put("disliked",true);
                JSONArray tags=new JSONArray();if(!tagFilter.isEmpty())tags.put(tagFilter);if(!tagsAllFilter.isEmpty())for(String tag:tagsAllFilter.split("[,，]"))if(!tag.trim().isEmpty())tags.put(tag.trim());if(tags.length()>0)filters.put("tags_all",tags);
                for(String key:new String[]{"tags_any","tags_not"}){String raw=key.equals("tags_any")?tagsAnyFilter:tagsNotFilter;JSONArray values=new JSONArray();for(String value:raw.split("[,，]"))if(!value.trim().isEmpty())values.put(value.trim());if(values.length()>0)filters.put(key,values);}
                if(!actorFilter.isEmpty())filters.put("actor",actorFilter);if(!yearMinFilter.isEmpty())filters.put("year_min",Integer.parseInt(yearMinFilter));if(!yearMaxFilter.isEmpty())filters.put("year_max",Integer.parseInt(yearMaxFilter));if(!ratingMinFilter.isEmpty())filters.put("rating_min",Integer.parseInt(ratingMinFilter));if(!watchFilter.isEmpty())filters.put("watch_state",watchFilter);
                JSONObject payload=new JSONObject().put("name",input.getText().toString().trim()).put("filters",filters);
                dialog.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(false);
                request(()->api.post("/api/lists",payload),ok->{dialog.dismiss();message("片单已保存，可在我的 → 智能片单查看");},error->{dialog.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(true);input.setError("保存失败："+error);});
            }catch(Exception error){input.setError(error.getMessage());}
        });
    }
    private void watchAction(long workId,Long fileId){
        showDialog(new AlertDialog.Builder(this).setTitle("观看状态").setItems(fileId==null?new String[]{"标记已看","标记未看 / 重置进度"}:new String[]{"标记已看","标记未看 / 重置进度","从头播放"},(d,index)->{
            try{JSONObject payload=new JSONObject().put("state",index==0?"completed":"unwatched");if(fileId!=null)payload.put("file_id",fileId);else if(index==2)payload.put("file_id",detail.optLong("resume_file_id"));
                request(()->api.post("/api/works/"+workId+"/watched",payload),ok->{if(index==2){startPlayer(fileId!=null?fileId:detail.optLong("resume_file_id"),false);}else openDetail(workId);});
            }catch(Exception e){message(e.getMessage());}
        }));
    }
    private void showGallery(JSONArray paths,int start){
        if(paths.length()==0)return;
        android.app.Dialog dialog=new android.app.Dialog(this,android.R.style.Theme_Material_NoActionBar_Fullscreen);
        LinearLayout page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);page.setBackgroundColor(Color.BLACK);
        int[] index={start};ZoomImage[] image={null};TextView title=text("",16,Color.WHITE);
        Runnable render=()->{title.setText((index[0]+1)+" / "+paths.length()+" · 双指缩放，缩小时左右滑动切换");image[0].resetZoom();image[0].setImageDrawable(null);loadImage(image[0],paths.optString(index[0]));};
        image[0]=new ZoomImage(this,delta->{index[0]=(index[0]+delta+paths.length())%paths.length();render.run();});
        page.addView(title);page.addView(image[0],new LinearLayout.LayoutParams(-1,0,1));LinearLayout controls=MediaStyle.actionRow(this);
        controls.addView(button("上一张",()->{index[0]=(index[0]+paths.length()-1)%paths.length();render.run();}));controls.addView(button("下一张",()->{index[0]=(index[0]+1)%paths.length();render.run();}));controls.addView(button("关闭",dialog::dismiss));page.addView(controls);
        dialog.setContentView(page);dialog.show();render.run();
    }
    void queueEditor(){
        android.content.SharedPreferences prefs=getSharedPreferences("queue",0);
        try{
            final String captured=prefs.getString("ids","[]");JSONArray ids=new JSONArray(captured);
            if(ids.length()==0){showDialog(new AlertDialog.Builder(this).setTitle("手机播放队列").setMessage("队列为空。可从影片详情加入，或随机播放当前列表。此队列保存在手机，与电脑队列独立。").setPositiveButton("关闭",null));return;}
            StringBuilder queryIds=new StringBuilder();for(int i=0;i<ids.length();i++){if(i>0)queryIds.append(",");queryIds.append(ids.optLong(i));}
            request(()->api.get("/api/queue-titles?ids="+queryIds),reply->{
                if(!captured.equals(prefs.getString("ids","[]"))){message("手机队列已更新，请重新打开队列");return;}
                final String[] expected={captured};final AlertDialog[] editor={null};java.util.function.BooleanSupplier currentQueue=()->{if(expected[0].equals(prefs.getString("ids","[]")))return true;if(editor[0]!=null)editor[0].dismiss();message("手机队列已更新，请重新打开队列");return false;};
                java.util.ArrayList<Long> values=new java.util.ArrayList<>();for(int i=0;i<ids.length();i++)values.add(ids.getLong(i));JSONObject titles=reply.optJSONObject("titles");
                LinearLayout page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);page.setPadding(dp(16),dp(8),dp(16),dp(8));TextView queueHint=text("手机队列与电脑独立。拖动右侧把手排序，也可用上移、下移。",13,MUTED);queueHint.setMaxLines(2);queueHint.setEllipsize(android.text.TextUtils.TruncateAt.END);page.addView(queueHint);
                ListView list=new ListView(this);list.setTag("phoneQueueItems");list.setChoiceMode(ListView.CHOICE_MODE_SINGLE);page.addView(list,new LinearLayout.LayoutParams(-1,dp(280),1));
                final int[] selected={Math.min(prefs.getInt("index",0),values.size()-1)};ArrayAdapter<String> adapter=new BiliQueueAdapter(this,index->{selected[0]=index;list.setItemChecked(index,true);});list.setAdapter(adapter);
                LinearLayout controls=MediaStyle.actionRow(this);controls.setTag("phoneQueueActions");controls.setPadding(0,dp(8),0,dp(8));
                Runnable render=()->{adapter.clear();for(int i=0;i<values.size();i++){long id=values.get(i);adapter.add((i+1)+". "+(titles==null?"作品 #"+id:titles.optString(String.valueOf(id),"已移除的作品")));}adapter.notifyDataSetChanged();if(!values.isEmpty()){selected[0]=Math.max(0,Math.min(selected[0],values.size()-1));list.setItemChecked(selected[0],true);}};
                list.setOnItemClickListener((parent,view,index,id)->selected[0]=index);
                page.addView(controls);
                list.setOnDragListener((view,event)->{
                    if(!(event.getLocalState() instanceof Integer))return false;
                    switch(event.getAction()){
                        case android.view.DragEvent.ACTION_DRAG_STARTED:return currentQueue.getAsBoolean();
                        case android.view.DragEvent.ACTION_DRAG_LOCATION:if(event.getY()<dp(40))list.smoothScrollBy(-dp(24),100);else if(event.getY()>list.getHeight()-dp(40))list.smoothScrollBy(dp(24),100);return true;
                        case android.view.DragEvent.ACTION_DROP:
                            if(!currentQueue.getAsBoolean())return false;
                            int from=(Integer)event.getLocalState(),target=list.pointToPosition((int)event.getX(),(int)event.getY());if(from<0||from>=values.size()||target<0||target>=values.size())return false;
                            long current=values.get(Math.max(0,Math.min(prefs.getInt("index",0),values.size()-1))),selectedId=values.get(Math.max(0,Math.min(selected[0],values.size()-1)));Long moving=values.remove(from);values.add(target,moving);selected[0]=values.indexOf(selectedId);String updated=new JSONArray(values).toString();prefs.edit().putString("ids",updated).putInt("index",Math.max(0,values.indexOf(current))).apply();expected[0]=updated;render.run();return true;
                        default:return true;
                    }
                });
                java.util.function.IntConsumer change=action->{
                    if(!currentQueue.getAsBoolean()||values.isEmpty())return;int index=Math.max(0,Math.min(selected[0],values.size()-1));long current=values.get(Math.max(0,Math.min(prefs.getInt("index",0),values.size()-1)));
                    if(action==0){prefs.edit().putInt("index",index).apply();Intent intent=new Intent(this,PlayerActivity.class);intent.putExtra("work_id",values.get(index));intent.putExtra("queue",true);startActivity(intent);return;}
                    if(action==3)values.remove(index);else {int target=action==1?index-1:index+1;if(target<0||target>=values.size())return;java.util.Collections.swap(values,index,target);selected[0]=target;}
                    String updated=new JSONArray(values).toString();prefs.edit().putString("ids",updated).putInt("index",Math.max(0,values.indexOf(current))).apply();expected[0]=updated;render.run();
                };
                String[] labels={"播放","上移","下移","移除"};for(int i=0;i<labels.length;i++){final int action=i;Button control=button(labels[i],()->change.accept(action));BiliMainUi.lightAction(control,"",false);if(control instanceof com.google.android.material.button.MaterialButton)((com.google.android.material.button.MaterialButton)control).setIcon(null);controls.addView(control,new LinearLayout.LayoutParams(0,-2,1));}
                Spinner repeat=new Spinner(this);repeat.setContentDescription("手机队列循环模式");repeat.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"播完停止","列表循环","单部循环"}));repeat.setSelection(prefs.getInt("repeat",0));repeat.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onNothingSelected(AdapterView<?> parent){}public void onItemSelected(AdapterView<?> parent,View view,int mode,long id){prefs.edit().putInt("repeat",mode).apply();}});page.addView(repeat,new LinearLayout.LayoutParams(-1,dp(48)));
                AlertDialog dialog=new AlertDialog.Builder(this).setTitle("手机播放队列").setView(page).setNegativeButton("关闭",null).create();editor[0]=dialog;dialog.show();MediaStyle.sheet(dialog);render.run();
            });
        }catch(Exception error){message(error.getMessage());}
    }

    private PersonalState personalState(Api client,long id){
        if(personalClient!=client){personalClient=client;personalStates.clear();personalIntent=0;personalConfirmation=0;}
        PersonalState state=personalStates.get(id);if(state==null){state=new PersonalState();personalStates.put(id,state);}return state;
    }
    private long personalReadVersion(Api client){personalState(client,detailId);return personalConfirmation;}
    long beginPersonalWrite(Api client,long id,String field){
        PersonalState state=personalState(client,id);long intent=++personalIntent;
        // Favorite, liked and disliked are one mutually exclusive server operation.
        if(field.equals("favorite")||field.equals("liked")||field.equals("disliked"))for(String key:new String[]{"favorite","liked","disliked"})state.intents.put(key,intent);else state.intents.put(field,intent);return intent;
    }
    static void copyPersonal(JSONObject target,JSONObject fields){
        if(target==null||fields==null)return;try{for(String key:PERSONAL_FIELDS)if(fields.has(key))target.put(key,fields.opt(key));}catch(Exception ignored){}
    }
    JSONObject confirmPersonalWrite(Api client,long id,long intent,JSONObject fields,String field,Object value){
        JSONObject accepted=new JSONObject();if(isDestroyed()||api!=client)return accepted;PersonalState state=personalState(client,id);long confirmation=++personalConfirmation;
        try{
            if(fields==null){fields=new JSONObject().put(field,value instanceof Boolean?((Boolean)value?1:0):value);if(field.equals("favorite")){fields.put("liked",Boolean.TRUE.equals(value)?1:0);if(Boolean.TRUE.equals(value))fields.put("disliked",0);}}
            for(String key:PERSONAL_FIELDS){if(!fields.has(key))continue;PersonalValue previous=state.confirmed.get(key);if(state.intents.getOrDefault(key,0L)>intent||(previous!=null&&previous.intent>intent))continue;Object canonical=fields.opt(key);accepted.put(key,canonical);state.confirmed.put(key,new PersonalValue(canonical,intent,confirmation));}
        }catch(Exception ignored){}
        // A list write may finish while this work's older detail is already visible.
        if(detailId==id&&detail!=null&&detail.optLong("id")==id){copyPersonal(detail,accepted);refreshPersonalButtons(detail,accepted);}
        return accepted;
    }
    private void mergePersonalRead(Api client,long id,long version,JSONObject work){
        if(api!=client||personalClient!=client)return;PersonalState state=personalStates.get(id);if(state==null)return;
        // Only overlay confirmations newer than this GET, so later reads can still see external edits.
        try{for(java.util.Map.Entry<String,PersonalValue> entry:state.confirmed.entrySet()){PersonalValue value=entry.getValue();if(value.confirmation>version&&state.intents.getOrDefault(entry.getKey(),0L)<=value.intent)work.put(entry.getKey(),value.value);}}catch(Exception ignored){}
    }
    private void refreshPersonalButtons(JSONObject work,JSONObject fields){
        if(root==null)return;long id=work.optLong("id");for(String field:new String[]{"favorite","watchlist"})if(fields.has(field)){Button button=root.findViewWithTag("mark:"+id+":"+field);if(button!=null)markStyle(button,work,field,work.optInt(field)==1,false);}
        if(fields.has("rating")){Button score=root.findViewWithTag("rating:"+id);if(score!=null){score.setText(work.isNull("rating")?getString(R.string.personal_rating_unset):getString(R.string.personal_rating_value,work.optInt("rating")));MediaStyle.icon(score,"star",!work.isNull("rating"));}}
    }
    private void detailAction(Button button,String icon,boolean selected){BiliMainUi.lightAction(button,icon,selected);if(button instanceof com.google.android.material.button.MaterialButton)((com.google.android.material.button.MaterialButton)button).setIconGravity(com.google.android.material.button.MaterialButton.ICON_GRAVITY_TEXT_TOP);button.setPaddingRelative(button.getPaddingStart(),dp(4),button.getPaddingEnd(),dp(4));button.setMinHeight(dp(64));button.setMinimumHeight(dp(64));}
    private void markStyle(Button button,JSONObject work,String field,boolean active,boolean compact){
        String title=field.equals("favorite")?"收藏":"想看";
        button.setText(compact?"":(active?"已":"")+title);button.setContentDescription((active?"取消":"加入")+title);
        if(compact)MediaStyle.cardMark(button,field.equals("favorite")?"heart":"bookmark",active);else detailAction(button,field.equals("favorite")?"heart":"bookmark",active);
    }
    private Button markButton(JSONObject work,String field,boolean compact){
        Button button=compact?MediaStyle.cardIcon(this):button("",()->{});button.setTag("mark:"+work.optLong("id")+":"+field);markStyle(button,work,field,work.optInt(field)==1,compact);
        button.setOnClickListener(view->{
            boolean old=work.optInt(field)==1,value=!old;int ticket=generation;Api client=api;long id=work.optLong("id"),intent=beginPersonalWrite(client,id,field);
            markStyle(button,work,field,value,compact);button.setEnabled(false);
            network.execute(()->{
                try{
                    JSONObject result=client.post("/api/works/"+id+"/personal",new JSONObject().put(field,value));
                    runOnUiThread(()->{
                        if(isDestroyed())return;
                        copyPersonal(work,confirmPersonalWrite(client,id,intent,result.optJSONObject("personal"),field,value));
                        if(ticket!=generation)return;
                        Button current=root.findViewWithTag("mark:"+work.optLong("id")+":"+field);
                        if(current!=null){markStyle(current,work,field,work.optInt(field)==1,compact);current.setEnabled(true);}
                        if(field.equals("favorite")&&favorites&&!value&&detailId==0){View card=root.findViewWithTag("card:"+work.optLong("id"));if(card!=null&&card.getParent() instanceof android.view.ViewGroup)((android.view.ViewGroup)card.getParent()).removeView(card);}
                        message(value?"已加入"+(field.equals("favorite")?"收藏":"想看"):"已取消"+(field.equals("favorite")?"收藏":"想看"));
                    });
                }catch(Exception error){runOnUiThread(()->{if(!isDestroyed()&&ticket==generation){Button current=root.findViewWithTag("mark:"+work.optLong("id")+":"+field);if(current!=null){markStyle(current,work,field,old,compact);current.setEnabled(true);}message("未保存："+error.getMessage());}});}
            });
        });return button;
    }
    private void personal(String field,Object value) {
        long id=detailId;JSONObject current=detail;Api client=api;long intent=beginPersonalWrite(client,id,field);
        request(()->client.post("/api/works/"+id+"/personal",new JSONObject().put(field,value)),result->{
            copyPersonal(current,confirmPersonalWrite(client,id,intent,result.optJSONObject("personal"),field,value));Button score=root.findViewWithTag("rating:"+id);
            if(score!=null){score.setText(current.isNull("rating")?"评分":current.optInt("rating")+" 分");detailAction(score,"star",!current.isNull("rating"));}
            message("评分已保存");
        });
    }
    private void startPlayer(long fileId,boolean queue) {
        if(fileId<=0){message("没有可播放的视频");return;}
        startActivity(playerIntent(fileId,queue));
    }
    private Intent playerIntent(long fileId,boolean queue){
        Intent intent=new Intent(this,PlayerActivity.class);intent.putExtra("work_id",detailId);intent.putExtra("file_id",fileId);intent.putExtra("queue",queue);
        intent.putExtra("browse_path",listPath().replaceFirst("offset=[0-9]+&limit=30&",""));
        intent.putExtra("browse_position",browsePositions.getOrDefault(detailId,-1));return intent;
    }
    private Button globalShuffleButton(){
        Button action=button(getString(R.string.global_shuffle_action),this::showGlobalShuffle);
        action.setTag("globalShuffle");BiliMainUi.lightAction(action,"shuffle",false);action.setTextColor(BLUE);if(action instanceof com.google.android.material.button.MaterialButton)((com.google.android.material.button.MaterialButton)action).setIconTint(android.content.res.ColorStateList.valueOf(BLUE));return action;
    }
    private void showGlobalShuffle(){
        if(api==null)return;
        String saved=getSharedPreferences("global_shuffle",0).getString("scope","");
        int initial=java.util.Arrays.asList(GLOBAL_SHUFFLE_KINDS).indexOf(saved);
        final int[] selected={Math.max(0,initial)};
        LinearLayout heading=new LinearLayout(this);heading.setOrientation(LinearLayout.VERTICAL);heading.setPadding(dp(24),dp(16),dp(24),dp(8));
        heading.addView(text(getString(R.string.global_shuffle_scope_title),20,MediaStyle.TEXT));
        TextView explanation=text(getString(R.string.global_shuffle_scope_hint),12,MUTED);explanation.setTag("globalShuffleHint");explanation.setPadding(0,dp(8),0,0);heading.addView(explanation);
        AlertDialog dialog=new AlertDialog.Builder(this).setCustomTitle(heading)
            .setSingleChoiceItems(R.array.global_shuffle_scopes,selected[0],(choice,index)->selected[0]=index)
            .setNegativeButton(R.string.global_shuffle_cancel,null)
            .setPositiveButton(R.string.global_shuffle_start,(choice,which)->{
                String scope=GLOBAL_SHUFFLE_KINDS[selected[0]];
                getSharedPreferences("global_shuffle",0).edit().putString("scope",scope).apply();
                shuffleGlobal(scope);
            }).create();
        dialog.show();MediaStyle.sheet(dialog);
    }
    private void shuffleGlobal(String kindScope){
        final Api client=api;if(client==null)return;
        final int attempt=++shuffleRequest;
        final String scope="/api/works"+(kindScope.isEmpty()?"":"?kind="+kindScope);
        request(()->{
            JSONObject result=client.post("/api/queue/from-browse",new JSONObject().put("browse_path",scope));
            JSONArray ids=result.getJSONArray("ids");for(int index=0;index<ids.length();index++)if(ids.getLong(index)<=0)throw new Exception(getString(R.string.global_shuffle_invalid_response));
            return result;
        },result->{
            if(client!=api||attempt!=shuffleRequest)return;
            JSONArray ids=result.getJSONArray("ids");if(ids.length()==0){message(getString(R.string.global_shuffle_empty));return;}
            Intent intent=new Intent(this,PlayerActivity.class);intent.putExtra("work_id",ids.getLong(0));intent.putExtra("queue",true);
            getSharedPreferences("queue",0).edit().putString("ids",ids.toString()).putInt("index",0).apply();startActivity(intent);
        },error->{
            if(client!=api||attempt!=shuffleRequest)return;
            String explanation=error!=null&&error.contains("404")?getString(R.string.global_shuffle_update_required):getString(R.string.global_shuffle_failed,error);
            showDialog(new AlertDialog.Builder(this).setTitle(R.string.global_shuffle_failed_title).setMessage(explanation).setPositiveButton(R.string.global_shuffle_close,null));
        });
    }
    void shuffle() {
        final Api client=api;if(client==null)return;
        final int attempt=++shuffleRequest;
        final String scope=listPath();
        request(()->client.post("/api/queue/from-browse",new JSONObject().put("browse_path",scope)),result->{
            if(client!=api||attempt!=shuffleRequest)return;
            JSONArray ids=result.getJSONArray("ids");if(ids.length()==0){message("当前列表没有可播放的本地视频");return;}
            getSharedPreferences("queue",0).edit().putString("ids",ids.toString()).putInt("index",0).apply();
            Intent intent=new Intent(this,PlayerActivity.class);intent.putExtra("work_id",ids.getLong(0));intent.putExtra("queue",true);startActivity(intent);
        },error->{
            if(client!=api||attempt!=shuffleRequest)return;
            String explanation=error!=null&&error.contains("404")?"当前电脑版本不支持按列表随机播放，请更新电脑端后重试。":"无法生成当前列表的播放队列："+error;
            showDialog(new AlertDialog.Builder(this).setTitle("未开始随机播放").setMessage(explanation).setPositiveButton("关闭",null));
        });
    }
    private String statsValue(JSONObject stats,String key){return stats.has(key)&&!stats.isNull(key)?Long.toString(stats.optLong(key)):"—";}
    private void showStats() {
        LinearLayout page=utility("stats","观影统计");page.addView(BiliMainUi.settingsRow(this,"与电脑共享观影记录","remote",()->message("观看记录由当前电脑媒体库提供")));TextView loading=text("正在读取观看记录…",14,MUTED);page.addView(loading);
        request(()->api.get("/api/stats"),stats->{page.removeView(loading);page.addView(BiliMainUi.metric(this,stats.has("seconds")?String.format(java.util.Locale.ROOT,"%.1f 小时",stats.optDouble("seconds")/3600):"—","累计实际观看","phone_queue"));
            String[] values={statsValue(stats,"valid"),statsValue(stats,"sessions"),statsValue(stats,"movies"),statsValue(stats,"series")};String[] labels={"有效播放","播放会话","部电影","部剧集"},icons={"play","smart_playlist","library","remote"};for(int row=0;row<2;row++){LinearLayout pair=MediaStyle.row(this);pair.setPadding(0,dp(12),0,0);for(int col=0;col<2;col++){int index=row*2+col;pair.addView(BiliMainUi.metric(this,values[index],labels[index],icons[index]),new LinearLayout.LayoutParams(0,-2,1));}page.addView(pair);}page.addView(BiliMainUi.section(this,"说明"));LinearLayout explanation=BiliMainUi.group(this);explanation.addView(BiliMainUi.settingsRow(this,"有效播放须严格超过 600 秒","check",()->message("累计观看时长严格超过 600 秒才计为有效播放")));explanation.addView(BiliMainUi.settingsRow(this,"观看记录来自实际播放","statistics",()->message("统计来自实际播放会话，不按标记状态推算")));page.addView(BiliMainUi.groupCard(this,explanation));page.addView(BiliMainUi.settingsRow(this,"详细统计","statistics",()->{try{showDialog(new AlertDialog.Builder(this).setTitle("详细统计").setMessage(stats.toString(2)).setPositiveButton("关闭",null));}catch(Exception error){message(error.getMessage());}}));
        },error->{loading.setText("读取失败："+error);page.addView(button("重试",this::showStats));});
    }
}
