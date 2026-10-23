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
    private boolean favorites=false,recommended=false;
    private int offset=0,generation=0;
    private long detailId=0,renderedDetailId=0;
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
        });MediaStyle.button(connect,true,false,false);panel.addView(connect);
        panel.addView(text("地址使用电脑的局域网 IPv4，不能填手机自己的 localhost。服务关闭或电脑休眠时，客户端无法播放。",13,MUTED));
    }
    private void header(String title, boolean back) {
        LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(dp(12),dp(6),dp(8),dp(6));
        if(back){Button previous=button("",()->{detailId=0;showLibrary();});MediaStyle.icon(previous,"back",false);previous.setContentDescription("返回媒体库");row.addView(previous,new LinearLayout.LayoutParams(dp(48),dp(48)));}
        TextView brand=text(title,24,Color.WHITE);row.addView(brand,new LinearLayout.LayoutParams(0,dp(52),1));
        if(!back){Button collection=button("",()->{kind="";query="";favorites=true;recommended=false;tagFilter="";actorFilter="";yearFilter="";showLibrary();});MediaStyle.icon(collection,"heart",favorites);collection.setContentDescription("收藏");row.addView(collection,new LinearLayout.LayoutParams(dp(48),dp(48)));}
        Button more=button("",()->{});MediaStyle.icon(more,"more",false);more.setContentDescription("更多操作");more.setOnClickListener(view->{
            PopupMenu menu=new PopupMenu(this,view);menu.getMenu().add("随机播放");menu.getMenu().add("观影统计");menu.getMenu().add("切换连接");
            menu.setOnMenuItemClickListener(item->{switch(item.getTitle().toString()){case "随机播放":shuffle();break;case "观影统计":showStats();break;default:showConnection();}return true;});menu.show();
        });row.addView(more,new LinearLayout.LayoutParams(dp(48),dp(48)));root.addView(row);
    }
    private void showLibrary() {
        generation++;detailId=0;renderedDetailId=0;detailScroll=null;offset=0;base();header("Lumen",false);
        LinearLayout searchRow=new LinearLayout(this);searchRow.setPadding(dp(16),0,dp(16),0);
        EditText search=new EditText(this);search.setTextColor(Color.WHITE);search.setHintTextColor(MUTED);search.setHint("搜索媒体库");search.setSingleLine(true);search.setText(query);search.setImeOptions(EditorInfo.IME_ACTION_SEARCH);
        Runnable applySearch=()->{query=search.getText().toString().trim();recommended=false;showLibrary();};
        search.setOnEditorActionListener((view,action,event)->{if(action==EditorInfo.IME_ACTION_SEARCH){applySearch.run();return true;}return false;});
        search.setBackground(MediaStyle.surface(this,0xff202026,0xff3a3a44,8));search.setPadding(dp(12),0,dp(8),0);
        searchRow.addView(search,new LinearLayout.LayoutParams(0,dp(48),1));Button searchButton=button("",applySearch);MediaStyle.icon(searchButton,"search",false);searchButton.setContentDescription("搜索");LinearLayout.LayoutParams searchParams=new LinearLayout.LayoutParams(dp(48),dp(48));searchParams.setMargins(dp(6),0,dp(6),0);searchRow.addView(searchButton,searchParams);
        int count=(tagFilter.isEmpty()?0:1)+(actorFilter.isEmpty()?0:1)+(yearFilter.isEmpty()?0:1)+(favorites?1:0);
        Button filters=button("筛选"+(count>0?" · "+count:""),this::showFilters);MediaStyle.icon(filters,"filter",count>0);searchRow.addView(filters);root.addView(searchRow);
        ChipLayout selectedFilters=new ChipLayout(this);selectedFilters.setPadding(dp(16),dp(8),dp(16),0);
        if(!tagFilter.isEmpty())selectedFilters.addView(filterChip(tagFilter,()->{tagFilter="";showLibrary();}));
        if(!actorFilter.isEmpty())selectedFilters.addView(filterChip(actorFilter,()->{actorFilter="";showLibrary();}));
        if(!yearFilter.isEmpty())selectedFilters.addView(filterChip(yearFilter,()->{yearFilter="";showLibrary();}));
        if(favorites)selectedFilters.addView(filterChip("已收藏",()->{favorites=false;showLibrary();}));
        if(count>0)root.addView(selectedFilters);
        HorizontalScrollView nav=new HorizontalScrollView(this);nav.setHorizontalScrollBarEnabled(false);LinearLayout links=new LinearLayout(this);
        String[] names={"首页","电影","电视剧","VR电影","其他","收藏","为你推荐"};String[] types={"","movie","series","vr","other","",""};
        for(int i=0;i<names.length;i++) {
            final int choice=i;Button tab=button(names[i],()->{kind=types[choice];favorites=choice==5;recommended=choice==6;query="";tagFilter="";actorFilter="";yearFilter="";showLibrary();});
            boolean selected=(choice==5&&favorites&&kind.isEmpty())||(choice==6&&recommended)||(choice<5&&(!favorites||!kind.isEmpty())&&!recommended&&kind.equals(types[i]));
            tab.setBackground(MediaStyle.surface(this,selected?0xff15343f:Color.TRANSPARENT,0,20));if(selected)tab.setTextColor(0xff9cdef2);links.addView(tab);
        }
        nav.addView(links);root.addView(nav);
        ScrollView scroll=new ScrollView(this);content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);content.setPadding(dp(16),dp(10),dp(16),dp(16));scroll.addView(content);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        if(kind.isEmpty()&&!favorites&&!recommended&&query.isEmpty()&&tagFilter.isEmpty()&&actorFilter.isEmpty()&&yearFilter.isEmpty()) {
            content.addView(text("我的媒体",22,Color.WHITE));LinearLayout tiles=new LinearLayout(this);
            for(int i=1;i<=4;i++){final int choice=i;Button tile=button(names[i],()->{kind=types[choice];showLibrary();});tile.setBackgroundTintList(android.content.res.ColorStateList.valueOf(Color.rgb(35,35,35)));LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(85),1);p.setMargins(dp(3),0,dp(3),dp(12));tiles.addView(tile,p);}
            content.addView(tiles);
        }
        content.addView(text(recommended?"为你推荐":favorites?"收藏":query.isEmpty()?"媒体库":"搜索结果",22,Color.WHITE));
        posters=new ChipLayout(this);content.addView(posters);
        loadPage();
    }
    private String listPath() {
        String path=recommended?"/api/recommendations?":"/api/works?";
        return path+"offset="+offset+"&limit=30&kind="+kind+"&favorite="+favorites+"&q="+android.net.Uri.encode(query)+"&tag="+android.net.Uri.encode(tagFilter)+"&actor="+android.net.Uri.encode(actorFilter)+"&year="+android.net.Uri.encode(yearFilter);
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
        AutoCompleteTextView tag=filterInput(form,"标签",tagFilter),actor=filterInput(form,"演员",actorFilter),year=filterInput(form,"年份",yearFilter);
        year.setInputType(InputType.TYPE_CLASS_NUMBER);
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
            tagFilter=tag.getText().toString().trim();actorFilter=actor.getText().toString().trim();yearFilter=value;favorites=onlyFavorites[0];dialog.dismiss();showLibrary();
        });
        android.view.Window sheet=dialog.getWindow();if(sheet!=null){sheet.setBackgroundDrawable(MediaStyle.surface(this,0xff18181e,0xff3a3a44,18));sheet.setGravity(Gravity.BOTTOM);sheet.setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);sheet.setLayout(-1,-2);View sheetView=sheet.getDecorView();sheetView.post(()->{int available=getResources().getDisplayMetrics().heightPixels-dp(48);if(sheetView.getHeight()>available)sheet.setLayout(-1,available);});}
        dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(view->{
            tag.setText("");actor.setText("");year.setText("");onlyFavorites[0]=false;
            collection.setText("全部收藏状态");MediaStyle.icon(collection,"heart",false);MediaStyle.button(collection,false,false,true);
        });
        MediaStyle.button(dialog.getButton(AlertDialog.BUTTON_POSITIVE),true,false,false);
        MediaStyle.button(dialog.getButton(AlertDialog.BUTTON_NEGATIVE),false,false,false);MediaStyle.button(dialog.getButton(AlertDialog.BUTTON_NEUTRAL),false,false,false);
        request(()->api.get("/api/filters?kind="+android.net.Uri.encode(kind)),options->{
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
        TextView loading=text("正在读取媒体库…",14,MUTED);content.addView(loading);String path=listPath();
        request(()->api.get(path),result->{
            content.removeView(loading);JSONArray items=result.getJSONArray("items");int total=result.optInt("total");
            if(total==0)content.addView(text("暂无内容。请先在电脑端导入媒体，或调整搜索条件。",16,MUTED));
            int columns=getResources().getConfiguration().screenWidthDp>=650?4:2;
            int width=(getResources().getDisplayMetrics().widthPixels-dp(32))/columns;
            width=(getResources().getDisplayMetrics().widthPixels-dp(32)-(columns-1)*dp(6))/columns;
            for(int i=0;i<items.length();i++) {
                JSONObject work=items.getJSONObject(i);long id=work.getLong("id");
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
        int previousScroll=renderedDetailId==work.optLong("id")&&detailScroll!=null?detailScroll.getScrollY():0;
        detail=work;detailId=work.getLong("id");renderedDetailId=detailId;base();header("详情",true);
        ScrollView scroll=new ScrollView(this);LinearLayout page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);page.setPadding(dp(20),0,dp(20),dp(24));scroll.addView(page);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        detailScroll=scroll;scroll.post(()->scroll.scrollTo(0,previousScroll));
        LinearLayout hero=new LinearLayout(this);hero.setGravity(Gravity.TOP);hero.setPadding(0,dp(8),0,dp(16));
        ImageView poster=new ImageView(this);poster.setScaleType(ImageView.ScaleType.FIT_CENTER);poster.setBackground(MediaStyle.surface(this,0xff19191f,0,6));poster.setClipToOutline(true);poster.setContentDescription("海报："+work.optString("title"));
        hero.addView(poster,new LinearLayout.LayoutParams(dp(120),dp(180)));loadImage(poster,work.optString("cover",""));
        LinearLayout info=new LinearLayout(this);info.setOrientation(LinearLayout.VERTICAL);info.setPadding(dp(16),0,0,0);
        TextView title=text(work.optString("title"),24,Color.WHITE);title.setMaxLines(4);title.setEllipsize(android.text.TextUtils.TruncateAt.END);title.setContentDescription(work.optString("title"));
        title.setOnClickListener(view->title.setMaxLines(title.getMaxLines()==4?Integer.MAX_VALUE:4));info.addView(title);
        String category=work.optString("kind").equals("series")?"电视剧":work.optString("kind").equals("vr")?"VR 电影":work.optString("kind").equals("movie")?"电影":"视频";
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
            String tag=tags.optString(i);metadata.addView(button(tag,()->{tagFilter=tag;actorFilter="";yearFilter="";favorites=false;recommended=false;query="";kind="";showLibrary();}));
        }
        if(metadata.getChildCount()>0)page.addView(metadata);
        ChipLayout cast=new ChipLayout(this);cast.setPadding(0,0,0,dp(12));
        if(actors!=null&&actors.length()>0){TextView caption=text("主演",13,MUTED);caption.setMinHeight(dp(48));caption.setGravity(Gravity.CENTER_VERTICAL);cast.addView(caption);}
        if(actors!=null)for(int i=0;i<actors.length();i++){
            String actor=actors.optJSONObject(i)==null?"":actors.optJSONObject(i).optString("name");if(actor.isEmpty())continue;
            cast.addView(button(actor,()->{actorFilter=actor;tagFilter="";yearFilter="";favorites=false;recommended=false;query="";kind="";showLibrary();}));
        }
        if(cast.getChildCount()>0)page.addView(cast);
        page.addView(text(work.optString("overview","暂无简介"),15,MUTED));
        JSONArray files=work.getJSONArray("files");page.addView(text(work.optString("kind").equals("series")?"季与集":"视频文件",21,Color.WHITE));
        for(int i=0;i<files.length();i++) {
            JSONObject file=files.getJSONObject(i);long id=file.getLong("id");String name=file.optString("name");
            if(work.optString("kind").equals("series")&&!file.isNull("season")&&!file.isNull("episode"))name=String.format(java.util.Locale.ROOT,"S%02d E%02d  ·  ",file.optInt("season"),file.optInt("episode"))+name;
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
            status.setText(phase.equals("queued")?"等待电脑端下载…":phase.equals("importing")?"视频已保存，正在补充影视资料…":payload==null?"电脑端正在下载…":payload.optString("message","电脑端正在下载…"));
            downloadUpdates.postDelayed(()->pollDownload(task,workId,status,ticket),1000);
        });
    }
    private void markStyle(Button button,JSONObject work,String field,boolean active,boolean compact){
        String title=field.equals("favorite")?"收藏":"想看";
        button.setText(compact?"":(active?"已":"")+title);button.setContentDescription((active?"取消":"加入")+title);
        MediaStyle.button(button,false,active,field.equals("favorite"));MediaStyle.icon(button,field.equals("favorite")?"heart":"bookmark",active);
        if(compact)button.setBackground(MediaStyle.surface(this,0xe51a1a21,active?0xff985166:0xff45454c,24));
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
