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

public final class MainActivity extends Activity {
    private static final int BG=MediaStyle.BG, BLUE=MediaStyle.ACCENT, MUTED=MediaStyle.MUTED;
    private final android.os.Handler downloadUpdates=new android.os.Handler(android.os.Looper.getMainLooper());
    private final ExecutorService network=Executors.newFixedThreadPool(4);
    private final LruCache<String,Bitmap> pictures=new LruCache<String,Bitmap>(24*1024) {
        @Override protected int sizeOf(String key,Bitmap image){return image.getByteCount()/1024;}
    };
    private final ImageRequests imageRequests=new ImageRequests(pictures);
    private Api api;
    private LinearLayout root,content;
    private PosterGrid posters;
    private ScrollView detailScroll;
    private String kind="",query="",tagFilter="",actorFilter="",yearMinFilter="",yearMaxFilter="",ratingMinFilter="",tagsAllFilter="",tagsAnyFilter="",tagsNotFilter="";
    private boolean actresses=false;
    private boolean favorites=false,recommended=false,discovery=false,watchlistOnly=false,dislikedOnly=false;
    private String mainPage="home";
    private boolean mineLanding=false;
    private int offset=0,generation=0;
    private long detailId=0,renderedDetailId=0;
    private boolean returned=false;
    private JSONObject detail;
    private LinearLayout browseRoot;
    private final java.util.Map<Long,JSONObject> browseRecords=new java.util.HashMap<>();
    private String sortField="added",watchFilter="",savedList="";
    private boolean sortDescending=true;
    private static final String[] DISCOVERY_SORT_KEYS={"discovered","site_added","title","year","community_rating"};
    private static final String[] DISCOVERY_SORT_NAMES={"首次发现","网站收录时间","影片名称","发行年份","来源评分"};
    private String discoverySort="discovered";
    private boolean discoveryDescending=true;
    private AutoCompleteTextView discoveryTagInput;
    private boolean discoveryOnline=false,discoveryProvidersLoaded=false;
    private String discoveryProvider="",discoverySearchTask="",discoverySearchState="",discoverySearchMessage="",discoverySearchErrors="";
    private JSONArray discoveryProviders=new JSONArray(),discoveryResultIds;
    private String discoveryResultTag="";
    private int discoverySubmission=0;
    private final java.util.Map<Long,Integer> browsePositions=new java.util.HashMap<>();
    private final java.util.ArrayDeque<NavigationState> navigationHistory=new java.util.ArrayDeque<>();
    private ScrollView browseScroll;
    private int restoreOffset=0,restoreScroll=0;
    private TextView browseLoading,catalogCount;
    private LinearLayout continuePanel;
    private static final class NavigationState {
        String kind,query,tag,actor,year,yearMin,yearMax,ratingMin,tagsAll,tagsAny,tagsNot,sort,watch,list,discoverySort,discoveryProvider,searchTask,searchState,searchMessage,searchErrors,resultIds,resultTag;
        boolean favorites,recommended,discovery,actresses,descending,discoveryDescending,discoveryOnline,watchlistOnly,dislikedOnly;
        String mainPage;
        int offset,scroll,detailScroll;
        JSONObject detail;
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        sortField=getSharedPreferences("catalog",0).getString("sort","added");sortDescending=getSharedPreferences("catalog",0).getBoolean("descending",true);
        discoverySort=getSharedPreferences("discovery",0).getString("sort","discovered");discoveryDescending=getSharedPreferences("discovery",0).getBoolean("descending",true);
        if(!java.util.Arrays.asList(DISCOVERY_SORT_KEYS).contains(discoverySort))discoverySort="discovered";
        Connection connection=Connection.load(this);
        if(connection==null)showConnection();else {api=new Api(connection);if(state!=null&&state.containsKey("browse"))restoreBrowseState(state.getBundle("browse"));else showLibrary();}
    }
    @Override protected void onStop() {imageRequests.cancelPage();super.onStop();}
    @Override protected void onStart() {super.onStart();if(api!=null&&root!=null)imageRequests.restore(api,root);}
    @Override protected void onResume() {
        super.onResume();
        if(returned && api!=null) { if(detailId>0)openDetail(detailId);else if(continuePanel!=null)loadContinue(); }
        returned=true;
    }
    @Override public void onConfigurationChanged(Configuration configuration) {
        super.onConfigurationChanged(configuration);
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
        state.putString("mainPage",mainPage);state.putBoolean("mineLanding",mineLanding);state.putBoolean("watchlistOnly",watchlistOnly);state.putBoolean("dislikedOnly",dislikedOnly);
        state.putBoolean("favorites",favorites);state.putBoolean("recommended",recommended);state.putBoolean("discovery",discovery);state.putBoolean("actresses",actresses);
        state.putBoolean("descending",sortDescending);state.putBoolean("discoveryDescending",discoveryDescending);state.putBoolean("online",discoveryOnline);
        state.putString("results",discoveryResultIds==null?null:discoveryResultIds.toString());
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
        if(state.getBoolean("mineLanding")){showMine();return;}
        showLibrary();restoreOffset=Math.max(1,state.getInt("offset"));restoreScroll=state.getInt("scroll");
    }
    @Override public void onBackPressed() {
        if(detailId>0) {returnLibrary();}else if(!navigationHistory.isEmpty())restoreNavigation();else if(!mainPage.equals("home"))navigatePrimary("home");else super.onBackPressed();
    }
    @Override protected void onDestroy() {downloadUpdates.removeCallbacksAndMessages(null);imageRequests.close();network.shutdownNow();super.onDestroy();}
    private int dp(float value){return Math.round(value*getResources().getDisplayMetrics().density);}
    private TextView text(String value,int size,int color) {
        TextView view=new TextView(this);view.setText(value);view.setTextSize(size);if(size>=20)view.setTypeface(android.graphics.Typeface.DEFAULT,android.graphics.Typeface.BOLD);view.setTextColor(color);view.setFontFeatureSettings("kern");view.setPadding(0,dp(5),0,dp(5));return view;
    }
    private Button button(String title,Runnable action) {
        Button button=new Button(this);button.setText(title);button.setTextColor(Color.WHITE);button.setAllCaps(false);button.setTextSize(14);
        MediaStyle.button(button,false,false,false);button.setOnClickListener(v->action.run());return button;
    }
    private void base() {
        imageRequests.cancelPage();
        root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(BG);root.setFitsSystemWindows(true);setContentView(root);
    }
    private void message(String value){if(!isDestroyed())Toast.makeText(this,value,Toast.LENGTH_LONG).show();}
    interface Work {JSONObject run() throws Exception;}
    interface Result {void accept(JSONObject result) throws Exception;}
    private void request(Work work,Result result) {
        request(work,result,null);
    }
    private void request(Work work,Result result,java.util.function.Consumer<String> failed) {
        final int ticket=generation;
        network.execute(()->{
            try {JSONObject value=work.run();runOnUiThread(()->{if(isDestroyed() || ticket!=generation)return;try{result.accept(value);}catch(Exception e){message(e.getMessage());}});}
            catch(Exception e){runOnUiThread(()->{if(!isDestroyed() && ticket==generation){if(failed!=null)failed.accept(e.getMessage());else message("连接失败："+e.getMessage());}});}
        });
    }
    private void showConnection() {
        generation++;detailId=0;api=null;navigationHistory.clear();discovery=false;discoveryProvidersLoaded=false;discoveryProviders=new JSONArray();clearDiscoverySearch();base();
        LinearLayout panel=new LinearLayout(this);panel.setOrientation(LinearLayout.VERTICAL);panel.setPadding(dp(26),dp(40),dp(26),dp(20));ScrollView connectionScroll=new ScrollView(this);connectionScroll.setFillViewport(true);connectionScroll.addView(panel);root.addView(connectionScroll,new LinearLayout.LayoutParams(-1,-1));
        panel.addView(text("Lumen",36,Color.WHITE));panel.addView(text("连接你的家庭媒体库",22,Color.WHITE));
        panel.addView(text("在电脑端设置 → 局域网 / Android 中启动服务。手机与电脑应连接同一 Wi-Fi。",15,MUTED));
        AutoCompleteTextView address=new SearchDropdown(this);address.setSingleLine(true);address.setTextColor(Color.WHITE);address.setHintTextColor(MUTED);address.setHint("http://192.168.1.10:8097");address.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);
        address.setText(getSharedPreferences("connection",0).getString("base",""));
        ArrayAdapter<ServerDiscovery.Server> servers=new ArrayAdapter<>(this,android.R.layout.simple_dropdown_item_1line);
        address.setAdapter(servers);
        address.setOnItemClickListener((parent,view,position,id)->address.setText(servers.getItem(position).address,false));
        LinearLayout addressRow=new LinearLayout(this);addressRow.addView(address,new LinearLayout.LayoutParams(0,dp(48),1));
        addressRow.addView(button("⌄",()->{address.requestFocus();address.showDropDown();}),new LinearLayout.LayoutParams(dp(44),dp(48)));panel.addView(addressRow);MediaStyle.field(address);
        TextView discoveryStatus=text("正在发现同一局域网内的服务端…",13,MUTED);panel.addView(discoveryStatus);
        Button discover=button("重新发现服务端",()->{});panel.addView(discover);
        Runnable scan=()->{
            final int ticket=generation;discover.setEnabled(false);servers.clear();discoveryStatus.setText("正在发现同一局域网内的服务端…");
            network.execute(()->{
                String error="";
                try{ServerDiscovery.scan(server->runOnUiThread(()->{
                    if(!isDestroyed()&&ticket==generation){servers.add(server);servers.notifyDataSetChanged();discoveryStatus.setText("发现 "+servers.getCount()+" 个服务端，可下拉选择");}
                }));}catch(Exception failure){error="发现失败，可手动输入地址";}
                final String failure=error;
                runOnUiThread(()->{if(!isDestroyed()&&ticket==generation){discover.setEnabled(true);discoveryStatus.setText(!failure.isEmpty()?failure:servers.isEmpty()?"未发现服务端。可重试或手动输入；请检查电脑服务和防火墙 UDP 8098。":"发现 "+servers.getCount()+" 个服务端，点击地址旁的 ⌄ 选择");}});
            });
        };
        discover.setOnClickListener(view->scan.run());scan.run();
        EditText token=new EditText(this);token.setSingleLine(true);token.setTextColor(Color.WHITE);token.setHintTextColor(MUTED);token.setHint("电脑端访问密钥");token.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        Connection saved=Connection.load(this);if(saved!=null)token.setText(saved.token);panel.addView(token);
        TextView status=text("",14,MUTED);panel.addView(status);
        Button connect=button("连接服务器",()->{
            try {
                Connection candidate=new Connection(address.getText().toString(),token.getText().toString());Api client=new Api(candidate);
                status.setText("正在连接…");
                request(()->client.get("/api/info"),info->{
                    if(info.optInt("api_version")!=1)throw new Exception("服务端协议版本不兼容");
                    candidate.save(this);api=client;pictures.evictAll();resetBrowseFilters();mainPage="home";showLibrary();
                },error->status.setText("连接失败："+error+"\n请检查电脑服务、地址和访问密钥，然后重试。"));
            }catch(Exception e){status.setText(e.getMessage());}
        });MediaStyle.button(connect,true,false,false);panel.addView(connect);
        panel.addView(text("地址使用电脑的局域网 IPv4，不能填手机自己的 localhost。服务关闭或电脑休眠时，客户端无法播放。",13,MUTED));
        panel.addView(button("检查客户端更新",()->startActivity(new Intent(this,UpdateActivity.class))));
    }
    private void header(String title, boolean back) {
        LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(dp(12),dp(6),dp(12),dp(6));
        if(back||!navigationHistory.isEmpty()){Button previous=button("",this::onBackPressed);MediaStyle.icon(previous,"back",false);previous.setContentDescription("返回上一页");row.addView(previous,new LinearLayout.LayoutParams(dp(48),dp(48)));}
        TextView brand=text(title,24,Color.WHITE);brand.setSingleLine(true);brand.setEllipsize(android.text.TextUtils.TruncateAt.END);brand.setMinHeight(dp(52));row.addView(brand,new LinearLayout.LayoutParams(0,-2,1));
        if(detailId>0&&detail!=null){
            Button more=button("",()->{});more.setTag("detailMore");MediaStyle.icon(more,"more",false);more.setContentDescription("当前影片操作");more.setOnClickListener(this::showDetailActions);row.addView(more,new LinearLayout.LayoutParams(dp(48),dp(48)));
        }else{
            Button tasks=button("",this::showTasks);MediaStyle.quiet(tasks,"server","电脑任务中心");row.addView(tasks,new LinearLayout.LayoutParams(dp(48),dp(48)));
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
        LinearLayout actions=new LinearLayout(this);actions.setOrientation(LinearLayout.VERTICAL);actions.setPadding(dp(20),dp(8),dp(20),dp(12));
        ScrollView scroll=new ScrollView(this);scroll.addView(actions);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("当前影片操作").setView(scroll).setNegativeButton("关闭",null).create();
        actions.addView(text("播放",16,MUTED));
        Button restart=button("从头播放",()->{dialog.dismiss();restartCurrent(workId,fileId);});restart.setEnabled(fileId>0);actions.addView(restart);
        Button remote=button("在电脑上播放",()->{dialog.dismiss();Intent intent=new Intent(this,RemoteActivity.class);intent.putExtra("work_id",workId);intent.putExtra("file_id",fileId);startActivity(intent);});remote.setEnabled(fileId>0);actions.addView(remote);
        actions.addView(button("加入手机播放队列",()->{addToPhoneQueue(workId);dialog.dismiss();}));
        actions.addView(text("观看记录",16,MUTED));actions.addView(button("修改观看状态",()->{dialog.dismiss();watchAction(workId,null);}));
        actions.addView(text("电脑端任务",16,MUTED));actions.addView(button("此影片的电脑任务",()->{dialog.dismiss();TaskCenter.show(this,api,workId);}));dialog.show();
    }
    private void resetBrowseFilters(){
        kind="";query="";tagFilter="";actorFilter="";yearMinFilter="";yearMaxFilter="";ratingMinFilter="";tagsAllFilter="";tagsAnyFilter="";tagsNotFilter="";watchFilter="";savedList="";
        favorites=false;watchlistOnly=false;dislikedOnly=false;recommended=false;discovery=false;actresses=false;navigationHistory.clear();clearDiscoverySearch();
    }
    private void navigatePrimary(String page){
        resetBrowseFilters();mainPage=page;
        if(page.equals("mine")){showMine();return;}
        discovery=page.equals("discover");showLibrary();
    }
    private void bottomNavigation(){
        LinearLayout nav=new LinearLayout(this);nav.setOrientation(LinearLayout.HORIZONTAL);nav.setTag("primaryNavigation");nav.setGravity(Gravity.CENTER_VERTICAL);nav.setPadding(dp(8),dp(5),dp(8),dp(6));nav.setBackgroundColor(MediaStyle.PANEL);
        String[] labels={"首页","媒体库","发现","我的"},pages={"home","library","discover","mine"},icons={"home","library","discover","user"};
        String active=discovery?"discover":favorites||watchlistOnly||!savedList.isEmpty()?"mine":!kind.isEmpty()||actresses?"library":mainPage;
        for(int i=0;i<pages.length;i++){final String page=pages[i];Button tab=MediaStyle.navigation(this,labels[i],icons[i],page.equals(active));tab.setTag("nav:"+page);tab.setOnClickListener(v->navigatePrimary(page));LinearLayout.LayoutParams cell=new LinearLayout.LayoutParams(0,-2,1);cell.setMargins(dp(3),0,dp(3),0);nav.addView(tab,cell);}
        root.addView(nav,new LinearLayout.LayoutParams(-1,-2));
    }
    private void showMine(){
        generation++;mineLanding=true;mainPage="mine";detailId=0;renderedDetailId=0;browseRoot=null;continuePanel=null;detailScroll=null;browseLoading=null;base();header("我的",false);
        ScrollView scroll=new ScrollView(this);LinearLayout page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);page.setPadding(dp(20),dp(8),dp(20),dp(20));scroll.addView(page);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));browseScroll=scroll;
        page.addView(text("我的影片",20,Color.WHITE));
        page.addView(button("收藏",()->openCollection(false)));page.addView(button("想看",()->openCollection(true)));page.addView(button("智能片单",this::smartLists));page.addView(button("观影统计",this::showStats));
        page.addView(text("播放与设备",20,Color.WHITE));page.addView(button("手机播放队列",this::queueEditor));page.addView(button("电脑遥控",()->startActivity(new Intent(this,RemoteActivity.class))));page.addView(button("电脑任务中心",this::showTasks));
        page.addView(text("应用设置",20,Color.WHITE));page.addView(button("连接管理",this::showConnection));page.addView(button("检查客户端更新",()->startActivity(new Intent(this,UpdateActivity.class))));for(int i=0;i<page.getChildCount();i++){View child=page.getChildAt(i);if(child instanceof TextView&&!(child instanceof Button))child.setPadding(0,dp(18),0,dp(8));if(child instanceof Button){Button row=(Button)child;String label=row.getText().toString();String symbol=label.equals("收藏")?"heart":label.equals("想看")?"bookmark":label.contains("更新")?"check":label.contains("连接")?"server":label.contains("统计")?"discover":"library";MediaStyle.icon(row,symbol,false);android.graphics.drawable.Drawable leading=row.getCompoundDrawables()[0];MediaStyle.Symbol trailing=new MediaStyle.Symbol("chevron",MediaStyle.MUTED,false);trailing.setBounds(0,0,dp(16),dp(16));row.setCompoundDrawables(leading,null,trailing,null);row.setGravity(Gravity.START|Gravity.CENTER_VERTICAL);row.setPadding(dp(16),dp(12),dp(12),dp(12));LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.setMargins(0,dp(4),0,dp(4));row.setLayoutParams(lp);}}
        bottomNavigation();
    }
    private void openCollection(boolean watchlist){resetBrowseFilters();mainPage="mine";watchlistOnly=watchlist;favorites=!watchlist;showLibrary();}
    private void browseCategories(){
        LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(dp(16),dp(4),dp(16),dp(4));
        Spinner categories=new Spinner(this);categories.setTag("libraryCategory");categories.setContentDescription("媒体分类");
        String[] labels={"全部媒体","电影","电视剧","VR电影","Fans视频","其他","女演员"},types={"","movie","series","vr","fans","other","actresses"};
        categories.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,labels));int selected=actresses?6:java.util.Arrays.asList(types).indexOf(kind);categories.setSelection(Math.max(0,selected));
        categories.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onNothingSelected(AdapterView<?> parent){}public void onItemSelected(AdapterView<?> parent,View view,int index,long id){String current=actresses?"actresses":kind;if(types[index].equals(current))return;resetBrowseFilters();mainPage="library";actresses=index==6;kind=actresses?"":types[index];showLibrary();}});
        row.addView(categories,new LinearLayout.LayoutParams(0,dp(48),1));catalogCount=text("",12,MUTED);row.addView(catalogCount);Button sort=button("",this::sorting);MediaStyle.quiet(sort,"sort","排序");sort.setVisibility(actresses?View.GONE:View.VISIBLE);row.addView(sort,new LinearLayout.LayoutParams(dp(48),dp(48)));Button more=button("",()->{});MediaStyle.quiet(more,"more","当前列表操作");more.setOnClickListener(this::showListActions);row.addView(more,new LinearLayout.LayoutParams(dp(48),dp(48)));root.addView(row);
    }
    private void showListActions(View anchor){
        PopupMenu menu=new PopupMenu(this,anchor);if(savedList.isEmpty())menu.getMenu().add("保存当前筛选为片单");menu.getMenu().add("随机播放当前列表");menu.getMenu().add("手机播放队列");
        menu.setOnMenuItemClickListener(item->{switch(item.getTitle().toString()){case "保存当前筛选为片单":saveSmartList();break;case "随机播放当前列表":shuffle();break;default:queueEditor();}return true;});menu.show();
    }
    private void showLibrary() {
        generation++;catalogCount=null;mineLanding=false;browseRoot=null;continuePanel=null;detailId=0;renderedDetailId=0;detailScroll=null;browseLoading=null;discoveryTagInput=null;offset=0;restoreOffset=0;restoreScroll=0;browsePositions.clear();browseRecords.clear();base();header(mainPage.equals("home")?"Lumen":discovery?"发现":"媒体库",false);
        boolean home=mainPage.equals("home")&&kind.isEmpty()&&!favorites&&!watchlistOnly&&!dislikedOnly&&!recommended&&!discovery&&!actresses&&query.isEmpty()&&tagFilter.isEmpty()&&actorFilter.isEmpty()&&yearMinFilter.isEmpty()&&yearMaxFilter.isEmpty()&&ratingMinFilter.isEmpty()&&tagsAllFilter.isEmpty()&&tagsAnyFilter.isEmpty()&&tagsNotFilter.isEmpty()&&watchFilter.isEmpty()&&savedList.isEmpty();
        LinearLayout searchRow=new LinearLayout(this);searchRow.setGravity(Gravity.CENTER_VERTICAL);searchRow.setPadding(dp(16),0,dp(16),0);
        EditText search=new EditText(this);search.setTextColor(Color.WHITE);search.setHintTextColor(MUTED);search.setHint(discovery?"按影片名称搜索":actresses?"搜索女演员":"搜索媒体库");search.setContentDescription(discovery?"发现影片名称搜索":actresses?"女演员搜索":"媒体库搜索");search.setSingleLine(true);search.setText(query);search.setImeOptions(EditorInfo.IME_ACTION_SEARCH);
        Runnable applySearch=()->{if(discovery&&discoveryOnline){startDiscoverySearch(search);return;}query=search.getText().toString().trim();if(discovery&&discoveryTagInput!=null)tagFilter=discoveryTagInput.getText().toString().trim();showLibrary();};
        search.setOnEditorActionListener((view,action,event)->{if(action==EditorInfo.IME_ACTION_SEARCH){applySearch.run();return true;}return false;});
        search.setBackground(MediaStyle.surface(this,0xff15212c,0xff2c414f,8));search.setPadding(dp(12),0,dp(8),0);
        searchRow.addView(search,new LinearLayout.LayoutParams(0,dp(48),1));Button searchButton=button("",applySearch);MediaStyle.quiet(searchButton,"search","搜索");searchButton.setContentDescription("搜索");LinearLayout.LayoutParams searchParams=new LinearLayout.LayoutParams(dp(48),dp(48));searchParams.setMargins(dp(6),0,dp(6),0);searchRow.addView(searchButton,searchParams);
        String activeTag=discovery&&discoveryOnline?discoveryResultTag:tagFilter;
        int count=(watchFilter.isEmpty()?0:1)+(savedList.isEmpty()?0:1)+(activeTag.isEmpty()?0:1)+(actorFilter.isEmpty()?0:1)+(yearMinFilter.isEmpty()?0:1)+(yearMaxFilter.isEmpty()?0:1)+(ratingMinFilter.isEmpty()?0:1)+(tagsAllFilter.isEmpty()?0:1)+(tagsAnyFilter.isEmpty()?0:1)+(tagsNotFilter.isEmpty()?0:1)+(favorites?1:0)+(watchlistOnly?1:0)+(dislikedOnly?1:0);
        Button filters=button("筛选"+(count>0?" · "+count:""),this::showFilters);filters.setContentDescription("筛选媒体库");MediaStyle.quiet(filters,"filter","筛选媒体库"+(count>0?"，已选 "+count+" 项":""));searchRow.addView(filters,new LinearLayout.LayoutParams(dp(48),dp(48)));root.addView(searchRow);
        if(!home&&!discovery&&!favorites&&!watchlistOnly&&!recommended&&savedList.isEmpty())browseCategories();
        ScrollView scroll=new ScrollView(this);browseScroll=scroll;scroll.setOnScrollChangeListener((View.OnScrollChangeListener)(v,x,y,oldX,oldY)->imageRequests.prioritizeVisible());content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);content.setPadding(dp(16),dp(10),dp(16),dp(16));scroll.addView(content);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        ChipLayout selectedFilters=new ChipLayout(this);selectedFilters.setTag("activeFilters");selectedFilters.setPadding(0,dp(4),0,dp(8));
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
        if(home){
            continuePanel=new LinearLayout(this);continuePanel.setOrientation(LinearLayout.VERTICAL);content.addView(continuePanel);loadContinue();
            content.addView(button("为我推荐",()->{resetBrowseFilters();mainPage="home";recommended=true;showLibrary();}));
        }
        LinearLayout listHeading=new LinearLayout(this);listHeading.setGravity(Gravity.CENTER_VERTICAL);
        String title=recommended?"为我推荐":discovery?"影片发现":actresses?"女演员墙":favorites?"收藏":watchlistOnly?"想看":!savedList.isEmpty()?savedList:query.isEmpty()?(home?"最近入库":"媒体库"):"搜索结果";
        listHeading.addView(text(title,22,Color.WHITE),new LinearLayout.LayoutParams(0,-2,1));
        if(!actresses){Button listMore=button("",()->{});listMore.setContentDescription("当前列表操作");MediaStyle.icon(listMore,"more",false);listMore.setOnClickListener(this::showListActions);listHeading.addView(listMore,new LinearLayout.LayoutParams(dp(48),dp(48)));if(home||favorites||watchlistOnly||recommended||!savedList.isEmpty())listHeading.addView(button("排序",this::sorting));}
        if(home||discovery||actresses||favorites||watchlistOnly||recommended||!savedList.isEmpty())content.addView(listHeading);
        if(discovery)showDiscoveryTools(search,applySearch);
        posters=new PosterGrid(this);content.addView(posters);bottomNavigation();
        if(actresses){loadActresses();return;}
        if(discovery&&discoveryOnline&&discoveryResultIds==null){content.addView(text(discoverySearchState.equals("running")||discoverySearchState.equals("queued")?"正在搜索站点，完成后显示本次结果。":"输入影片名称或标签，点击“搜索站点”。",15,MUTED));}else loadPage();
        if(discovery&&discoveryOnline&&!discoverySearchTask.isEmpty()&&(discoverySearchState.equals("running")||discoverySearchState.equals("queued")))pollDiscoverySearch(discoverySearchTask,generation);
    }
    private String continueTime(double seconds){long n=(long)Math.max(0,seconds);return String.format(java.util.Locale.ROOT,"%d:%02d:%02d",n/3600,n/60%60,n%60);}
    private void loadContinue() {
        final LinearLayout panel=continuePanel;if(panel==null)return;
        request(()->api.get("/api/continue?limit=24"),result->{
            if(panel!=continuePanel)return;panel.removeAllViews();
            JSONArray items=result.optJSONArray("items");if(items==null||items.length()==0){panel.setVisibility(View.GONE);return;}
            panel.setVisibility(View.VISIBLE);panel.addView(text("继续观看",22,Color.WHITE));
            HorizontalScrollView scroll=new HorizontalScrollView(this);scroll.setHorizontalScrollBarEnabled(false);LinearLayout row=new LinearLayout(this);scroll.addView(row);panel.addView(scroll);
            for(int i=0;i<items.length();i++){
                JSONObject work=items.getJSONObject(i),resume=work.optJSONObject("resume");if(resume==null)continue;
                long workId=work.optLong("id"),fileId=resume.optLong("file_id");
                LinearLayout card=new LinearLayout(this);card.setOrientation(LinearLayout.VERTICAL);card.setPadding(dp(10),dp(6),dp(10),dp(8));card.setBackground(MediaStyle.surface(this,0xff15212c,0xff2c414f,8));
                LinearLayout.LayoutParams size=new LinearLayout.LayoutParams(dp(Math.min(336,Math.max(260,getResources().getConfiguration().screenWidthDp-52))),-2);size.setMargins(0,0,dp(12),dp(12));row.addView(card,size);
                ImageView cover=new ImageView(this);cover.setScaleType(ImageView.ScaleType.CENTER_CROP);card.addView(cover,new LinearLayout.LayoutParams(-1,dp(130)));loadImage(cover,work.optString("cover",""));
                TextView title=text(work.optString("title"),17,Color.WHITE);title.setMaxLines(2);card.addView(title);
                String filename=resume.optString("name",resume.optString("file_name",resume.optString("label")));
                TextView description=text(filename,12,MUTED);description.setTag("continueIdentity:"+fileId);description.setMaxLines(2);description.setEllipsize(android.text.TextUtils.TruncateAt.END);description.setOnClickListener(v->new AlertDialog.Builder(this).setTitle(work.optString("title")).setMessage(resume.optString("label",filename)).setPositiveButton("关闭",null).show());card.addView(description);
                double duration=resume.optDouble("duration",0),position=resume.optDouble("position",0);
                TextView times=text("已看 "+continueTime(position)+(duration>0?" / "+continueTime(duration)+"  ·  剩余 "+continueTime(Math.max(0,duration-position)):" · 时长未知"),12,0xffbfe8ee);times.setTag("continueTime:"+fileId);card.addView(times);
                if(duration>0){ProgressBar progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);progress.setMax(1000);progress.setProgress((int)Math.max(0,Math.min(1000,position/duration*1000)));progress.setContentDescription("观看进度");card.addView(progress,new LinearLayout.LayoutParams(-1,dp(4)));}
                Button play=button(position>0?"继续播放":"播放下一集",()->{Intent intent=new Intent(this,PlayerActivity.class);intent.putExtra("work_id",workId);intent.putExtra("file_id",fileId);intent.putExtra("queue",false);startActivity(intent);});
                play.setContentDescription("续播："+work.optString("title")+" · "+resume.optString("label"));card.addView(play);cover.setOnClickListener(view->openDetail(workId));title.setOnClickListener(view->openDetail(workId));
            }
        },error->{if(panel!=continuePanel)return;panel.removeAllViews();panel.setVisibility(View.VISIBLE);panel.addView(button("续播读取失败，点击重试",this::loadContinue));});
    }
    private String listPath() {
        String path=recommended?"/api/recommendations?":discovery?"/api/discover?":"/api/works?";
        boolean onlineResult=discovery&&discoveryOnline;
        String ids="";if(onlineResult){java.util.ArrayList<String> selected=new java.util.ArrayList<>();if(discoveryResultIds!=null)for(int i=0;i<discoveryResultIds.length();i++)selected.add(Long.toString(discoveryResultIds.optLong(i)));ids="&ids="+android.text.TextUtils.join(",",selected);}
        return path+"offset="+offset+"&limit=30&kind="+kind+"&favorite="+favorites+"&watchlist="+watchlistOnly+(dislikedOnly?"&disliked=true":"")+"&q="+android.net.Uri.encode(onlineResult?"":query)+(discovery?"&tag_q=":"&tag=")+android.net.Uri.encode(onlineResult?discoveryResultTag:tagFilter)+"&actor="+android.net.Uri.encode(actorFilter)+"&year_min="+android.net.Uri.encode(discovery?"":yearMinFilter)+"&year_max="+android.net.Uri.encode(discovery?"":yearMaxFilter)+"&rating_min="+android.net.Uri.encode(discovery?"":ratingMinFilter)+"&tags_all="+android.net.Uri.encode(discovery?"":tagsAllFilter)+"&tags_any="+android.net.Uri.encode(tagsAnyFilter)+"&tags_not="+android.net.Uri.encode(tagsNotFilter)+"&sort="+(discovery?discoverySort:sortField)+"&direction="+((discovery?discoveryDescending:sortDescending)?"desc":"asc")+"&watch_state="+watchFilter+"&list="+android.net.Uri.encode(savedList)+ids;
    }
    private void showDiscoveryTools(EditText search,Runnable applySearch){
        LinearLayout panel=new LinearLayout(this);panel.setOrientation(LinearLayout.VERTICAL);panel.setPadding(dp(12),dp(6),dp(12),dp(12));
        panel.setBackground(MediaStyle.surface(this,0xff101b24,0xff30303a,10));
        Spinner scope=new Spinner(this);scope.setTag("discoveryScope");scope.setContentDescription("发现搜索范围");scope.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"筛选已发现资料","在线搜索站点"}));scope.setSelection(discoveryOnline?1:0);
        scope.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onNothingSelected(AdapterView<?> parent){}public void onItemSelected(AdapterView<?> parent,View view,int position,long id){
            boolean online=position==1;if(online==discoveryOnline)return;query=search.getText().toString().trim();if(discoveryTagInput!=null)tagFilter=discoveryTagInput.getText().toString().trim();if(!online)clearDiscoverySearch();discoveryOnline=online;showLibrary();
        }});panel.addView(scope,new LinearLayout.LayoutParams(-1,dp(48)));
        TextView label=text("标签搜索",13,MUTED);panel.addView(label);
        AutoCompleteTextView tag=new SearchDropdown(this);discoveryTagInput=tag;
        tag.setTag("discoveryTag");tag.setContentDescription("发现影片标签搜索");tag.setSingleLine(true);tag.setTextColor(Color.WHITE);tag.setHintTextColor(MUTED);
        tag.setHint("输入标签搜索或下拉选择");tag.setText(tagFilter);tag.setImeOptions(EditorInfo.IME_ACTION_SEARCH);
        tag.setPadding(dp(12),0,dp(8),0);tag.setBackground(MediaStyle.surface(this,0xff13212c,0xff314652,8));
        tag.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_dropdown_item_1line));
        tag.setOnItemClickListener((parent,view,position,id)->applySearch.run());
        tag.setOnEditorActionListener((view,action,event)->{if(action==EditorInfo.IME_ACTION_SEARCH){applySearch.run();return true;}return false;});
        LinearLayout tagRow=new LinearLayout(this);tagRow.addView(tag,new LinearLayout.LayoutParams(0,dp(48),1));
        Button dropdown=button("⌄",()->{tag.requestFocus();tag.showDropDown();});dropdown.setContentDescription("选择发现标签");tagRow.addView(dropdown,new LinearLayout.LayoutParams(dp(48),dp(48)));
        Button apply=button(discoveryOnline?"搜索站点":"应用",applySearch);apply.setTag("discoverySearch");apply.setContentDescription(discoveryOnline?"搜索站点":"应用发现名称与标签搜索");tagRow.addView(apply,new LinearLayout.LayoutParams(dp(discoveryOnline?96:64),dp(48)));panel.addView(tagRow);
        if(discoveryOnline)showDiscoveryProviders(panel,apply);
        panel.addView(text("排序",13,MUTED));LinearLayout sortRow=new LinearLayout(this);
        Spinner order=new Spinner(this);order.setTag("discoverySort");order.setContentDescription("发现影片排序字段");
        order.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,DISCOVERY_SORT_NAMES));
        order.setSelection(Math.max(0,java.util.Arrays.asList(DISCOVERY_SORT_KEYS).indexOf(discoverySort)));
        order.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onNothingSelected(AdapterView<?> parent){}public void onItemSelected(AdapterView<?> parent,View view,int position,long id){
            if(position<0||position>=DISCOVERY_SORT_KEYS.length||DISCOVERY_SORT_KEYS[position].equals(discoverySort))return;
            discoverySort=DISCOVERY_SORT_KEYS[position];saveDiscoverySort();if(discoveryOnline)showLibrary();else applySearch.run();
        }});
        sortRow.addView(order,new LinearLayout.LayoutParams(0,dp(48),1));
        Button direction=button(discoveryDescending?"降序 ↓":"升序 ↑",()->{discoveryDescending=!discoveryDescending;saveDiscoverySort();if(discoveryOnline)showLibrary();else applySearch.run();});
        direction.setTag("discoveryDirection");direction.setContentDescription("切换发现排序方向");sortRow.addView(direction,new LinearLayout.LayoutParams(dp(96),dp(48)));panel.addView(sortRow);
        LinearLayout.LayoutParams spacing=new LinearLayout.LayoutParams(-1,-2);spacing.setMargins(0,dp(2),0,dp(14));content.addView(panel,spacing);
        loadDiscoveryTags(tag);
    }
    private void loadDiscoveryTags(AutoCompleteTextView target){
        request(()->api.get("/api/filters?discover=true&kind="+android.net.Uri.encode(kind)),options->{
            if(target!=discoveryTagInput)return;
            JSONArray tags=options.optJSONArray("tags");java.util.ArrayList<String> names=new java.util.ArrayList<>();
            if(tags!=null)for(int i=0;i<tags.length();i++)names.add(tags.optString(i));
            target.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_dropdown_item_1line,names));
        });
    }
    private void saveDiscoverySort(){getSharedPreferences("discovery",0).edit().putString("sort",discoverySort).putBoolean("descending",discoveryDescending).apply();}
    private void clearDiscoverySearch(){
        discoverySubmission++;discoveryOnline=false;discoverySearchTask="";discoverySearchState="";discoverySearchMessage="";discoverySearchErrors="";discoveryResultIds=null;discoveryResultTag="";
    }
    private boolean discoverySearchBusy(){return discoverySearchState.equals("queued")||discoverySearchState.equals("running");}
    private void showDiscoveryProviders(LinearLayout panel,Button apply){
        panel.addView(text("搜索来源",13,MUTED));LinearLayout sourceRow=new LinearLayout(this);Spinner sources=new Spinner(this);sources.setTag("discoveryProvider");sources.setContentDescription("在线搜索来源");sourceRow.addView(sources,new LinearLayout.LayoutParams(0,dp(48),1));
        Button refresh=button("↻",()->{});refresh.setContentDescription("刷新搜索来源");sourceRow.addView(refresh,new LinearLayout.LayoutParams(dp(48),dp(48)));panel.addView(sourceRow);
        TextView capability=text("正在读取可用站点…",12,MUTED);capability.setTag("discoveryProviderHint");panel.addView(capability);
        TextView status=text(discoverySearchMessage+(discoverySearchErrors.isEmpty()?"":"\n"+discoverySearchErrors),13,MUTED);status.setTag("discoverySearchStatus");panel.addView(status);
        apply.setEnabled(discoveryProvidersLoaded&&discoveryProviders.length()>0&&!discoverySearchBusy());
        Runnable populate=()->{
            java.util.ArrayList<String> labels=new java.util.ArrayList<>();labels.add("全部可用站点");int selected=0;
            for(int i=0;i<discoveryProviders.length();i++){
                JSONObject provider=discoveryProviders.optJSONObject(i);if(provider==null)continue;
                labels.add(provider.optString("name",provider.optString("id"))+(provider.optBoolean("supports_tags")?" · 名称和标签":" · 仅名称"));
                if(provider.optString("id").equals(discoveryProvider))selected=i+1;
            }
            sources.setOnItemSelectedListener(null);sources.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,labels));sources.setSelection(selected);
            if(selected==0)discoveryProvider="";
            capability.setText(discoveryProviders.length()==0?"暂无可用站点，请在电脑端启用支持搜索的插件。":discoveryProviderHint());
            sources.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onNothingSelected(AdapterView<?> parent){}public void onItemSelected(AdapterView<?> parent,View view,int position,long id){
                discoveryProvider=position==0?"":discoveryProviders.optJSONObject(position-1).optString("id");capability.setText(discoveryProviderHint());
            }});
            apply.setEnabled(discoveryProviders.length()>0&&!discoverySearchBusy());
        };
        if(discoveryProvidersLoaded)populate.run();
        Runnable reload=()->request(()->api.get("/api/discovery/providers"),result->{
            discoveryProviders=result.optJSONArray("items");if(discoveryProviders==null)discoveryProviders=new JSONArray();discoveryProvidersLoaded=true;populate.run();
        },error->{capability.setText("来源读取失败，点击右侧刷新按钮重试："+error);apply.setEnabled(discoveryProvidersLoaded&&discoveryProviders.length()>0&&!discoverySearchBusy());});
        refresh.setOnClickListener(view->reload.run());reload.run();
    }
    private String discoveryProviderHint(){
        if(discoveryProvider.isEmpty())return "名称和标签同时填写时，只搜索声明支持标签的站点；不支持的站点会显示原因。";
        for(int i=0;i<discoveryProviders.length();i++){
            JSONObject provider=discoveryProviders.optJSONObject(i);if(provider!=null&&provider.optString("id").equals(discoveryProvider))return provider.optBoolean("supports_tags")?"此站点支持名称与标签组合搜索。":"此站点仅支持名称搜索；标签搜索请更换来源。";
        }
        return "请选择可用站点。";
    }
    private void startDiscoverySearch(EditText search){
        if(discoverySearchBusy())return;
        query=search.getText().toString().trim();tagFilter=discoveryTagInput==null?"":discoveryTagInput.getText().toString().trim();
        if(query.isEmpty()&&tagFilter.isEmpty()){message("请输入影片名称或标签");return;}
        if(!discoveryProvidersLoaded||discoveryProviders.length()==0){message("请先选择可用的搜索站点");return;}
        if(!tagFilter.isEmpty()&&!discoveryProvider.isEmpty())for(int i=0;i<discoveryProviders.length();i++){
            JSONObject provider=discoveryProviders.optJSONObject(i);
            if(provider!=null&&provider.optString("id").equals(discoveryProvider)&&!provider.optBoolean("supports_tags")){
                discoverySearchTask="";discoverySearchState="failed";discoveryResultIds=null;discoverySearchMessage="该站点不支持标签搜索，请更换来源或清空标签。";discoverySearchErrors="";showLibrary();return;
            }
        }
        // A new site search uses only its explicit name/tag/provider inputs;
        // old local-library conditions must not silently discard site matches.
        kind="";actorFilter="";yearMinFilter="";yearMaxFilter="";ratingMinFilter="";tagsAllFilter="";tagsAnyFilter="";tagsNotFilter="";favorites=false;watchFilter="";savedList="";discoveryResultTag="";
        final JSONObject payload=new JSONObject();
        try{payload.put("query",query).put("tag",tagFilter).put("plugin",discoveryProvider);}catch(Exception error){message(error.getMessage());return;}
        savedList="";discoveryResultIds=null;discoverySearchTask="";discoverySearchState="queued";discoverySearchMessage="正在提交站点搜索…";discoverySearchErrors="";showLibrary();
        final int submission=++discoverySubmission;final Api client=api;
        network.execute(()->{
            try{
                String task=client.post("/api/discovery/search",payload).getString("task_id");
                runOnUiThread(()->{if(isDestroyed()||submission!=discoverySubmission||api!=client)return;
                    discoverySearchTask=task;discoverySearchState="queued";discoverySearchMessage="站点搜索已加入队列…";
                    if(discovery&&discoveryOnline&&detailId==0)showLibrary();
                });
            }catch(Exception error){runOnUiThread(()->{if(isDestroyed()||submission!=discoverySubmission||api!=client)return;
                discoverySearchState="failed";discoverySearchMessage="搜索提交失败，可重新搜索。";discoverySearchErrors=error.getMessage()==null?error.toString():error.getMessage();
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
                    discoverySearchMessage="本次找到 "+discoveryResultIds.length()+" 部影片，已加入发现资料。";
                }else{
                    discoveryResultIds=null;discoverySearchMessage=phase.equals("cancelled")?"搜索已取消，可重新搜索。":"站点搜索失败，可更换条件或来源重试。";
                    if(!state.isNull("error")&&!state.optString("error").isEmpty())discoverySearchErrors=state.optString("error")+(discoverySearchErrors.isEmpty()?"":"\n"+discoverySearchErrors);
                }
                showLibrary();return;
            }
            discoverySearchState=phase;discoverySearchMessage=phase.equals("queued")?"正在等待搜索…":"正在搜索站点…";
            TextView status=root.findViewWithTag("discoverySearchStatus");if(status!=null)status.setText(discoverySearchMessage);
            downloadUpdates.postDelayed(()->pollDiscoverySearch(task,ticket),750);
        },error->{
            discoverySearchState="interrupted";discoverySearchMessage="暂时无法读取搜索进度，可重新搜索。";discoverySearchErrors=error;showLibrary();
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
        chip.setBackground(MediaStyle.surface(this,0xff18313a,0xff315563,20));chip.setTextColor(0xffbfe8f6);MediaStyle.icon(chip,"close",false);chip.setContentDescription("移除筛选："+text);return chip;
    }
    private AutoCompleteTextView filterInput(LinearLayout form,String label,String value){
        form.addView(text(label,13,MUTED));
        AutoCompleteTextView input=new SearchDropdown(this);input.setSingleLine(true);input.setTextColor(Color.WHITE);input.setHintTextColor(MUTED);
        input.setHint("输入搜索或下拉选择");input.setText(value);MediaStyle.field(input);
        LinearLayout row=new LinearLayout(this);row.addView(input,new LinearLayout.LayoutParams(0,dp(48),1));
        row.addView(button("⌄",()->{input.requestFocus();input.showDropDown();}),new LinearLayout.LayoutParams(dp(44),dp(48)));form.addView(row);
        return input;
    }
    private void showFilters(){
        LinearLayout form=new LinearLayout(this);form.setOrientation(LinearLayout.VERTICAL);form.setPadding(dp(20),dp(12),dp(20),dp(12));
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
        LinearLayout preferences=new LinearLayout(this);preferences.setOrientation(LinearLayout.HORIZONTAL);
        Button wanted=button("想看",()->{});final boolean[] onlyWanted={watchlistOnly};MediaStyle.icon(wanted,"bookmark",onlyWanted[0]);MediaStyle.button(wanted,false,onlyWanted[0],false);
        wanted.setOnClickListener(v->{onlyWanted[0]=!onlyWanted[0];MediaStyle.button(wanted,false,onlyWanted[0],false);MediaStyle.icon(wanted,"bookmark",onlyWanted[0]);});
        for(Button option:new Button[]{collection,wanted,disliked}){option.setTextSize(12);option.setPadding(dp(4),dp(6),dp(4),dp(6));LinearLayout.LayoutParams cell=new LinearLayout.LayoutParams(0,-2,1);cell.setMargins(dp(2),0,dp(2),dp(10));preferences.addView(option,cell);}form.addView(preferences);
        AutoCompleteTextView tag=filterInput(form,"标签",discovery&&discoveryOnline?discoveryResultTag:tagFilter),actor=filterInput(form,"演员",actorFilter),multiTag=filterInput(form,"多个标签（逗号分隔，需全部包含）",tagsAllFilter);
        AutoCompleteTextView anyTags=filterInput(form,"包含任一标签",tagsAnyFilter),notTags=filterInput(form,"排除标签／不想看的类型",tagsNotFilter);
        AutoCompleteTextView yearFrom=filterInput(form,"年份从",yearMinFilter),yearTo=filterInput(form,"年份到",yearMaxFilter);
        yearFrom.setTag("filterYearFrom");yearTo.setTag("filterYearTo");
        yearFrom.setInputType(InputType.TYPE_CLASS_NUMBER);yearTo.setInputType(InputType.TYPE_CLASS_NUMBER);
        AutoCompleteTextView rating=filterInput(form,"最低评分（0–10）",ratingMinFilter);rating.setInputType(InputType.TYPE_CLASS_NUMBER);
        android.widget.Spinner watching=new android.widget.Spinner(this);String[] states={"","unwatched","progress","completed"};
        watching.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"全部观看状态","未开始","观看中","已完成"}));
        for(int i=0;i<states.length;i++)if(states[i].equals(watchFilter))watching.setSelection(i);watching.setVisibility(View.GONE);form.addView(watching);
        LinearLayout watchRow=new LinearLayout(this);watchRow.setOrientation(LinearLayout.HORIZONTAL);watchRow.setTag("watchSegments");
        String[] watchLabels={"全部","未看","观看中","已看完"};
        Runnable refreshWatch=()->{for(int i=0;i<watchRow.getChildCount();i++){Button option=(Button)watchRow.getChildAt(i);MediaStyle.button(option,false,watching.getSelectedItemPosition()==i,false);option.setTextSize(12);option.setPadding(dp(3),dp(6),dp(3),dp(6));}};
        for(int i=0;i<watchLabels.length;i++){final int index=i;Button option=button(watchLabels[i],()->{watching.setSelection(index);refreshWatch.run();});LinearLayout.LayoutParams cell=new LinearLayout.LayoutParams(0,-2,1);cell.setMargins(dp(2),0,dp(2),dp(8));watchRow.addView(option,cell);}refreshWatch.run();form.addView(watchRow,0);form.addView(text("观看状态",14,MediaStyle.TEXT),0);
        LinearLayout yearPair=new LinearLayout(this);yearPair.setOrientation(LinearLayout.HORIZONTAL);yearPair.setPadding(0,0,0,dp(8));
        for(AutoCompleteTextView input:new AutoCompleteTextView[]{yearFrom,yearTo}){View parent=(View)input.getParent();int index=form.indexOfChild(parent);View label=form.getChildAt(index-1);form.removeView(label);form.removeView(parent);((android.view.ViewGroup)parent).removeView(input);LinearLayout cell=new LinearLayout(this);cell.setOrientation(LinearLayout.VERTICAL);cell.addView(label);cell.addView(input,new LinearLayout.LayoutParams(-1,dp(48)));LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,-2,1);lp.setMargins(input==yearFrom?0:dp(6),0,input==yearFrom?dp(6):0,0);yearPair.addView(cell,lp);}form.addView(yearPair);
        LinearLayout advanced=new LinearLayout(this);advanced.setOrientation(LinearLayout.VERTICAL);advanced.setTag("advancedFilterFields");
        for(AutoCompleteTextView input:new AutoCompleteTextView[]{multiTag,anyTags,notTags,rating}){View parent=(View)input.getParent();int index=form.indexOfChild(parent);View label=form.getChildAt(index-1);form.removeView(label);form.removeView(parent);advanced.addView(label);advanced.addView(parent);}
        advanced.setVisibility(tagsAllFilter.isEmpty()&&tagsAnyFilter.isEmpty()&&tagsNotFilter.isEmpty()&&ratingMinFilter.isEmpty()?View.GONE:View.VISIBLE);
        Button moreFilters=button("更多条件 · 标签组合、排除、评分",()->advanced.setVisibility(advanced.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE));form.addView(moreFilters);form.addView(advanced);
        TextView status=text("正在读取筛选选项…",13,MUTED);form.addView(status);
        ScrollView scroll=new ScrollView(this);scroll.addView(form);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("筛选媒体库").setView(scroll)
            .setPositiveButton("应用",null).setNegativeButton("取消",null).setNeutralButton("重置",(d,which)->{tagFilter="";actorFilter="";yearMinFilter="";yearMaxFilter="";ratingMinFilter="";tagsAllFilter="";favorites=false;showLibrary();}).create();
        dialog.show();MediaStyle.sheet(dialog);
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view->{
            String from=yearFrom.getText().toString().trim(),to=yearTo.getText().toString().trim(),score=rating.getText().toString().trim();
            if(!from.isEmpty()&&(!from.matches("[0-9]{4}")||Integer.parseInt(from)<1800||Integer.parseInt(from)>2200)){yearFrom.setError("请输入 1800–2200 的年份");return;}
            if(!to.isEmpty()&&(!to.matches("[0-9]{4}")||Integer.parseInt(to)<1800||Integer.parseInt(to)>2200)){yearTo.setError("请输入 1800–2200 的年份");return;}
            if(!score.isEmpty()&&(!score.matches("[0-9]{1,2}")||Integer.parseInt(score)>10)){rating.setError("评分范围 0–10");return;}
            if(!from.isEmpty()&&!to.isEmpty()&&Integer.parseInt(from)>Integer.parseInt(to)){yearFrom.setError("起始年份不能晚于结束");return;}
            if(discovery&&discoveryOnline)discoveryResultTag=tag.getText().toString().trim();else tagFilter=tag.getText().toString().trim();
            actorFilter=actor.getText().toString().trim();tagsAllFilter=multiTag.getText().toString().trim();tagsAnyFilter=anyTags.getText().toString().trim();tagsNotFilter=notTags.getText().toString().trim();
            yearMinFilter=from;yearMaxFilter=to;ratingMinFilter=score;favorites=onlyFavorites[0];dislikedOnly=onlyDisliked[0];watchlistOnly=onlyWanted[0];watchFilter=states[watching.getSelectedItemPosition()];dialog.dismiss();showLibrary();
        });
        android.view.Window sheet=dialog.getWindow();if(sheet!=null){sheet.setBackgroundDrawable(MediaStyle.surface(this,0xff131e28,0xff2c414f,18));sheet.setGravity(Gravity.BOTTOM);sheet.setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);sheet.setLayout(-1,-2);View sheetView=sheet.getDecorView();sheetView.post(()->{int available=getResources().getDisplayMetrics().heightPixels-dp(48);if(sheetView.getHeight()>available)sheet.setLayout(-1,available);});}
        dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(view->{
            tag.setText("");actor.setText("");multiTag.setText("");anyTags.setText("");notTags.setText("");yearFrom.setText("");yearTo.setText("");rating.setText("");watching.setSelection(0);refreshWatch.run();onlyWanted[0]=false;MediaStyle.button(wanted,false,false,false);MediaStyle.icon(wanted,"bookmark",false);onlyFavorites[0]=false;onlyDisliked[0]=false;disliked.setText("不喜欢");MediaStyle.icon(disliked,"ban",false);MediaStyle.button(disliked,false,false,false);
            collection.setText("已收藏");MediaStyle.icon(collection,"heart",false);MediaStyle.button(collection,false,false,true);
        });
        MediaStyle.button(dialog.getButton(AlertDialog.BUTTON_POSITIVE),true,false,false);
        MediaStyle.button(dialog.getButton(AlertDialog.BUTTON_NEGATIVE),false,false,false);MediaStyle.button(dialog.getButton(AlertDialog.BUTTON_NEUTRAL),false,false,false);
        request(()->api.get("/api/filters?kind="+android.net.Uri.encode(kind)+"&discover="+discovery),options->{
            if(!dialog.isShowing())return;
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
        TextView loading=text("正在读取媒体库…",14,MUTED);browseLoading=loading;content.addView(loading);String path=listPath();
        request(()->api.get(path),result->{
            content.removeView(loading);if(browseLoading==loading)browseLoading=null;JSONArray items=result.getJSONArray("items");int total=result.optInt("total");if(catalogCount!=null)catalogCount.setText(total+" 部");
            if(total==0)content.addView(text(discovery?(discoveryOnline?"本次站点搜索没有匹配结果，可更换名称、标签或来源重试。":"暂无匹配的发现资料，可调整名称、标签或切换在线搜索站点。"):"暂无内容。请先在电脑端导入媒体，或调整搜索条件。",16,MUTED));
            int columns=Math.max(2,getResources().getConfiguration().screenWidthDp/165);
            int width=(getResources().getDisplayMetrics().widthPixels-dp(32))/columns;
            width=(getResources().getDisplayMetrics().widthPixels-dp(32)-(columns-1)*dp(6))/columns;
            for(int i=0;i<items.length();i++) {
                JSONObject work=items.getJSONObject(i);long id=work.getLong("id");browseRecords.put(id,work);browsePositions.put(id,offset+i);
                LinearLayout card=new LinearLayout(this);card.setTag("card:"+id);card.setOrientation(LinearLayout.VERTICAL);card.setPadding(0,dp(4),0,dp(10));
                FrameLayout cover=new FrameLayout(this);cover.setBackground(MediaStyle.surface(this,0xff172a35,0,12));cover.setClipToOutline(true);
                ImageView poster=new ImageView(this);poster.setScaleType(ImageView.ScaleType.CENTER_CROP);cover.addView(poster,new FrameLayout.LayoutParams(-1,-1));
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
            int columns=Math.max(2,getResources().getConfiguration().screenWidthDp/165);
            int width=(getResources().getDisplayMetrics().widthPixels-dp(32)-(columns-1)*dp(6))/columns;
            for(int i=0;i<items.length();i++){
                JSONObject actor=items.getJSONObject(i);
                LinearLayout card=new LinearLayout(this);card.setOrientation(LinearLayout.VERTICAL);card.setPadding(0,dp(4),0,dp(10));
                FrameLayout cover=new FrameLayout(this);cover.setBackground(MediaStyle.surface(this,0xff172a35,0,12));cover.setClipToOutline(true);
                ImageView photo=new ImageView(this);photo.setScaleType(ImageView.ScaleType.CENTER_CROP);cover.addView(photo,new FrameLayout.LayoutParams(-1,-1));
                card.addView(cover,new LinearLayout.LayoutParams(-1,(int)(width*1.5)));loadImage(photo,actor.optString("photo",""));
                TextView name=text(actor.optString("name"),15,Color.WHITE);name.setMaxLines(1);name.setEllipsize(android.text.TextUtils.TruncateAt.END);card.addView(name);
                String average=actor.isNull("average")?"暂无评分":"均分 "+String.format(java.util.Locale.ROOT,"%.1f",actor.optDouble("average"));
                card.addView(text(actor.optInt("count")+" 部 · "+average+" · 已评分 "+actor.optInt("rated"),12,MUTED));
                card.setOnClickListener(view->{actorFilter=actor.optString("name");actresses=false;kind="movie";savedList="";query="";navigationHistory.clear();showLibrary();});
                posters.addView(card,new android.view.ViewGroup.LayoutParams(width,-2));
            }
        });
    }
    private void loadImage(ImageView view,String path) {
        if(view.getBackground()==null)view.setBackground(new MediaStyle.ArtworkPlaceholder());
        if(api!=null)imageRequests.load(api,view,path);
    }
    private void openDetail(long id) {
        if(detailId==0)browseRoot=root;
        generation++;detailId=id;
        request(()->api.get("/api/works/"+id),this::renderDetail);
    }
    private void renderDetail(JSONObject work) throws Exception {
        int previousScroll=renderedDetailId==work.optLong("id")&&detailScroll!=null?detailScroll.getScrollY():0;
        detail=work;detailId=work.getLong("id");renderedDetailId=detailId;base();header("详情",true);
        ScrollView scroll=new ScrollView(this);LinearLayout page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);page.setPadding(dp(20),0,dp(20),dp(24));scroll.addView(page);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        detailScroll=scroll;scroll.post(()->scroll.scrollTo(0,previousScroll));
        LinearLayout hero=new LinearLayout(this);hero.setGravity(Gravity.TOP);hero.setPadding(0,dp(8),0,dp(16));
        ImageView poster=new ImageView(this);poster.setScaleType(ImageView.ScaleType.FIT_CENTER);poster.setBackground(MediaStyle.surface(this,0xff101b24,0,6));poster.setClipToOutline(true);poster.setContentDescription("海报："+work.optString("title"));
        hero.addView(poster,new LinearLayout.LayoutParams(dp(120),dp(180)));loadImage(poster,work.optString("cover",""));
        String coverPath=work.optString("cover","");
        poster.setContentDescription("放大封面："+work.optString("title"));
        poster.setOnClickListener(view->{if(!coverPath.isEmpty()&&!coverPath.equals("null"))showGallery(new JSONArray().put(coverPath),0);else message("此影片暂无封面");});
        LinearLayout info=new LinearLayout(this);info.setOrientation(LinearLayout.VERTICAL);info.setPadding(dp(16),0,0,0);
        TextView title=text(work.optString("title"),24,Color.WHITE);title.setMaxLines(4);title.setEllipsize(android.text.TextUtils.TruncateAt.END);title.setContentDescription(work.optString("title"));
        title.setOnClickListener(view->title.setMaxLines(title.getMaxLines()==4?Integer.MAX_VALUE:4));info.addView(title);
        String category=work.optString("kind").equals("series")?"电视剧":work.optString("kind").equals("vr")?"VR 电影":work.optString("kind").equals("fans")?"Fans视频":work.optString("kind").equals("movie")?"电影":"视频";
        info.addView(text((work.isNull("year")?"":work.optString("year")+"  ·  ")+category,14,MUTED));
        info.addView(text(work.optInt("file_count")==0?"未入库":work.optInt("file_count")+" 个视频",13,MUTED));
        if(!work.isNull("community_rating"))info.addView(text("★ "+String.format(java.util.Locale.ROOT,"%.1f",work.optDouble("community_rating"))+"  来源评分",14,0xffe7c567));
        hero.addView(info,new LinearLayout.LayoutParams(0,-2,1));page.addView(hero);
        JSONObject resume=work.optJSONObject("resume");
        Button play=button(resume!=null&&resume.optDouble("position",work.optDouble("position"))>0||work.optDouble("position")>0?"继续播放":"播放",()->startPlayer(work.optLong("resume_file_id"),false));
        play.setTag("detailPlay");MediaStyle.button(play,true,false,false);MediaStyle.icon(play,"play",true);play.setMinHeight(dp(52));play.setEnabled(work.optInt("file_count")>0);page.addView(play,new LinearLayout.LayoutParams(-1,-2));
        if(resume!=null&&!resume.optString("label").isEmpty()){TextView resumeInfo=text(resume.optString("label"),13,MUTED);resumeInfo.setTag("detailResumeInfo");page.addView(resumeInfo);}
        ChipLayout personal=new ChipLayout(this);personal.setPadding(0,dp(12),0,dp(12));
        personal.addView(markButton(work,"favorite",false));personal.addView(markButton(work,"watchlist",false));
        Button score=button(work.isNull("rating")?"评分":work.optInt("rating")+" 分",()->{
            String[] scores={"清除评分","1 分","2 分","3 分","4 分","5 分","6 分","7 分","8 分","9 分","10 分"};
            new AlertDialog.Builder(this).setTitle("我的评分").setSingleChoiceItems(scores,work.optInt("rating",0),(dialog,index)->{dialog.dismiss();personal("rating",index==0?JSONObject.NULL:index);}).setNegativeButton("取消",null).show();
        });score.setContentDescription("我的评分");score.setTag("rating:"+work.optLong("id"));MediaStyle.icon(score,"star",!work.isNull("rating"));personal.addView(score);page.addView(personal);
        LinearLayout metadataSection=new LinearLayout(this);metadataSection.setOrientation(LinearLayout.VERTICAL);
        JSONArray tags=work.optJSONArray("tags");JSONArray actors=work.optJSONArray("actors");
        ChipLayout metadata=new ChipLayout(this);metadata.setPadding(0,0,0,dp(12));
        if(tags!=null)for(int i=0;i<tags.length();i++){
            String tag=tags.optString(i);metadata.addView(button(tag,()->filterMetadata("tag",tag)));
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
                face.setOnLongClickListener(view->{String credit=person.optString("photo_attribution","")+"\n"+person.optString("photo_license","")+"\n"+person.optString("photo_page",person.optString("photo_source_url",""));new AlertDialog.Builder(this).setTitle(actor+" · 头像来源 / 许可").setMessage(credit.trim().isEmpty()?"来源未提供署名资料":credit.trim()).setPositiveButton("关闭",null).show();return true;});
                Button actorName=button(actor,()->filterMetadata("actor",actor));actorName.setTag("actorName:"+actor);personCard.addView(actorName,new LinearLayout.LayoutParams(dp(104),-2));cast.addView(personCard);
            }else cast.addView(button(actor,()->filterMetadata("actor",actor)));
        }
        if(cast.getChildCount()>0)metadataSection.addView(cast);
        TextView overview=text(work.optString("overview","暂无简介"),15,MUTED);overview.setTag("detailOverview");overview.setMaxLines(4);overview.setEllipsize(android.text.TextUtils.TruncateAt.END);overview.setContentDescription("简介，点击展开或收起");overview.setOnClickListener(v->overview.setMaxLines(overview.getMaxLines()==4?Integer.MAX_VALUE:4));metadataSection.addView(overview);
        JSONArray files=work.getJSONArray("files");page.addView(text(work.optString("kind").equals("series")?"季与集":work.optString("kind").equals("fans")?"作者视频":"视频文件",21,Color.WHITE));
        LinearLayout episodes=new LinearLayout(this);episodes.setOrientation(LinearLayout.VERTICAL);
        android.widget.Spinner seasons=new android.widget.Spinner(this);java.util.ArrayList<Integer> seasonValues=new java.util.ArrayList<>();seasonValues.add(-1);
        java.util.TreeSet<Integer> available=new java.util.TreeSet<>();for(int j=0;j<files.length();j++)available.add(files.getJSONObject(j).optInt("season",1));seasonValues.addAll(available);
        java.util.ArrayList<String> seasonNames=new java.util.ArrayList<>();seasonNames.add("全部季");for(int j=1;j<seasonValues.size();j++)seasonNames.add(seasonValues.get(j)==0?"特别篇":"第 "+seasonValues.get(j)+" 季");
        seasons.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,seasonNames));if(work.optString("kind").equals("series"))page.addView(seasons);page.addView(episodes);
        seasons.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener(){public void onNothingSelected(android.widget.AdapterView<?> p){}public void onItemSelected(android.widget.AdapterView<?> p,View v,int pos,long id){int selected=seasonValues.get(pos);for(int j=0;j<episodes.getChildCount();j++){View child=episodes.getChildAt(j);child.setVisibility(selected==-1||Integer.valueOf(selected).equals(child.getTag())?View.VISIBLE:View.GONE);}}});
        for(int i=0;i<files.length();i++) {
            JSONObject file=files.getJSONObject(i);long id=file.getLong("id");String name=file.optString("name");
            if(work.optString("kind").equals("series")&&!file.isNull("season")&&!file.isNull("episode"))name=String.format(java.util.Locale.ROOT,"S%02d E%02d  ·  ",file.optInt("season"),file.optInt("episode"))+name;
            LinearLayout episode=new LinearLayout(this);episode.setOrientation(LinearLayout.VERTICAL);episode.setTag(file.optInt("season",1));episodes.addView(episode);
            Button playEpisode=button(name+"  ·  "+(int)(file.optDouble("duration")/60)+" 分钟",()->startPlayer(id,false));playEpisode.setOnLongClickListener(v->{watchAction(work.optLong("id"),id);return true;});episode.addView(playEpisode);
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
            for(int i=0;i<bookmarks.length();i++){
                JSONObject mark=bookmarks.optJSONObject(i);if(mark==null)continue;
                if(i<12&&!mark.isNull("image")){ImageView preview=new ImageView(this);preview.setScaleType(ImageView.ScaleType.FIT_CENTER);page.addView(preview,new LinearLayout.LayoutParams(-1,dp(140)));loadImage(preview,mark.optString("image"));}
                page.addView(button(String.format(java.util.Locale.ROOT,"%d:%02d · %s",mark.optInt("position")/60,mark.optInt("position")%60,mark.optString("title")),()->{
                    Intent intent=playerIntent(mark.optLong("file_id"),false);intent.putExtra("start_position",mark.optDouble("position"));startActivity(intent);
                }));if(!mark.optString("note").isEmpty())page.addView(text(mark.optString("note"),14,MUTED));
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
                new AlertDialog.Builder(this).setTitle("电脑端保存目录").setMessage("填写电脑上的完整路径；留空恢复分类默认目录。").setView(input)
                    .setPositiveButton("保存",(dialog,which)->request(()->api.post("/api/works/"+work.optLong("id")+"/download-directory",new JSONObject().put("directory",input.getText().toString().trim())),result->{
                        work.put("download_directory",result.getString("directory"));directory.setText("保存到电脑："+result.getString("directory"));
                    })).setNegativeButton("取消",null).show();
            }));
            TextView status=text("HTTP 下载完成后自动加入当前影视资料；磁力由电脑端配置的外部下载器处理。",13,MUTED);page.addView(status);
            for(int i=0;i<downloads.length();i++){
                JSONObject entry=downloads.optJSONObject(i);if(entry==null)continue;final int index=i;
                page.addView(button(entry.optString("description","下载"),()->request(
                    ()->api.post("/api/works/"+work.optLong("id")+"/downloads",new JSONObject().put("index",index)),result->{
                        String task=result.getString("task_id");status.setText("已加入电脑端下载队列…");
                        getSharedPreferences("download-tasks",0).edit().putString(Long.toString(work.optLong("id")),task).apply();
                        pollDownload(task,work.optLong("id"),status,generation);
                    })));
            }
            page.addView(button("外部下载完成，检查文件并入库",()->request(
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
        state.resultTag=discoveryResultTag;
        state.mainPage=mainPage;state.watchlistOnly=watchlistOnly;state.dislikedOnly=dislikedOnly;state.favorites=favorites;state.recommended=recommended;state.discovery=discovery;state.actresses=actresses;
        state.offset=offset;state.scroll=browseScroll==null?0:browseScroll.getScrollY();
        state.detailScroll=detailScroll==null?0:detailScroll.getScrollY();
        try{state.detail=detailId>0&&detail!=null?new JSONObject(detail.toString()):null;}catch(Exception ignored){}
        navigationHistory.addLast(state);while(navigationHistory.size()>20)navigationHistory.removeFirst();
        savedList="";watchFilter="";tagFilter=field.equals("tag")?value:"";actorFilter=field.equals("actor")?value:"";
        yearMinFilter="";yearMaxFilter="";ratingMinFilter="";tagsAllFilter="";favorites=false;watchlistOnly=false;dislikedOnly=false;mainPage="library";recommended=false;discovery=state.discovery;actresses=false;discoveryOnline=false;query="";kind="";showLibrary();
    }
    private void restoreNavigation(){
        NavigationState state=navigationHistory.removeLast();
        kind=state.kind;query=state.query;tagFilter=state.tag;actorFilter=state.actor;yearMinFilter=state.yearMin;yearMaxFilter=state.yearMax;ratingMinFilter=state.ratingMin;tagsAllFilter=state.tagsAll;
        tagsAnyFilter=state.tagsAny==null?"":state.tagsAny;tagsNotFilter=state.tagsNot==null?"":state.tagsNot;sortField=state.sort;watchFilter=state.watch;savedList=state.list;sortDescending=state.descending;
        discoverySort=state.discoverySort;discoveryDescending=state.discoveryDescending;
        discoveryOnline=state.discoveryOnline;discoveryProvider=state.discoveryProvider;discoverySearchTask=state.searchTask;discoverySearchState=state.searchState;discoverySearchMessage=state.searchMessage;discoverySearchErrors=state.searchErrors;
        discoveryResultTag=state.resultTag;
        try{discoveryResultIds=state.resultIds==null?null:new JSONArray(state.resultIds);}catch(Exception ignored){discoveryResultIds=null;}
        mainPage=state.mainPage;watchlistOnly=state.watchlistOnly;dislikedOnly=state.dislikedOnly;favorites=state.favorites;recommended=state.recommended;discovery=state.discovery;actresses=state.actresses;
        showLibrary();restoreOffset=Math.max(1,state.offset);restoreScroll=state.scroll;
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
                Button favorite=browseRoot.findViewWithTag("mark:"+id+":favorite");
                if(favorite!=null){markStyle(favorite,record,"favorite",record.optInt("favorite")==1,true);favorite.setEnabled(true);}
                if((favorites&&record.optInt("favorite")==0)||(watchlistOnly&&record.optInt("watchlist")==0)||(dislikedOnly&&record.optInt("disliked")==0)||(!watchFilter.isEmpty()&&!watchFilter.equals(record.optString("watch_state")))){
                    View card=browseRoot.findViewWithTag("card:"+id);if(card!=null&&card.getParent() instanceof android.view.ViewGroup){((android.view.ViewGroup)card.getParent()).removeView(card);offset=Math.max(0,offset-1);int position=browsePositions.getOrDefault(id,-1);browsePositions.remove(id);for(Long key:new java.util.ArrayList<>(browsePositions.keySet()))if(browsePositions.get(key)>position)browsePositions.put(key,browsePositions.get(key)-1);}
                }
            }
        }
        detailId=0;renderedDetailId=0;detailScroll=null;generation++;
        if(browseRoot!=null){root=browseRoot;setContentView(root);imageRequests.restore(api,root);browseRoot=null;if(browseLoading!=null){content.removeView(browseLoading);browseLoading=null;loadPage();}if(discovery&&discoveryTagInput!=null&&discoveryTagInput.getAdapter().isEmpty())loadDiscoveryTags(discoveryTagInput);if(discovery&&discoveryOnline&&!discoverySearchTask.isEmpty()&&discoverySearchBusy())pollDiscoverySearch(discoverySearchTask,generation);}else showLibrary();
    }
    private void sorting(){
        if(discovery){
            String[] choices=java.util.Arrays.copyOf(DISCOVERY_SORT_NAMES,DISCOVERY_SORT_NAMES.length+1);choices[choices.length-1]=discoveryDescending?"改为升序":"改为降序";
            new AlertDialog.Builder(this).setTitle("发现影片排序").setItems(choices,(dialog,index)->{
                if(index==DISCOVERY_SORT_KEYS.length)discoveryDescending=!discoveryDescending;else discoverySort=DISCOVERY_SORT_KEYS[index];
                saveDiscoverySort();showLibrary();
            }).show();return;
        }
        new AlertDialog.Builder(this).setTitle("排序").setItems(new String[]{"入库时间","名称","年份","个人评分","时长","切换升序 / 降序"},(d,index)->{
            if(index==5)sortDescending=!sortDescending;else sortField=new String[]{"added","title","year","rating","duration"}[index];
            getSharedPreferences("catalog",0).edit().putString("sort",sortField).putBoolean("descending",sortDescending).apply();showLibrary();
        }).show();
    }
    private void smartLists(){
        request(()->api.get("/api/lists"),result->{
            JSONArray lists=result.getJSONArray("items");String[] names=new String[lists.length()];for(int i=0;i<lists.length();i++)names[i]=lists.getJSONObject(i).getString("name");
            AlertDialog.Builder dialog=new AlertDialog.Builder(this).setTitle("智能片单").setNegativeButton("关闭",null);
            if(names.length==0)dialog.setMessage("还没有片单。进入媒体库筛选影片后，在当前列表操作中保存片单。");
            else dialog.setItems(names,(d,index)->{resetBrowseFilters();mainPage="mine";savedList=names[index];JSONObject stored=lists.optJSONObject(index).optJSONObject("filters");if(stored!=null){String sort=stored.optString("sort","added");sortField=java.util.Arrays.asList("added","title","year","rating","duration").contains(sort)?sort:"added";sortDescending=stored.optBoolean("descending",true);}showLibrary();});dialog.show();
        });
    }
    private void saveSmartList(){
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
        new AlertDialog.Builder(this).setTitle("观看状态").setItems(fileId==null?new String[]{"标记已看","标记未看 / 重置进度"}:new String[]{"标记已看","标记未看 / 重置进度","从头播放"},(d,index)->{
            try{JSONObject payload=new JSONObject().put("state",index==0?"completed":"unwatched");if(fileId!=null)payload.put("file_id",fileId);else if(index==2)payload.put("file_id",detail.optLong("resume_file_id"));
                request(()->api.post("/api/works/"+workId+"/watched",payload),ok->{if(index==2){startPlayer(fileId!=null?fileId:detail.optLong("resume_file_id"),false);}else openDetail(workId);});
            }catch(Exception e){message(e.getMessage());}
        }).show();
    }
    private void showGallery(JSONArray paths,int start){
        if(paths.length()==0)return;
        android.app.Dialog dialog=new android.app.Dialog(this,android.R.style.Theme_Material_NoActionBar_Fullscreen);
        LinearLayout page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);page.setBackgroundColor(Color.BLACK);
        int[] index={start};ZoomImage[] image={null};TextView title=text("",16,Color.WHITE);
        Runnable render=()->{title.setText((index[0]+1)+" / "+paths.length()+" · 双指缩放，缩小时左右滑动切换");image[0].resetZoom();image[0].setImageDrawable(null);loadImage(image[0],paths.optString(index[0]));};
        image[0]=new ZoomImage(this,delta->{index[0]=(index[0]+delta+paths.length())%paths.length();render.run();});
        page.addView(title);page.addView(image[0],new LinearLayout.LayoutParams(-1,0,1));LinearLayout controls=new LinearLayout(this);
        controls.addView(button("上一张",()->{index[0]=(index[0]+paths.length()-1)%paths.length();render.run();}));controls.addView(button("下一张",()->{index[0]=(index[0]+1)%paths.length();render.run();}));controls.addView(button("关闭",dialog::dismiss));page.addView(controls);
        dialog.setContentView(page);dialog.show();render.run();
    }
    private void queueEditor(){
        android.content.SharedPreferences prefs=getSharedPreferences("queue",0);
        try{
            JSONArray ids=new JSONArray(prefs.getString("ids","[]"));
            if(ids.length()==0){new AlertDialog.Builder(this).setTitle("手机播放队列").setMessage("队列为空。可从影片详情加入，或随机播放当前列表。此队列保存在手机，与电脑队列独立。").setPositiveButton("关闭",null).show();return;}
            StringBuilder queryIds=new StringBuilder();for(int i=0;i<ids.length();i++){if(i>0)queryIds.append(",");queryIds.append(ids.optLong(i));}
            request(()->api.get("/api/queue-titles?ids="+queryIds),reply->{
                java.util.ArrayList<Long> values=new java.util.ArrayList<>();for(int i=0;i<ids.length();i++)values.add(ids.getLong(i));JSONObject titles=reply.optJSONObject("titles");
                LinearLayout page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);page.setPadding(dp(16),dp(8),dp(16),dp(8));page.addView(text("此队列保存在手机，与电脑队列独立。选中影片后可连续调整顺序。",13,MUTED));
                ListView list=new ListView(this);list.setChoiceMode(ListView.CHOICE_MODE_SINGLE);page.addView(list,new LinearLayout.LayoutParams(-1,Math.min(dp(340),getResources().getDisplayMetrics().heightPixels/3)));
                ArrayAdapter<String> adapter=new ArrayAdapter<>(this,android.R.layout.simple_list_item_single_choice,new java.util.ArrayList<>());list.setAdapter(adapter);final int[] selected={Math.min(prefs.getInt("index",0),values.size()-1)};
                Runnable render=()->{adapter.clear();for(int i=0;i<values.size();i++){long id=values.get(i);adapter.add((i+1)+". "+(titles==null?"作品 #"+id:titles.optString(String.valueOf(id),"已移除的作品")));}adapter.notifyDataSetChanged();if(!values.isEmpty()){selected[0]=Math.max(0,Math.min(selected[0],values.size()-1));list.setItemChecked(selected[0],true);}};
                list.setOnItemClickListener((parent,view,index,id)->selected[0]=index);
                ChipLayout controls=new ChipLayout(this);page.addView(controls);
                java.util.function.IntConsumer change=action->{
                    if(values.isEmpty())return;int index=Math.max(0,Math.min(selected[0],values.size()-1));long current=values.get(Math.max(0,Math.min(prefs.getInt("index",0),values.size()-1)));
                    if(action==0){prefs.edit().putInt("index",index).apply();Intent intent=new Intent(this,PlayerActivity.class);intent.putExtra("work_id",values.get(index));intent.putExtra("queue",true);startActivity(intent);return;}
                    if(action==3)values.remove(index);else {int target=action==1?index-1:index+1;if(target<0||target>=values.size())return;java.util.Collections.swap(values,index,target);selected[0]=target;}
                    prefs.edit().putString("ids",new JSONArray(values).toString()).putInt("index",Math.max(0,values.indexOf(current))).apply();render.run();
                };
                controls.addView(button("播放",()->change.accept(0)));controls.addView(button("上移",()->change.accept(1)));controls.addView(button("下移",()->change.accept(2)));controls.addView(button("移除",()->change.accept(3)));
                Spinner repeat=new Spinner(this);repeat.setContentDescription("手机队列循环模式");repeat.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"播完停止","列表循环","单部循环"}));repeat.setSelection(prefs.getInt("repeat",0));repeat.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onNothingSelected(AdapterView<?> parent){}public void onItemSelected(AdapterView<?> parent,View view,int mode,long id){prefs.edit().putInt("repeat",mode).apply();}});page.addView(repeat);
                ScrollView scroll=new ScrollView(this);scroll.addView(page);new AlertDialog.Builder(this).setTitle("手机播放队列").setView(scroll).setNegativeButton("关闭",null).show();render.run();
            });
        }catch(Exception error){message(error.getMessage());}
    }

    private void markStyle(Button button,JSONObject work,String field,boolean active,boolean compact){
        String title=field.equals("favorite")?"收藏":"想看";
        button.setText(compact?"":(active?"已":"")+title);button.setContentDescription((active?"取消":"加入")+title);
        MediaStyle.button(button,false,active,field.equals("favorite"));MediaStyle.icon(button,field.equals("favorite")?"heart":"bookmark",active);
        if(compact)button.setBackgroundColor(Color.TRANSPARENT);
    }
    private Button markButton(JSONObject work,String field,boolean compact){
        Button button=button("",()->{});button.setTag("mark:"+work.optLong("id")+":"+field);markStyle(button,work,field,work.optInt(field)==1,compact);
        button.setOnClickListener(view->{
            boolean old=work.optInt(field)==1,value=!old;int ticket=generation;Api client=api;
            markStyle(button,work,field,value,compact);button.setEnabled(false);
            network.execute(()->{
                try{
                    client.post("/api/works/"+work.optLong("id")+"/personal",new JSONObject().put(field,value));
                    runOnUiThread(()->{
                        if(isDestroyed())return;
                        try{work.put(field,value?1:0);}catch(Exception ignored){}
                        if(ticket!=generation)return;
                        Button current=root.findViewWithTag("mark:"+work.optLong("id")+":"+field);
                        if(current!=null){markStyle(current,work,field,value,compact);current.setEnabled(true);}
                        if(field.equals("favorite")&&favorites&&!value&&detailId==0){View card=root.findViewWithTag("card:"+work.optLong("id"));if(card!=null&&card.getParent() instanceof android.view.ViewGroup)((android.view.ViewGroup)card.getParent()).removeView(card);}
                        message(value?"已加入"+(field.equals("favorite")?"收藏":"想看"):"已取消"+(field.equals("favorite")?"收藏":"想看"));
                    });
                }catch(Exception error){runOnUiThread(()->{if(!isDestroyed()&&ticket==generation){Button current=root.findViewWithTag("mark:"+work.optLong("id")+":"+field);if(current!=null){markStyle(current,work,field,old,compact);current.setEnabled(true);}message("未保存："+error.getMessage());}});}
            });
        });return button;
    }
    private void personal(String field,Object value) {
        long id=detailId;JSONObject current=detail;
        request(()->api.post("/api/works/"+id+"/personal",new JSONObject().put(field,value)),result->{
            current.put(field,value);Button score=root.findViewWithTag("rating:"+id);
            if(score!=null){score.setText(current.isNull("rating")?"评分":current.optInt("rating")+" 分");MediaStyle.icon(score,"star",!current.isNull("rating"));}
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
    private void shuffle() {
        final String scope=listPath();
        request(()->api.post("/api/queue/from-browse",new JSONObject().put("browse_path",scope)),result->{
            JSONArray ids=result.getJSONArray("ids");if(ids.length()==0){message("当前列表没有可播放的本地视频");return;}
            getSharedPreferences("queue",0).edit().putString("ids",ids.toString()).putInt("index",0).apply();
            Intent intent=new Intent(this,PlayerActivity.class);intent.putExtra("work_id",ids.getLong(0));intent.putExtra("queue",true);startActivity(intent);
        },error->{
            String explanation=error!=null&&error.contains("404")?"当前电脑版本不支持按列表随机播放，请更新电脑端后重试。":"无法生成当前列表的播放队列："+error;
            new AlertDialog.Builder(this).setTitle("未开始随机播放").setMessage(explanation).setPositiveButton("关闭",null).show();
        });
    }
    private void showStats() {
        request(()->api.get("/api/stats"),stats->{
            new AlertDialog.Builder(this).setTitle("观影统计 · 与电脑同步").setMessage(String.format(java.util.Locale.ROOT,
                "累计实际观看 %.1f 小时\n有效播放 %d 次\n播放会话 %d 次\n看过电影 %d 部\n看过电视剧 %d 部\n\n有效播放须严格超过 600 秒。",
                stats.optDouble("seconds")/3600,stats.optInt("valid"),stats.optInt("sessions"),stats.optInt("movies"),stats.optInt("series"))).setPositiveButton("关闭",null).show();
        });
    }
}
