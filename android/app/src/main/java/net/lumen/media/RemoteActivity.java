package net.lumen.media;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.*;
import org.json.JSONObject;
import org.json.JSONArray;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Controls only the connected PC; never opens a local decoder or offline download. */
public final class RemoteActivity extends Activity {
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final ExecutorService network=Executors.newSingleThreadExecutor();
    private Api api;private TextView title,status,time;private SeekBar seek,volume;
    private JSONObject state=new JSONObject();private String commandId="";private boolean active=false,dragging=false;private volatile boolean polling=false;private int generation=0;
    private final Runnable refresh=new Runnable(){public void run(){poll();if(active)handler.postDelayed(this,1500);}};
    private int dp(int value){return Math.round(value*getResources().getDisplayMetrics().density);}
    private TextView label(String text,int size){TextView view=new TextView(this);view.setText(text);view.setTextColor(Color.WHITE);view.setTextSize(size);view.setPadding(0,dp(10),0,dp(10));return view;}
    private Button button(String text,Runnable action){Button view=new Button(this);view.setText(text);MediaStyle.button(view,false,false,false);view.setOnClickListener(v->action.run());return view;}
    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);Connection connection=Connection.load(this);if(connection==null){finish();return;}api=new Api(connection);
        buildUi();
    }
    private void buildUi(){
        LinearLayout page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);page.setPadding(dp(20),dp(20),dp(20),dp(20));page.setBackgroundColor(Color.rgb(16,16,16));
        page.addView(button("返回媒体库",this::finish));page.addView(label("电脑遥控",26));title=label("正在连接电脑…",20);page.addView(title);
        status=label("请先在电脑设置 → 局域网 / Android 中启用手机遥控",14);page.addView(status);time=label("",14);page.addView(time);
        seek=new SeekBar(this);seek.setMax(10000);seek.setContentDescription("电脑播放进度");page.addView(seek);
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){public void onStartTrackingTouch(SeekBar bar){dragging=true;}public void onProgressChanged(SeekBar bar,int value,boolean user){}public void onStopTrackingTouch(SeekBar bar){dragging=false;send("seek",state.optDouble("duration")*bar.getProgress()/10000);}});
        LinearLayout actions=new LinearLayout(this);page.addView(actions);
        for(String text:new String[]{"−10 秒","播放 / 暂停","+10 秒"})actions.addView(button(text,()->{if(text.equals("播放 / 暂停"))send("toggle",null);else send("jump",text.startsWith("−")?-10:10);}),new LinearLayout.LayoutParams(0,-2,1));
        page.addView(label("电脑音量",16));volume=new SeekBar(this);volume.setMax(100);volume.setContentDescription("电脑音量");page.addView(volume);
        volume.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){public void onStartTrackingTouch(SeekBar bar){}public void onProgressChanged(SeekBar bar,int value,boolean user){}public void onStopTrackingTouch(SeekBar bar){send("volume",bar.getProgress());}});
        page.addView(button("静音 / 恢复",()->send("mute",!state.optBoolean("muted"))));page.addView(button("选择音轨",()->tracks(false)));page.addView(button("选择字幕",()->tracks(true)));
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.addView(page);setContentView(scroll);
        long work=getIntent().getLongExtra("work_id",0);if(work>0){try{JSONObject command=new JSONObject().put("action","open").put("work_id",work);long file=getIntent().getLongExtra("file_id",0);if(file>0)command.put("file_id",file);send(command);}catch(Exception error){status.setText(error.getMessage());}}
    }
    private void tracks(boolean subtitles){
        JSONArray entries=state.optJSONArray(subtitles?"subtitles":"audio");if(entries==null)entries=new JSONArray();
        final JSONArray tracks=entries;String[] names=new String[tracks.length()+1];names[0]="关闭";for(int i=0;i<tracks.length();i++)names[i+1]=tracks.optJSONObject(i).optString("name");
        new AlertDialog.Builder(this).setTitle(subtitles?"电脑字幕":"电脑音轨").setItems(names,(d,index)->send(subtitles?"subtitle":"audio",index==0?-1:tracks.optJSONObject(index-1).optInt("index"))).show();
    }
    private void send(String action,Object value){try{JSONObject command=new JSONObject().put("action",action);if(value!=null)command.put("value",value);send(command);}catch(Exception error){status.setText(error.getMessage());}}
    private void send(JSONObject command){network.execute(()->{try{JSONObject result=api.post("/api/remote",command);runOnUiThread(()->{if(!isDestroyed()){commandId=result.optString("command_id");status.setText("命令已发送，等待电脑执行");}});}catch(Exception error){runOnUiThread(()->{if(!isDestroyed())status.setText("遥控失败："+error.getMessage());});}});}
    private String clock(double seconds){long value=(long)Math.max(0,seconds);return String.format(java.util.Locale.ROOT,"%d:%02d:%02d",value/3600,value/60%60,value%60);}
    private void poll(){
        if(polling||!active)return;polling=true;int ticket=generation;
        network.execute(()->{try{JSONObject result=api.get("/api/remote");runOnUiThread(()->{
            if(!active||ticket!=generation)return;state=result;title.setText(result.optBoolean("active")?result.optString("title"):"电脑当前未播放影片");
            time.setText(clock(result.optDouble("position"))+" / "+clock(result.optDouble("duration")));if(!dragging)seek.setProgress((int)(result.optDouble("position")/Math.max(1,result.optDouble("duration"))*10000));
            if(!volume.isPressed())volume.setProgress(result.optInt("volume"));JSONObject last=result.optJSONObject("last_command");
            if(last!=null&&last.optString("id").equals(commandId)){status.setText(last.optBoolean("ok")?(result.optBoolean("playing")?"电脑正在播放":"电脑已暂停"):last.optString("error"));commandId="";}
            else if(commandId.isEmpty())status.setText(result.optBoolean("playing")?"电脑正在播放":"已连接电脑");
        });}catch(Exception error){runOnUiThread(()->{if(active&&ticket==generation)status.setText("请确认电脑已启动服务并启用手机遥控："+error.getMessage());});}finally{polling=false;}});
    }
    @Override protected void onStart(){super.onStart();if(api!=null&&title!=null){active=true;handler.post(refresh);}}
    @Override protected void onStop(){active=false;generation++;handler.removeCallbacks(refresh);super.onStop();}
    @Override protected void onDestroy(){active=false;generation++;handler.removeCallbacksAndMessages(null);network.shutdownNow();super.onDestroy();}
}
