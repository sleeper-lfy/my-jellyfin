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
    private static final int BG=Color.rgb(16,16,16), BLUE=Color.rgb(0,164,220), MUTED=Color.rgb(160,160,160);
    private final android.os.Handler downloadUpdates=new android.os.Handler(android.os.Looper.getMainLooper());
    private final ExecutorService network=Executors.newFixedThreadPool(4);
    private final LruCache<String,Bitmap> pictures=new LruCache<String,Bitmap>(24*1024) {
        @Override protected int sizeOf(String key,Bitmap image){return image.getByteCount()/1024;}
    };
    private Api api;
    private LinearLayout root,content;
    private ChipLayout posters;
    private ScrollView detailScroll;
    private String kind="",query="",tagFilter="",actorFilter="",yearFilter="";
    private boolean favorites=false,recommended=false,discovery=false;
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
    private TextView browseLoading;
    private static final class NavigationState {
        String kind,query,tag,actor,year,sort,watch,list,discoverySort,discoveryProvider,searchTask,searchState,searchMessage,searchErrors,resultIds,resultTag;
        boolean favorites,recommended,discovery,descending,discoveryDescending,discoveryOnline;
        int offset,scroll,detailScroll;
        JSONObject detail;
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        sortField=getSharedPreferences("catalog",0).getString("sort","added");sortDescending=getSharedPreferences("catalog",0).getBoolean("descending",true);
        discoverySort=getSharedPreferences("discovery",0).getString("sort","discovered");discoveryDescending=getSharedPreferences("discovery",0).getBoolean("descending",true);
        if(!java.util.Arrays.asList(DISCOVERY_SORT_KEYS).contains(discoverySort))discoverySort="discovered";
        Connection connection=Connection.load(this);
        if(connection==null)showConnection();else {api=new Api(connection);showLibrary();}
    }
    @Override protected void onResume() {
        super.onResume();
        if(returned && api!=null) { if(detailId>0)openDetail(detailId);else showLibrary(); }
        returned=true;
    }
    @Override public void onConfigurationChanged(Configuration configuration) {
        super.onConfigurationChanged(configuration);
        if(api!=null) { try {if(detailId>0 && detail!=null)renderDetail(detail);else showLibrary();} catch(Exception e){message(e.getMessage());} }
    }
    @Override public void onBackPressed() {
        if(detailId>0) {returnLibrary();}else if(!navigationHistory.isEmpty())restoreNavigation();else super.onBackPressed();
    }
    @Override protected void onDestroy() {downloadUpdates.removeCallbacksAndMessages(null);network.shutdownNow();super.onDestroy();}
    private int dp(float value){return Math.round(value*getResources().getDisplayMetrics().density);}
    private TextView text(String value,int size,int color) {
        TextView view=new TextView(this);view.setText(value);view.setTextSize(size);if(size>=20)view.setTypeface(android.graphics.Typeface.DEFAULT,android.graphics.Typeface.BOLD);view.setTextColor(color);view.setPadding(0,dp(6),0,dp(6));return view;
    }
    private Button button(String title,Runnable action) {
        Button button=new Button(this);button.setText(title);button.setTextColor(Color.WHITE);button.setAllCaps(false);button.setTextSize(14);
        MediaStyle.button(button,false,false,false);button.setOnClickListener(v->action.run());return button;
    }
    private void base() {
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
        LinearLayout addressRow=new LinearLayout(this);addressRow.addView(address,new LinearLayout.LayoutParams(0,dp(56),1));
        addressRow.addView(button("⌄",()->{address.requestFocus();address.showDropDown();}),new LinearLayout.LayoutParams(dp(52),dp(56)));panel.addView(addressRow);
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
                    candidate.save(this);api=client;pictures.evictAll();kind="";query="";tagFilter="";actorFilter="";yearFilter="";favorites=false;recommended=false;showLibrary();
                });
            }catch(Exception e){status.setText(e.getMessage());}
        });MediaStyle.button(connect,true,false,false);panel.addView(connect);
        panel.addView(text("地址使用电脑的局域网 IPv4，不能填手机自己的 localhost。服务关闭或电脑休眠时，客户端无法播放。",13,MUTED));
        panel.addView(button("检查客户端更新",()->startActivity(new Intent(this,UpdateActivity.class))));
    }
    private void header(String title, boolean back) {
        LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(dp(12),dp(6),dp(8),dp(6));
        if(back||!navigationHistory.isEmpty()){Button previous=button("",this::onBackPressed);MediaStyle.icon(previous,"back",false);previous.setContentDescription("返回上一页");row.addView(previous,new LinearLayout.LayoutParams(dp(48),dp(48)));}
        TextView brand=text(title,24,Color.WHITE);row.addView(brand,new LinearLayout.LayoutParams(0,dp(52),1));
        if(!back){Button collection=button("",()->{navigationHistory.clear();kind="";query="";savedList="";favorites=true;recommended=false;discovery=false;tagFilter="";actorFilter="";yearFilter="";showLibrary();});MediaStyle.icon(collection,"heart",favorites);collection.setContentDescription("收藏");row.addView(collection,new LinearLayout.LayoutParams(dp(48),dp(48)));}
        Button more=button("",()->{});MediaStyle.icon(more,"more",false);more.setContentDescription("更多操作");more.setOnClickListener(view->{
            PopupMenu menu=new PopupMenu(this,view);menu.getMenu().add("排序");menu.getMenu().add("智能片单");menu.getMenu().add("播放队列");menu.getMenu().add("随机播放");menu.getMenu().add("观影统计");menu.getMenu().add("电脑遥控");menu.getMenu().add("检查更新");menu.getMenu().add("切换连接");
            menu.setOnMenuItemClickListener(item->{switch(item.getTitle().toString()){case "排序":sorting();break;case "智能片单":smartLists();break;case "播放队列":queueEditor();break;case "随机播放":shuffle();break;case "观影统计":showStats();break;case "电脑遥控":startActivity(new Intent(this,RemoteActivity.class));break;case "检查更新":startActivity(new Intent(this,UpdateActivity.class));break;default:showConnection();}return true;});menu.show();
        });row.addView(more,new LinearLayout.LayoutParams(dp(48),dp(48)));root.addView(row);
    }
    private void showLibrary() {
        generation++;browseRoot=null;detailId=0;renderedDetailId=0;detailScroll=null;browseLoading=null;discoveryTagInput=null;offset=0;restoreOffset=0;restoreScroll=0;browsePositions.clear();browseRecords.clear();base();header("Lumen",false);
        LinearLayout searchRow=new LinearLayout(this);searchRow.setPadding(dp(16),0,dp(16),0);
        EditText search=new EditText(this);search.setTextColor(Color.WHITE);search.setHintTextColor(MUTED);search.setHint(discovery?"按影片名称搜索":"搜索媒体库");search.setContentDescription(discovery?"发现影片名称搜索":"媒体库搜索");search.setSingleLine(true);search.setText(query);search.setImeOptions(EditorInfo.IME_ACTION_SEARCH);
        Runnable applySearch=()->{if(discovery&&discoveryOnline){startDiscoverySearch(search);return;}savedList="";query=search.getText().toString().trim();if(discovery&&discoveryTagInput!=null)tagFilter=discoveryTagInput.getText().toString().trim();showLibrary();};
        search.setOnEditorActionListener((view,action,event)->{if(action==EditorInfo.IME_ACTION_SEARCH){applySearch.run();return true;}return false;});
        search.setBackground(MediaStyle.surface(this,0xff202026,0xff3a3a44,8));search.setPadding(dp(12),0,dp(8),0);
        searchRow.addView(search,new LinearLayout.LayoutParams(0,dp(48),1));Button searchButton=button("",applySearch);MediaStyle.icon(searchButton,"search",false);searchButton.setContentDescription("搜索");LinearLayout.LayoutParams searchParams=new LinearLayout.LayoutParams(dp(48),dp(48));searchParams.setMargins(dp(6),0,dp(6),0);searchRow.addView(searchButton,searchParams);
        String activeTag=discovery&&discoveryOnline?discoveryResultTag:tagFilter;
        int count=(watchFilter.isEmpty()?0:1)+(savedList.isEmpty()?0:1)+(activeTag.isEmpty()?0:1)+(actorFilter.isEmpty()?0:1)+(yearFilter.isEmpty()?0:1)+(favorites?1:0);
        Button filters=button("筛选"+(count>0?" · "+count:""),this::showFilters);MediaStyle.icon(filters,"filter",count>0);searchRow.addView(filters);root.addView(searchRow);
        ChipLayout selectedFilters=new ChipLayout(this);selectedFilters.setPadding(dp(16),dp(8),dp(16),0);
        if(!activeTag.isEmpty())selectedFilters.addView(filterChip(activeTag,()->{if(discovery&&discoveryOnline)discoveryResultTag="";else tagFilter="";showLibrary();}));
        if(!actorFilter.isEmpty())selectedFilters.addView(filterChip(actorFilter,()->{actorFilter="";showLibrary();}));
        if(!yearFilter.isEmpty())selectedFilters.addView(filterChip(yearFilter,()->{yearFilter="";showLibrary();}));
        if(!watchFilter.isEmpty())selectedFilters.addView(filterChip(watchFilter.equals("completed")?"已完成":watchFilter.equals("progress")?"观看中":"未开始",()->{watchFilter="";savedList="";showLibrary();}));
        if(!savedList.isEmpty())selectedFilters.addView(filterChip("片单："+savedList,()->{savedList="";showLibrary();}));
        if(favorites)selectedFilters.addView(filterChip("已收藏",()->{favorites=false;showLibrary();}));
        if(count>0)root.addView(selectedFilters);
        HorizontalScrollView nav=new HorizontalScrollView(this);nav.setHorizontalScrollBarEnabled(false);LinearLayout links=new LinearLayout(this);
        String[] names={"首页","电影","电视剧","VR电影","Fans视频","其他","收藏","为我推荐","影片发现"};String[] types={"","movie","series","vr","fans","other","","",""};
        for(int i=0;i<names.length;i++) {
            final int choice=i;Button tab=button(names[i],()->{navigationHistory.clear();savedList="";watchFilter="";kind=types[choice];favorites=choice==6;recommended=choice==7;discovery=choice==8;query="";tagFilter="";actorFilter="";yearFilter="";if(discovery)clearDiscoverySearch();showLibrary();});
            boolean selected=(choice==6&&favorites&&kind.isEmpty())||(choice==7&&recommended)||(choice==8&&discovery)||(choice<6&&(!favorites||!kind.isEmpty())&&!recommended&&!discovery&&kind.equals(types[i]));
            tab.setBackground(MediaStyle.surface(this,selected?0xff15343f:Color.TRANSPARENT,0,20));if(selected)tab.setTextColor(0xff9cdef2);links.addView(tab);
        }
        nav.addView(links);root.addView(nav);
        ScrollView scroll=new ScrollView(this);browseScroll=scroll;content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);content.setPadding(dp(16),dp(10),dp(16),dp(16));scroll.addView(content);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        if(kind.isEmpty()&&!favorites&&!recommended&&!discovery&&query.isEmpty()&&tagFilter.isEmpty()&&actorFilter.isEmpty()&&yearFilter.isEmpty()) {
            content.addView(text("我的媒体",22,Color.WHITE));LinearLayout tiles=new LinearLayout(this);
            for(int i=1;i<=5;i++){final int choice=i;Button tile=button(names[i],()->{savedList="";kind=types[choice];showLibrary();});tile.setBackgroundTintList(android.content.res.ColorStateList.valueOf(Color.rgb(35,35,35)));LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(85),1);p.setMargins(dp(3),0,dp(3),dp(12));tiles.addView(tile,p);}
            content.addView(tiles);
        }
        content.addView(text(recommended?"为我推荐":discovery?"影片发现":favorites?"收藏":query.isEmpty()?"媒体库":"搜索结果",22,Color.WHITE));
        if(discovery)showDiscoveryTools(search,applySearch);
        posters=new ChipLayout(this);content.addView(posters);
        if(discovery&&discoveryOnline&&discoveryResultIds==null){
            content.addView(text(discoverySearchState.equals("running")||discoverySearchState.equals("queued")?"正在搜索站点，完成后显示本次结果。":"输入影片名称或标签，点击“搜索站点”。",15,MUTED));
        }else loadPage();
        if(discovery&&discoveryOnline&&!discoverySearchTask.isEmpty()&&(discoverySearchState.equals("running")||discoverySearchState.equals("queued")))pollDiscoverySearch(discoverySearchTask,generation);
    }
    private String listPath() {
        String path=recommended?"/api/recommendations?":discovery?"/api/discover?":"/api/works?";
        boolean onlineResult=discovery&&discoveryOnline;
        String ids="";if(onlineResult){java.util.ArrayList<String> selected=new java.util.ArrayList<>();if(discoveryResultIds!=null)for(int i=0;i<discoveryResultIds.length();i++)selected.add(Long.toString(discoveryResultIds.optLong(i)));ids="&ids="+android.text.TextUtils.join(",",selected);}
        return path+"offset="+offset+"&limit=30&kind="+kind+"&favorite="+favorites+"&q="+android.net.Uri.encode(onlineResult?"":query)+(discovery?"&tag_q=":"&tag=")+android.net.Uri.encode(onlineResult?discoveryResultTag:tagFilter)+"&actor="+android.net.Uri.encode(actorFilter)+"&year="+android.net.Uri.encode(yearFilter)+"&sort="+(discovery?discoverySort:sortField)+"&direction="+((discovery?discoveryDescending:sortDescending)?"desc":"asc")+"&watch_state="+watchFilter+"&list="+android.net.Uri.encode(savedList)+ids;
    }
    private void showDiscoveryTools(EditText search,Runnable applySearch){
        LinearLayout panel=new LinearLayout(this);panel.setOrientation(LinearLayout.VERTICAL);panel.setPadding(dp(12),dp(6),dp(12),dp(12));
        panel.setBackground(MediaStyle.surface(this,0xff19191f,0xff30303a,10));
        Spinner scope=new Spinner(this);scope.setTag("discoveryScope");scope.setContentDescription("发现搜索范围");scope.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"筛选已发现资料","在线搜索站点"}));scope.setSelection(discoveryOnline?1:0);
        scope.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onNothingSelected(AdapterView<?> parent){}public void onItemSelected(AdapterView<?> parent,View view,int position,long id){
            boolean online=position==1;if(online==discoveryOnline)return;query=search.getText().toString().trim();if(discoveryTagInput!=null)tagFilter=discoveryTagInput.getText().toString().trim();if(!online)clearDiscoverySearch();discoveryOnline=online;showLibrary();
        }});panel.addView(scope,new LinearLayout.LayoutParams(-1,dp(48)));
        TextView label=text("标签搜索",13,MUTED);panel.addView(label);
        AutoCompleteTextView tag=new SearchDropdown(this);discoveryTagInput=tag;
        tag.setTag("discoveryTag");tag.setContentDescription("发现影片标签搜索");tag.setSingleLine(true);tag.setTextColor(Color.WHITE);tag.setHintTextColor(MUTED);
        tag.setHint("输入标签搜索或下拉选择");tag.setText(tagFilter);tag.setImeOptions(EditorInfo.IME_ACTION_SEARCH);
        tag.setPadding(dp(12),0,dp(8),0);tag.setBackground(MediaStyle.surface(this,0xff24242b,0xff41414a,8));
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
        kind="";actorFilter="";yearFilter="";favorites=false;watchFilter="";savedList="";discoveryResultTag="";
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
        Button chip=button(text,remove);chip.setTextSize(13);chip.setMaxWidth(dp(230));chip.setSingleLine(true);chip.setEllipsize(android.text.TextUtils.TruncateAt.END);
        chip.setBackground(MediaStyle.surface(this,0xff18313a,0xff315563,20));chip.setTextColor(0xffbfe8f6);MediaStyle.icon(chip,"close",false);chip.setContentDescription("移除筛选："+text);return chip;
    }
    private AutoCompleteTextView filterInput(LinearLayout form,String label,String value){
        form.addView(text(label,15,MUTED));
        AutoCompleteTextView input=new SearchDropdown(this);input.setSingleLine(true);input.setTextColor(Color.WHITE);input.setHintTextColor(MUTED);
        input.setHint("输入搜索或下拉选择");input.setText(value);input.setBackground(MediaStyle.surface(this,0xff24242b,0xff41414a,8));input.setPadding(dp(12),dp(6),dp(10),dp(6));
        LinearLayout row=new LinearLayout(this);row.addView(input,new LinearLayout.LayoutParams(0,dp(56),1));
        row.addView(button("⌄",()->{input.requestFocus();input.showDropDown();}),new LinearLayout.LayoutParams(dp(52),dp(56)));form.addView(row);
        return input;
    }
    private void showFilters(){
        LinearLayout form=new LinearLayout(this);form.setOrientation(LinearLayout.VERTICAL);form.setPadding(dp(20),dp(12),dp(20),dp(12));
        AutoCompleteTextView tag=filterInput(form,"标签",discovery&&discoveryOnline?discoveryResultTag:tagFilter),actor=filterInput(form,"演员",actorFilter),year=filterInput(form,"年份",yearFilter);
        year.setInputType(InputType.TYPE_CLASS_NUMBER);
        android.widget.Spinner watching=new android.widget.Spinner(this);String[] states={"","unwatched","progress","completed"};
        watching.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"全部观看状态","未开始","观看中","已完成"}));
        for(int i=0;i<states.length;i++)if(states[i].equals(watchFilter))watching.setSelection(i);form.addView(watching);
        final boolean[] onlyFavorites={favorites};
        Button collection=button(favorites?"仅看已收藏":"全部收藏状态",()->{});MediaStyle.icon(collection,"heart",favorites);MediaStyle.button(collection,false,favorites,true);
        collection.setOnClickListener(view->{onlyFavorites[0]=!onlyFavorites[0];collection.setText(onlyFavorites[0]?"仅看已收藏":"全部收藏状态");MediaStyle.icon(collection,"heart",onlyFavorites[0]);MediaStyle.button(collection,false,onlyFavorites[0],true);});form.addView(collection);
        TextView status=text("正在读取筛选选项…",13,MUTED);form.addView(status);
        ScrollView scroll=new ScrollView(this);scroll.addView(form);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("筛选媒体库").setView(scroll)
            .setPositiveButton("应用",null).setNegativeButton("取消",null).setNeutralButton("重置",(d,which)->{tagFilter="";actorFilter="";yearFilter="";favorites=false;showLibrary();}).create();
        dialog.show();
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view->{
            String value=year.getText().toString().trim();
            if(!value.isEmpty()&&(!value.matches("[0-9]{4}")||Integer.parseInt(value)<1800||Integer.parseInt(value)>2200)){year.setError("请输入 1800–2200 的年份");return;}
            if(discovery&&discoveryOnline)discoveryResultTag=tag.getText().toString().trim();else tagFilter=tag.getText().toString().trim();actorFilter=actor.getText().toString().trim();yearFilter=value;favorites=onlyFavorites[0];watchFilter=states[watching.getSelectedItemPosition()];savedList="";dialog.dismiss();showLibrary();
        });
        android.view.Window sheet=dialog.getWindow();if(sheet!=null){sheet.setBackgroundDrawable(MediaStyle.surface(this,0xff18181e,0xff3a3a44,18));sheet.setGravity(Gravity.BOTTOM);sheet.setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);sheet.setLayout(-1,-2);View sheetView=sheet.getDecorView();sheetView.post(()->{int available=getResources().getDisplayMetrics().heightPixels-dp(48);if(sheetView.getHeight()>available)sheet.setLayout(-1,available);});}
        dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(view->{
            tag.setText("");actor.setText("");year.setText("");watching.setSelection(0);onlyFavorites[0]=false;
            collection.setText("全部收藏状态");MediaStyle.icon(collection,"heart",false);MediaStyle.button(collection,false,false,true);
        });
        MediaStyle.button(dialog.getButton(AlertDialog.BUTTON_POSITIVE),true,false,false);
        MediaStyle.button(dialog.getButton(AlertDialog.BUTTON_NEGATIVE),false,false,false);MediaStyle.button(dialog.getButton(AlertDialog.BUTTON_NEUTRAL),false,false,false);
        request(()->api.get("/api/filters?kind="+android.net.Uri.encode(kind)+"&discover="+discovery),options->{
            if(!dialog.isShowing())return;
            AutoCompleteTextView[] inputs={tag,actor,year};String[] keys={"tags","actors","years"};
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
            content.removeView(loading);if(browseLoading==loading)browseLoading=null;JSONArray items=result.getJSONArray("items");int total=result.optInt("total");
            if(total==0)content.addView(text(discovery?(discoveryOnline?"本次站点搜索没有匹配结果，可更换名称、标签或来源重试。":"暂无匹配的发现资料，可调整名称、标签或切换在线搜索站点。"):"暂无内容。请先在电脑端导入媒体，或调整搜索条件。",16,MUTED));
            int columns=getResources().getConfiguration().screenWidthDp>=650?4:2;
            int width=(getResources().getDisplayMetrics().widthPixels-dp(32))/columns;
            width=(getResources().getDisplayMetrics().widthPixels-dp(32)-(columns-1)*dp(6))/columns;
            for(int i=0;i<items.length();i++) {
                JSONObject work=items.getJSONObject(i);long id=work.getLong("id");browseRecords.put(id,work);browsePositions.put(id,offset+i);
                LinearLayout card=new LinearLayout(this);card.setTag("card:"+id);card.setOrientation(LinearLayout.VERTICAL);card.setPadding(dp(3),dp(6),dp(3),dp(12));
                FrameLayout cover=new FrameLayout(this);cover.setBackground(MediaStyle.surface(this,0xff25252b,0,6));cover.setClipToOutline(true);
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
        });
    }
    private void loadImage(ImageView view,String path) {
        if(path.isEmpty()||path.equals("null"))return;
        String key=api.connection.base+path;view.setTag(key);Bitmap cached=pictures.get(key);if(cached!=null){view.setImageBitmap(cached);return;}
        Api client=api;network.execute(()->{try{Bitmap image=client.image(path);if(image==null)return;pictures.put(key,image);runOnUiThread(()->{if(!isDestroyed()&&key.equals(view.getTag()))view.setImageBitmap(image);});}catch(Exception ignored){/* A missing cover does not prevent browsing or playback. */}});
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
        ImageView poster=new ImageView(this);poster.setScaleType(ImageView.ScaleType.FIT_CENTER);poster.setBackground(MediaStyle.surface(this,0xff19191f,0,6));poster.setClipToOutline(true);poster.setContentDescription("海报："+work.optString("title"));
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
        Button play=button(work.optDouble("position")>0?"继续播放":"播放",()->startPlayer(work.optLong("resume_file_id"),false));
        MediaStyle.button(play,true,false,false);MediaStyle.icon(play,"play",true);play.setEnabled(work.optInt("file_count")>0);page.addView(play,new LinearLayout.LayoutParams(-1,dp(52)));
        ChipLayout personal=new ChipLayout(this);personal.setPadding(0,dp(12),0,dp(12));
        personal.addView(markButton(work,"favorite",false));personal.addView(markButton(work,"watchlist",false));
        Button score=button(work.isNull("rating")?"评分":work.optInt("rating")+" 分",()->{
            String[] scores={"清除评分","1 分","2 分","3 分","4 分","5 分","6 分","7 分","8 分","9 分","10 分"};
            new AlertDialog.Builder(this).setTitle("我的评分").setSingleChoiceItems(scores,work.optInt("rating",0),(dialog,index)->{dialog.dismiss();personal("rating",index==0?JSONObject.NULL:index);}).setNegativeButton("取消",null).show();
        });score.setContentDescription("我的评分");score.setTag("rating:"+work.optLong("id"));MediaStyle.icon(score,"star",!work.isNull("rating"));personal.addView(score);page.addView(personal);
        JSONArray tags=work.optJSONArray("tags");JSONArray actors=work.optJSONArray("actors");
        ChipLayout metadata=new ChipLayout(this);metadata.setPadding(0,0,0,dp(12));
        if(tags!=null)for(int i=0;i<tags.length();i++){
            String tag=tags.optString(i);metadata.addView(button(tag,()->filterMetadata("tag",tag)));
        }
        if(metadata.getChildCount()>0)page.addView(metadata);
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
                personCard.addView(button(actor,()->filterMetadata("actor",actor)),new LinearLayout.LayoutParams(dp(104),dp(48)));cast.addView(personCard);
            }else cast.addView(button(actor,()->filterMetadata("actor",actor)));
        }
        if(cast.getChildCount()>0)page.addView(cast);
        page.addView(text(work.optString("overview","暂无简介"),15,MUTED));
        JSONArray files=work.getJSONArray("files");page.addView(text(work.optString("kind").equals("series")?"季与集":work.optString("kind").equals("fans")?"作者视频":"视频文件",21,Color.WHITE));
        page.addView(button("在电脑上播放",()->{Intent remote=new Intent(this,RemoteActivity.class);remote.putExtra("work_id",detailId);remote.putExtra("file_id",work.optLong("resume_file_id"));startActivity(remote);}));
        page.addView(button("观看状态 / 从头播放",()->watchAction(work.optLong("id"),null)));
        page.addView(button("加入播放队列",()->{try{android.content.SharedPreferences prefs=getSharedPreferences("queue",0);JSONArray ids=new JSONArray(prefs.getString("ids","[]"));boolean found=false;for(int j=0;j<ids.length();j++)if(ids.optLong(j)==work.optLong("id"))found=true;if(!found)ids.put(work.optLong("id"));prefs.edit().putString("ids",ids.toString()).apply();message("已加入队列");}catch(Exception e){message(e.getMessage());}}));
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
        state.kind=kind;state.query=query;state.tag=tagFilter;state.actor=actorFilter;state.year=yearFilter;
        state.sort=sortField;state.watch=watchFilter;state.list=savedList;state.descending=sortDescending;
        state.discoverySort=discoverySort;state.discoveryDescending=discoveryDescending;
        state.discoveryOnline=discoveryOnline;state.discoveryProvider=discoveryProvider;state.searchTask=discoverySearchTask;state.searchState=discoverySearchState;state.searchMessage=discoverySearchMessage;state.searchErrors=discoverySearchErrors;state.resultIds=discoveryResultIds==null?null:discoveryResultIds.toString();
        state.resultTag=discoveryResultTag;
        state.favorites=favorites;state.recommended=recommended;state.discovery=discovery;
        state.offset=offset;state.scroll=browseScroll==null?0:browseScroll.getScrollY();
        state.detailScroll=detailScroll==null?0:detailScroll.getScrollY();
        try{state.detail=detailId>0&&detail!=null?new JSONObject(detail.toString()):null;}catch(Exception ignored){}
        navigationHistory.addLast(state);while(navigationHistory.size()>20)navigationHistory.removeFirst();
        savedList="";watchFilter="";tagFilter=field.equals("tag")?value:"";actorFilter=field.equals("actor")?value:"";
        yearFilter="";favorites=false;recommended=false;discovery=state.discovery;discoveryOnline=false;query="";kind="";showLibrary();
    }
    private void restoreNavigation(){
        NavigationState state=navigationHistory.removeLast();
        kind=state.kind;query=state.query;tagFilter=state.tag;actorFilter=state.actor;yearFilter=state.year;
        sortField=state.sort;watchFilter=state.watch;savedList=state.list;sortDescending=state.descending;
        discoverySort=state.discoverySort;discoveryDescending=state.discoveryDescending;
        discoveryOnline=state.discoveryOnline;discoveryProvider=state.discoveryProvider;discoverySearchTask=state.searchTask;discoverySearchState=state.searchState;discoverySearchMessage=state.searchMessage;discoverySearchErrors=state.searchErrors;
        discoveryResultTag=state.resultTag;
        try{discoveryResultIds=state.resultIds==null?null:new JSONArray(state.resultIds);}catch(Exception ignored){discoveryResultIds=null;}
        favorites=state.favorites;recommended=state.recommended;discovery=state.discovery;
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
                if((favorites&&record.optInt("favorite")==0)||(!watchFilter.isEmpty()&&!watchFilter.equals(record.optString("watch_state")))){
                    View card=browseRoot.findViewWithTag("card:"+id);if(card!=null&&card.getParent() instanceof android.view.ViewGroup){((android.view.ViewGroup)card.getParent()).removeView(card);offset=Math.max(0,offset-1);int position=browsePositions.getOrDefault(id,-1);browsePositions.remove(id);for(Long key:new java.util.ArrayList<>(browsePositions.keySet()))if(browsePositions.get(key)>position)browsePositions.put(key,browsePositions.get(key)-1);}
                }
            }
        }
        detailId=0;renderedDetailId=0;detailScroll=null;generation++;
        if(browseRoot!=null){root=browseRoot;setContentView(root);browseRoot=null;if(browseLoading!=null){content.removeView(browseLoading);browseLoading=null;loadPage();}if(discovery&&discoveryTagInput!=null&&discoveryTagInput.getAdapter().isEmpty())loadDiscoveryTags(discoveryTagInput);if(discovery&&discoveryOnline&&!discoverySearchTask.isEmpty()&&discoverySearchBusy())pollDiscoverySearch(discoverySearchTask,generation);}else showLibrary();
    }
    private void sorting(){
        if(discovery){
            String[] choices=java.util.Arrays.copyOf(DISCOVERY_SORT_NAMES,DISCOVERY_SORT_NAMES.length+1);choices[choices.length-1]=discoveryDescending?"改为升序":"改为降序";
            new AlertDialog.Builder(this).setTitle("发现影片排序").setItems(choices,(dialog,index)->{
                if(index==DISCOVERY_SORT_KEYS.length)discoveryDescending=!discoveryDescending;else discoverySort=DISCOVERY_SORT_KEYS[index];
                saveDiscoverySort();savedList="";showLibrary();
            }).show();return;
        }
        new AlertDialog.Builder(this).setTitle("排序").setItems(new String[]{"入库时间","名称","年份","个人评分","时长","切换升序 / 降序"},(d,index)->{
            if(index==5)sortDescending=!sortDescending;else sortField=new String[]{"added","title","year","rating","duration"}[index];
            getSharedPreferences("catalog",0).edit().putString("sort",sortField).putBoolean("descending",sortDescending).apply();savedList="";showLibrary();
        }).show();
    }
    private void smartLists(){
        request(()->api.get("/api/lists"),result->{
            JSONArray lists=result.getJSONArray("items");String[] names=new String[lists.length()+1];names[0]="保存当前筛选…";
            for(int i=0;i<lists.length();i++)names[i+1]=lists.getJSONObject(i).getString("name");
            new AlertDialog.Builder(this).setTitle("智能片单").setItems(names,(d,index)->{
                if(index>0){savedList=names[index];recommended=false;showLibrary();return;}
                EditText input=new EditText(this);input.setHint("片单名称（同名会覆盖）");
                new AlertDialog.Builder(this).setTitle("保存智能片单").setView(input).setPositiveButton("保存",(a,b)->{
                    try{
                        JSONObject filters=new JSONObject().put("query",query).put("sort",sortField).put("descending",sortDescending);
                        if(!kind.isEmpty())filters.put("kinds",new JSONArray().put(kind));if(favorites)filters.put("favorite",true);
                        if(!tagFilter.isEmpty())filters.put("tags_all",new JSONArray().put(tagFilter));if(!actorFilter.isEmpty())filters.put("actor",actorFilter);
                        if(!yearFilter.isEmpty())filters.put("year_min",Integer.parseInt(yearFilter)).put("year_max",Integer.parseInt(yearFilter));if(!watchFilter.isEmpty())filters.put("watch_state",watchFilter);
                        JSONObject payload=new JSONObject().put("name",input.getText().toString()).put("filters",filters);
                        request(()->api.post("/api/lists",payload),ok->message("片单已保存"));
                    }catch(Exception e){message(e.getMessage());}
                }).setNegativeButton("取消",null).show();
            }).show();
        });
    }
    private void watchAction(long workId,Long fileId){
        new AlertDialog.Builder(this).setTitle("观看状态").setItems(new String[]{"标记已看","标记未看 / 重置进度","从头播放"},(d,index)->{
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
        try{JSONArray ids=new JSONArray(prefs.getString("ids","[]"));if(ids.length()==0){message("先随机播放，或从详情加入队列");return;}
            StringBuilder queryIds=new StringBuilder();for(int i=0;i<ids.length();i++){if(i>0)queryIds.append(",");queryIds.append(ids.optLong(i));}
            request(()->api.get("/api/queue-titles?ids="+queryIds),reply->{
                JSONObject titles=reply.optJSONObject("titles");
                String[] labels=new String[ids.length()];for(int i=0;i<ids.length();i++)labels[i]=(i+1)+". "+(titles==null?"作品 #"+ids.optLong(i):titles.optString(String.valueOf(ids.optLong(i)),"已移除的作品"));
                new AlertDialog.Builder(this).setTitle("播放队列").setItems(labels,(d,index)->{
                    new AlertDialog.Builder(this).setTitle(labels[index]).setItems(new String[]{"播放","上移","下移","移除"},(a,action)->{
                        try{java.util.ArrayList<Long> values=new java.util.ArrayList<>();for(int i=0;i<ids.length();i++)values.add(ids.getLong(i));long current=ids.optLong(prefs.getInt("index",0),-1);
                            if(action==0){prefs.edit().putInt("index",index).apply();Intent intent=new Intent(this,PlayerActivity.class);intent.putExtra("work_id",values.get(index));intent.putExtra("queue",true);startActivity(intent);return;}
                            if(action==3)values.remove(index);else{int target=action==1?index-1:index+1;if(target>=0&&target<values.size())java.util.Collections.swap(values,index,target);}
                            prefs.edit().putString("ids",new JSONArray(values).toString()).putInt("index",Math.max(0,values.indexOf(current))).apply();queueEditor();
                        }catch(Exception e){message(e.getMessage());}
                    }).show();
                }).setNeutralButton("循环模式",(d,w)->new AlertDialog.Builder(this).setTitle("循环模式").setSingleChoiceItems(new String[]{"播完停止","列表循环","单部循环"},prefs.getInt("repeat",0),(a,mode)->{prefs.edit().putInt("repeat",mode).apply();a.dismiss();}).show()).setNegativeButton("关闭",null).show();
            });
        }catch(Exception e){message(e.getMessage());}
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
        request(()->api.post("/api/queue",new JSONObject().put("kind",kind).put("q",query).put("favorite",favorites).put("tag",tagFilter).put("actor",actorFilter).put("year",yearFilter)),result->{
            JSONArray ids=result.getJSONArray("ids");if(ids.length()==0){message("当前范围没有媒体");return;}
            getSharedPreferences("queue",0).edit().putString("ids",ids.toString()).putInt("index",0).apply();
            Intent intent=new Intent(this,PlayerActivity.class);intent.putExtra("work_id",ids.getLong(0));intent.putExtra("queue",true);startActivity(intent);
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
