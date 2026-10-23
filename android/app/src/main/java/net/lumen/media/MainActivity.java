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
    private final ExecutorService network=Executors.newFixedThreadPool(4);
    private final LruCache<String,Bitmap> pictures=new LruCache<String,Bitmap>(24*1024) {
        @Override protected int sizeOf(String key,Bitmap image){return image.getByteCount()/1024;}
    };
    private Api api;
    private LinearLayout root,content;
    private String kind="",query="",tagFilter="",actorFilter="",yearFilter="";
    private boolean favorites=false,recommended=false;
    private int offset=0,generation=0;
    private long detailId=0;
    private boolean returned=false;
    private JSONObject detail;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
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
        if(detailId>0) {detailId=0;showLibrary();}else super.onBackPressed();
    }
    @Override protected void onDestroy() {network.shutdownNow();super.onDestroy();}
    private int dp(float value){return Math.round(value*getResources().getDisplayMetrics().density);}
    private TextView text(String value,int size,int color) {
        TextView view=new TextView(this);view.setText(value);view.setTextSize(size);view.setTextColor(color);view.setPadding(0,dp(6),0,dp(6));return view;
    }
    private Button button(String title,Runnable action) {
        Button button=new Button(this);button.setText(title);button.setTextColor(Color.WHITE);button.setAllCaps(false);button.setTextSize(14);
        button.setOnClickListener(v->action.run());return button;
    }
    private void base() {
        root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(BG);root.setFitsSystemWindows(true);setContentView(root);
    }
    private void message(String value){if(!isDestroyed())Toast.makeText(this,value,Toast.LENGTH_LONG).show();}
    interface Work {JSONObject run() throws Exception;}
    interface Result {void accept(JSONObject result) throws Exception;}
    private void request(Work work,Result result) {
        final int ticket=generation;
        network.execute(()->{
            try {JSONObject value=work.run();runOnUiThread(()->{if(isDestroyed() || ticket!=generation)return;try{result.accept(value);}catch(Exception e){message(e.getMessage());}});}
            catch(Exception e){runOnUiThread(()->{if(!isDestroyed() && ticket==generation)message("连接失败："+e.getMessage());});}
        });
    }
    private void showConnection() {
        generation++;detailId=0;api=null;base();
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
        });connect.setBackgroundTintList(android.content.res.ColorStateList.valueOf(BLUE));panel.addView(connect);
        panel.addView(text("地址使用电脑的局域网 IPv4，不能填手机自己的 localhost。服务关闭或电脑休眠时，客户端无法播放。",13,MUTED));
    }
    private void header(String title, boolean back) {
        LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(dp(12),dp(6),dp(8),dp(6));
        if(back)row.addView(button("‹",()->{detailId=0;showLibrary();}),new LinearLayout.LayoutParams(dp(48),dp(48)));
        TextView brand=text(title,24,Color.WHITE);row.addView(brand,new LinearLayout.LayoutParams(0,dp(52),1));
        Button more=button("⋮",()->{});more.setOnClickListener(view->{
            PopupMenu menu=new PopupMenu(this,view);menu.getMenu().add("随机播放");menu.getMenu().add("观影统计");menu.getMenu().add("切换连接");
            menu.setOnMenuItemClickListener(item->{switch(item.getTitle().toString()){case "随机播放":shuffle();break;case "观影统计":showStats();break;default:showConnection();}return true;});menu.show();
        });row.addView(more,new LinearLayout.LayoutParams(dp(48),dp(48)));root.addView(row);
    }
    private void showLibrary() {
        generation++;detailId=0;offset=0;base();header("Lumen",false);
        LinearLayout searchRow=new LinearLayout(this);searchRow.setPadding(dp(16),0,dp(16),0);
        EditText search=new EditText(this);search.setTextColor(Color.WHITE);search.setHintTextColor(MUTED);search.setHint("搜索影片、别名、文件夹");search.setSingleLine(true);search.setText(query);search.setImeOptions(EditorInfo.IME_ACTION_SEARCH);
        Runnable applySearch=()->{query=search.getText().toString().trim();recommended=false;showLibrary();};
        search.setOnEditorActionListener((view,action,event)->{if(action==EditorInfo.IME_ACTION_SEARCH){applySearch.run();return true;}return false;});
        searchRow.addView(search,new LinearLayout.LayoutParams(0,dp(52),1));searchRow.addView(button("搜索",applySearch));searchRow.addView(button("筛选",this::showFilters));root.addView(searchRow);
        if(!tagFilter.isEmpty()||!actorFilter.isEmpty()||!yearFilter.isEmpty())root.addView(button("筛选中："+tagFilter+"  "+actorFilter+"  "+yearFilter,this::showFilters));
        HorizontalScrollView nav=new HorizontalScrollView(this);nav.setHorizontalScrollBarEnabled(false);LinearLayout links=new LinearLayout(this);
        String[] names={"首页","电影","电视剧","VR电影","其他","收藏","为你推荐"};String[] types={"","movie","series","vr","other","",""};
        for(int i=0;i<names.length;i++) {
            final int choice=i;Button tab=button(names[i],()->{kind=types[choice];favorites=choice==5;recommended=choice==6;query="";tagFilter="";actorFilter="";yearFilter="";showLibrary();});
            boolean selected=(choice==5&&favorites)||(choice==6&&recommended)||(choice<5&&!favorites&&!recommended&&kind.equals(types[i]));
            if(selected)tab.setTextColor(BLUE);links.addView(tab);
        }
        nav.addView(links);root.addView(nav);
        ScrollView scroll=new ScrollView(this);content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);content.setPadding(dp(16),dp(10),dp(16),dp(16));scroll.addView(content);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        if(kind.isEmpty()&&!favorites&&!recommended&&query.isEmpty()&&tagFilter.isEmpty()&&actorFilter.isEmpty()&&yearFilter.isEmpty()) {
            content.addView(text("我的媒体",22,Color.WHITE));LinearLayout tiles=new LinearLayout(this);
            for(int i=1;i<=4;i++){final int choice=i;Button tile=button(names[i],()->{kind=types[choice];showLibrary();});tile.setBackgroundTintList(android.content.res.ColorStateList.valueOf(Color.rgb(35,35,35)));LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(85),1);p.setMargins(dp(3),0,dp(3),dp(12));tiles.addView(tile,p);}
            content.addView(tiles);
        }
        content.addView(text(recommended?"为你推荐":favorites?"收藏":query.isEmpty()?"媒体库":"搜索结果",22,Color.WHITE));
        loadPage();
    }
    private String listPath() {
        String path=recommended?"/api/recommendations?":"/api/works?";
        return path+"offset="+offset+"&limit=30&kind="+kind+"&favorite="+favorites+"&q="+android.net.Uri.encode(query)+"&tag="+android.net.Uri.encode(tagFilter)+"&actor="+android.net.Uri.encode(actorFilter)+"&year="+android.net.Uri.encode(yearFilter);
    }
    private AutoCompleteTextView filterInput(LinearLayout form,String label,String value){
        form.addView(text(label,15,MUTED));
        AutoCompleteTextView input=new SearchDropdown(this);input.setSingleLine(true);input.setTextColor(Color.WHITE);input.setHintTextColor(MUTED);
        input.setHint("输入搜索或下拉选择；留空不限");input.setText(value);
        LinearLayout row=new LinearLayout(this);row.addView(input,new LinearLayout.LayoutParams(0,dp(56),1));
        row.addView(button("⌄",()->{input.requestFocus();input.showDropDown();}),new LinearLayout.LayoutParams(dp(52),dp(56)));form.addView(row);
        return input;
    }
    private void showFilters(){
        LinearLayout form=new LinearLayout(this);form.setOrientation(LinearLayout.VERTICAL);form.setPadding(dp(20),dp(12),dp(20),dp(12));
        AutoCompleteTextView tag=filterInput(form,"标签",tagFilter),actor=filterInput(form,"演员",actorFilter),year=filterInput(form,"年份",yearFilter);
        year.setInputType(InputType.TYPE_CLASS_NUMBER);
        TextView status=text("正在读取完整媒体库中的筛选选项…",13,MUTED);form.addView(status);
        ScrollView scroll=new ScrollView(this);scroll.addView(form);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("筛选媒体库").setView(scroll)
            .setPositiveButton("应用",null).setNegativeButton("取消",null).setNeutralButton("清空",(d,which)->{tagFilter="";actorFilter="";yearFilter="";showLibrary();}).create();
        dialog.setOnShowListener(ignored->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view->{
            String value=year.getText().toString().trim();
            if(!value.isEmpty()&&(!value.matches("[0-9]{4}")||Integer.parseInt(value)<1800||Integer.parseInt(value)>2200)){year.setError("请输入 1800–2200 的年份");return;}
            tagFilter=tag.getText().toString().trim();actorFilter=actor.getText().toString().trim();yearFilter=value;dialog.dismiss();showLibrary();
        }));dialog.show();
        request(()->api.get("/api/filters?kind="+android.net.Uri.encode(kind)),options->{
            if(!dialog.isShowing())return;
            AutoCompleteTextView[] inputs={tag,actor,year};String[] keys={"tags","actors","years"};
            for(int i=0;i<inputs.length;i++){
                JSONArray values=options.getJSONArray(keys[i]);java.util.ArrayList<String> choices=new java.util.ArrayList<>();
                for(int j=0;j<values.length();j++)choices.add(values.optString(j));
                inputs[i].setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_dropdown_item_1line,choices));
            }
            status.setText("输入文字缩小候选范围，点击 ⌄ 查看下拉列表。多个条件同时生效。");
        });
    }
    private void loadPage() {
        TextView loading=text("正在读取媒体库…",14,MUTED);content.addView(loading);String path=listPath();
        request(()->api.get(path),result->{
            content.removeView(loading);JSONArray items=result.getJSONArray("items");int total=result.optInt("total");
            if(total==0)content.addView(text("暂无内容。请先在电脑端导入媒体，或调整搜索条件。",16,MUTED));
            int columns=getResources().getConfiguration().screenWidthDp>=650?4:2;
            int width=(getResources().getDisplayMetrics().widthPixels-dp(32))/columns;
            LinearLayout row=null;
            for(int i=0;i<items.length();i++) {
                if(i%columns==0){row=new LinearLayout(this);content.addView(row);}
                JSONObject work=items.getJSONObject(i);LinearLayout card=new LinearLayout(this);card.setOrientation(LinearLayout.VERTICAL);card.setPadding(dp(5),dp(6),dp(5),dp(12));
                ImageView poster=new ImageView(this);poster.setBackgroundColor(Color.rgb(38,38,38));poster.setScaleType(ImageView.ScaleType.CENTER_CROP);card.addView(poster,new LinearLayout.LayoutParams(-1,(int)((width-dp(10))*1.5)));
                loadImage(poster,work.optString("cover",""));
                TextView title=text(work.optString("title"),15,Color.WHITE);title.setMaxLines(2);title.setGravity(Gravity.CENTER);card.addView(title);
                TextView meta=text((work.isNull("year")?"":work.optString("year"))+(work.isNull("rating")?"":"  ★ "+work.optInt("rating")),12,MUTED);meta.setGravity(Gravity.CENTER);card.addView(meta);
                long id=work.getLong("id");card.setOnClickListener(view->openDetail(id));poster.setOnClickListener(view->openDetail(id));row.addView(card,new LinearLayout.LayoutParams(width,-2));
            }
            offset+=items.length();
            if(offset<total) {Button more=button("加载更多  ·  "+offset+" / "+total,()->{});more.setOnClickListener(v->{content.removeView(more);loadPage();});content.addView(more);}
        });
    }
    private void loadImage(ImageView view,String path) {
        if(path.isEmpty()||path.equals("null"))return;
        String key=api.connection.base+path;view.setTag(key);Bitmap cached=pictures.get(key);if(cached!=null){view.setImageBitmap(cached);return;}
        Api client=api;network.execute(()->{try{Bitmap image=client.image(path);if(image==null)return;pictures.put(key,image);runOnUiThread(()->{if(!isDestroyed()&&key.equals(view.getTag()))view.setImageBitmap(image);});}catch(Exception ignored){/* A missing cover does not prevent browsing or playback. */}});
    }
    private void openDetail(long id) {
        generation++;detailId=id;
        request(()->api.get("/api/works/"+id),this::renderDetail);
    }
    private void renderDetail(JSONObject work) throws Exception {
        detail=work;detailId=work.getLong("id");base();header("详情",true);
        ScrollView scroll=new ScrollView(this);LinearLayout page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);page.setPadding(dp(20),0,dp(20),dp(24));scroll.addView(page);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        ImageView poster=new ImageView(this);poster.setScaleType(ImageView.ScaleType.CENTER_CROP);page.addView(poster,new LinearLayout.LayoutParams(-1,dp(260)));loadImage(poster,work.optString("cover",""));
        page.addView(text(work.optString("title"),27,Color.WHITE));page.addView(text((work.isNull("year")?"":work.optString("year"))+"  ·  "+work.optInt("file_count")+" 个视频",14,MUTED));
        Button play=button("▶  继续播放",()->startPlayer(work.optLong("resume_file_id"),false));play.setEnabled(work.optInt("file_count")>0);play.setBackgroundTintList(android.content.res.ColorStateList.valueOf(BLUE));page.addView(play);
        LinearLayout personal=new LinearLayout(this);
        personal.addView(button(work.optInt("favorite")==1?"已收藏":"收藏",()->personal("favorite",work.optInt("favorite")!=1)));
        personal.addView(button(work.optInt("watchlist")==1?"已想看":"想看",()->personal("watchlist",work.optInt("watchlist")!=1)));
        personal.addView(button(work.isNull("rating")?"评分":"★ "+work.optInt("rating"),()->{
            String[] scores={"未评分","1","2","3","4","5","6","7","8","9","10"};new AlertDialog.Builder(this).setTitle("个人评分").setItems(scores,(dialog,index)->personal("rating",index==0?JSONObject.NULL:index)).show();
        }));page.addView(personal);
        page.addView(text(work.optString("overview","暂无简介"),15,MUTED));
        JSONArray files=work.getJSONArray("files");page.addView(text(work.optString("kind").equals("series")?"季与集":"视频文件",21,Color.WHITE));
        for(int i=0;i<files.length();i++) {
            JSONObject file=files.getJSONObject(i);long id=file.getLong("id");String name=file.optString("name");
            if(work.optString("kind").equals("series"))name=String.format(java.util.Locale.ROOT,"S%02d E%02d  ·  ",file.optInt("season"),file.optInt("episode"))+name;
            page.addView(button(name+"  ·  "+(int)(file.optDouble("duration")/60)+" 分钟",()->startPlayer(id,false)));
            if(!file.optString("overview").isEmpty())page.addView(text(file.optString("overview"),14,MUTED));
            JSONArray episodeStills=file.optJSONArray("stills");
            if(episodeStills!=null&&episodeStills.length()>0){
                HorizontalScrollView shots=new HorizontalScrollView(this);LinearLayout images=new LinearLayout(this);
                for(int j=0;j<episodeStills.length();j++){
                    ImageView shot=new ImageView(this);shot.setScaleType(ImageView.ScaleType.FIT_CENTER);
                    images.addView(shot,new LinearLayout.LayoutParams(dp(240),dp(150)));loadImage(shot,episodeStills.optString(j));
                }
                shots.addView(images);page.addView(shots);
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
                image.setOnClickListener(v->{loadImage(expanded,path);expanded.setVisibility(View.VISIBLE);});
            }
            gallery.addView(images);page.addView(gallery);page.addView(expanded,new LinearLayout.LayoutParams(-1,dp(300)));
        }
        JSONArray downloads=work.optJSONArray("download_url");
        if(downloads!=null&&downloads.length()>0)page.addView(text("下载资源",21,Color.WHITE));
        if(downloads!=null)for(int i=0;i<downloads.length();i++){
            JSONObject entry=downloads.optJSONObject(i);if(entry==null)continue;String url=entry.optString("url");
            page.addView(button(entry.optString("description","下载"),()->{
                try{if(url.startsWith("https://")||url.startsWith("http://"))DirectDownload.start(this,url);
                    else startActivity(new Intent(Intent.ACTION_VIEW,android.net.Uri.parse(url)));}
                catch(android.content.ActivityNotFoundException error){Toast.makeText(this,"请安装支持该链接的下载器",Toast.LENGTH_LONG).show();}
            }));
        }
        JSONArray sources=work.optJSONArray("sources");
        if(sources!=null&&sources.length()>0)page.addView(text("信息来源",21,Color.WHITE));
        if(sources!=null)for(int i=0;i<sources.length();i++) {
            JSONObject source=sources.getJSONObject(i);String url=source.optString("url");
            page.addView(button(source.optString("site")+"  ↗",()->{PrivateBrowserActivity.open(this,url);}));
        }
    }
    private void personal(String field,Object value) {
        long id=detailId;
        request(()->api.post("/api/works/"+id+"/personal",new JSONObject().put(field,value)),result->openDetail(id));
    }
    private void startPlayer(long fileId,boolean queue) {
        if(fileId<=0){message("没有可播放的视频");return;}
        Intent intent=new Intent(this,PlayerActivity.class);intent.putExtra("work_id",detailId);intent.putExtra("file_id",fileId);intent.putExtra("queue",queue);startActivity(intent);
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
