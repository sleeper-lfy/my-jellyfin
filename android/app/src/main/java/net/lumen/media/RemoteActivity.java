package net.lumen.media;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Color;
import android.graphics.Bitmap;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.*;
import android.view.View;
import android.view.Gravity;
import android.content.res.ColorStateList;
import android.util.LruCache;
import com.google.android.material.button.MaterialButton;
import com.google.android.material.card.MaterialCardView;
import net.lumen.media.ui.theme.NativeActionTokens;
import org.json.JSONObject;
import org.json.JSONArray;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Controls only the connected PC; never opens a local decoder or offline download. */
public final class RemoteActivity extends Activity {
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final ExecutorService network=Executors.newSingleThreadExecutor();
    private Api api;private TextView title,status,time,powerStatus;private Button shutdown,cancelShutdown;private PlaybackIconButton togglePlayback;private SeekBar seek,volume;
    private final ImageRequests images=new ImageRequests(new LruCache<String,Bitmap>(4));private ImageView thumbnail;private long thumbnailFile=-1;
    private JSONObject state=new JSONObject();private String commandId="";private boolean active=false,dragging=false;private volatile boolean polling=false;private int generation=0;
    private final Runnable refresh=new Runnable(){public void run(){poll();if(active)handler.postDelayed(this,1500);}};
    private AlertDialog showDialog(AlertDialog.Builder builder){AlertDialog dialog=builder.show();MediaStyle.dialogActions(dialog);return dialog;}
    private int dp(int value){return Math.round(value*getResources().getDisplayMetrics().density);}
    private Button button(String text,Runnable action){Button view=MediaStyle.action(this);view.setText(text);MediaStyle.button(view,false,false,false);view.setOnClickListener(v->action.run());return view;}
    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);Connection connection=Connection.load(this);if(connection==null){finish();return;}api=new Api(connection);
        buildUi();
    }
    private void buildUi(){
        LinearLayout page=BiliAuxiliaryUi.column(this);page.setTag("remotePage");page.setPadding(dp(16),dp(8),dp(16),dp(24));page.setBackgroundColor(NativeActionTokens.background(true));page.setFitsSystemWindows(true);
        page.addView(BiliAuxiliaryUi.header(this,getString(R.string.bili_aux_remote_title),this::finish));
        MaterialCardView media=BiliAuxiliaryUi.card(this,"remoteCurrentMedia");LinearLayout mediaBody=BiliAuxiliaryUi.cardContent(media,12);
        TextView playing=BiliAuxiliaryUi.supporting(this,getString(R.string.bili_aux_remote_now_playing));playing.setTextColor(NativeActionTokens.primary(true));mediaBody.addView(playing);
        LinearLayout identity=BiliAuxiliaryUi.row(this);thumbnail=new ImageView(this);thumbnail.setImageDrawable(new MediaStyle.ArtworkPlaceholder());thumbnail.setScaleType(ImageView.ScaleType.CENTER_CROP);thumbnail.setContentDescription(getString(R.string.bili_aux_remote_thumbnail));identity.addView(thumbnail,new LinearLayout.LayoutParams(dp(104),dp(64)));
        LinearLayout details=BiliAuxiliaryUi.column(this);details.setPadding(dp(12),0,0,0);title=BiliAuxiliaryUi.body(this,"正在连接电脑…");title.setTypeface(android.graphics.Typeface.DEFAULT,android.graphics.Typeface.BOLD);title.setMaxLines(2);title.setEllipsize(android.text.TextUtils.TruncateAt.END);details.addView(title);
        status=BiliAuxiliaryUi.supporting(this,"请先在电脑设置 → 局域网 / Android 中启用手机遥控");status.setPadding(0,dp(6),0,0);status.setMaxLines(3);status.setEllipsize(android.text.TextUtils.TruncateAt.END);details.addView(status);identity.addView(details,new LinearLayout.LayoutParams(0,-2,1));BiliAuxiliaryUi.add(mediaBody,identity,12);
        LinearLayout timeline=BiliAuxiliaryUi.row(this);seek=new SeekBar(this);seek.setMax(10000);seek.setContentDescription("电脑播放进度");seek.setProgressTintList(ColorStateList.valueOf(NativeActionTokens.primary(true)));timeline.addView(seek,new LinearLayout.LayoutParams(0,dp(48),1));time=BiliAuxiliaryUi.supporting(this,"");time.setGravity(Gravity.END);time.setMaxLines(2);timeline.addView(time,new LinearLayout.LayoutParams(-2,-2));mediaBody.addView(timeline);BiliAuxiliaryUi.add(page,media,16);
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){public void onStartTrackingTouch(SeekBar bar){dragging=true;}public void onProgressChanged(SeekBar bar,int value,boolean user){}public void onStopTrackingTouch(SeekBar bar){dragging=false;send("seek",state.optDouble("duration")*bar.getProgress()/10000);}});
        LinearLayout actions=MediaStyle.actionRow(this);actions.setBaselineAligned(false);LinearLayout.LayoutParams transport=new LinearLayout.LayoutParams(-1,-2);transport.setMargins(0,dp(24),0,0);page.addView(actions,transport);
        PlaybackIconButton back=new PlaybackIconButton(this,"backward","电脑后退 10 秒");back.setOnClickListener(v->send("jump",-10));
        togglePlayback=new PlaybackIconButton(this,"play","电脑播放 / 暂停");togglePlayback.setOnClickListener(v->send("toggle",null));
        PlaybackIconButton forward=new PlaybackIconButton(this,"forward","电脑快进 10 秒");forward.setOnClickListener(v->send("jump",10));
        for(PlaybackIconButton control:new PlaybackIconButton[]{back,togglePlayback,forward})actions.addView(control,new LinearLayout.LayoutParams(0,dp(56),1));
        LinearLayout transportLabels=MediaStyle.actionRow(this);for(int resource:new int[]{R.string.bili_aux_remote_back_ten,R.string.bili_aux_remote_play_pause,R.string.bili_aux_remote_forward_ten}){TextView caption=BiliAuxiliaryUi.supporting(this,getString(resource));caption.setGravity(Gravity.CENTER);transportLabels.addView(caption,new LinearLayout.LayoutParams(0,-2,1));}page.addView(transportLabels);
        LinearLayout volumeRow=BiliAuxiliaryUi.row(this);volumeRow.addView(BiliAuxiliaryUi.icon(this,R.drawable.bili_aux_volume,null),new LinearLayout.LayoutParams(dp(24),dp(24)));volume=new SeekBar(this);volume.setMax(100);volume.setContentDescription("电脑音量");volume.setProgressTintList(ColorStateList.valueOf(NativeActionTokens.primary(true)));volumeRow.addView(volume,new LinearLayout.LayoutParams(0,dp(48),1));volumeRow.addView(BiliAuxiliaryUi.icon(this,R.drawable.bili_aux_volume,null),new LinearLayout.LayoutParams(dp(24),dp(24)));BiliAuxiliaryUi.add(page,volumeRow,24);
        volume.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){public void onStartTrackingTouch(SeekBar bar){}public void onProgressChanged(SeekBar bar,int value,boolean user){}public void onStopTrackingTouch(SeekBar bar){send("volume",bar.getProgress());}});
        LinearLayout mediaActions=MediaStyle.actionRow(this);mediaActions.setTag("remoteMediaActions");LinearLayout.LayoutParams mediaGroup=new LinearLayout.LayoutParams(-1,-2);mediaGroup.setMargins(0,dp(16),0,dp(16));page.addView(mediaActions,mediaGroup);
        Button mute=button("静音 / 恢复",()->send("mute",!state.optBoolean("muted"))),audio=button("选择音轨",()->tracks(false)),subtitle=button("选择字幕",()->tracks(true));Button[] quick={mute,audio,subtitle};int[] icons={R.drawable.bili_aux_volume,R.drawable.bili_aux_audio,R.drawable.bili_aux_subtitle};for(int index=0;index<quick.length;index++){BiliAuxiliaryUi.quickAction(quick[index],icons[index]);mediaActions.addView(quick[index],new LinearLayout.LayoutParams(0,-2,1));}
        page.addView(BiliAuxiliaryUi.section(this,getString(R.string.bili_aux_remote_power)));MaterialCardView power=BiliAuxiliaryUi.card(this,"remotePowerCard");LinearLayout powerBody=BiliAuxiliaryUi.cardContent(power,12);LinearLayout powerInfo=BiliAuxiliaryUi.row(this);powerInfo.addView(BiliAuxiliaryUi.icon(this,R.drawable.bili_aux_power,null),new LinearLayout.LayoutParams(dp(24),dp(24)));powerStatus=BiliAuxiliaryUi.supporting(this,"正在读取电脑关机权限…");LinearLayout.LayoutParams powerText=new LinearLayout.LayoutParams(0,-2,1);powerText.setMarginStart(dp(12));powerInfo.addView(powerStatus,powerText);powerBody.addView(powerInfo);BiliAuxiliaryUi.add(page,power,0);
        LinearLayout powerActions=MediaStyle.actionColumn(this);powerActions.setTag("remotePowerActions");BiliAuxiliaryUi.add(powerBody,powerActions,12);
        shutdown=button("关闭电脑",this::confirmShutdown);MediaStyle.danger(shutdown);BiliAuxiliaryUi.textAction(shutdown,true);shutdown.setGravity(Gravity.START|Gravity.CENTER_VERTICAL);((MaterialButton)shutdown).setIconResource(R.drawable.bili_aux_power);shutdown.setEnabled(false);powerActions.addView(shutdown,new LinearLayout.LayoutParams(-1,-2));
        cancelShutdown=button("取消电脑关机",()->send("shutdown_cancel",null));BiliAuxiliaryUi.textAction(cancelShutdown,false);cancelShutdown.setGravity(Gravity.START|Gravity.CENTER_VERTICAL);cancelShutdown.setVisibility(android.view.View.GONE);powerActions.addView(cancelShutdown,new LinearLayout.LayoutParams(-1,-2));
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.addView(page);setContentView(scroll);
        long work=getIntent().getLongExtra("work_id",0);if(work>0){try{JSONObject command=new JSONObject().put("action","open").put("work_id",work);long file=getIntent().getLongExtra("file_id",0);if(file>0)command.put("file_id",file);send(command);}catch(Exception error){status.setText(error.getMessage());}}
    }
    private void updateThumbnail(){
        long file=state.optBoolean("active")?state.optLong("file_id",0):0;if(file==thumbnailFile)return;thumbnailFile=file;images.cancelPage();thumbnail.setImageDrawable(new MediaStyle.ArtworkPlaceholder());
        if(file>0)images.load(api,thumbnail,"/api/files/"+file+"/thumbnail");else thumbnail.setTag(null);
    }
    private void confirmShutdown(){
        if(!state.optBoolean("shutdown_supported")||!state.optBoolean("shutdown_allowed")){powerStatus.setText("请更新 Windows 电脑端，并在设置 → 局域网 / Android 中允许手机关机。");return;}
        showDialog(new AlertDialog.Builder(this).setTitle("关闭当前连接的电脑？")
            .setMessage("电脑将在 15 秒倒计时后请求 Windows 正常关机。请先保存其他程序中的文件；倒计时期间可在手机或电脑上取消。不会强制关闭未保存的程序。")
            .setPositiveButton("确认关机",(dialog,which)->{try{send(new JSONObject().put("action","shutdown").put("confirm",true));}catch(Exception error){status.setText(error.getMessage());}})
            .setNegativeButton("取消",null));
    }
    private void powerState(){
        int pending=state.optInt("shutdown_pending");boolean running=state.optBoolean("shutdown_running"),supported=state.optBoolean("shutdown_supported"),allowed=state.optBoolean("shutdown_allowed");
        shutdown.setEnabled(supported&&allowed&&pending==0&&!running);cancelShutdown.setVisibility(pending>0?android.view.View.VISIBLE:android.view.View.GONE);
        powerStatus.setText(!state.optString("shutdown_error").isEmpty()?state.optString("shutdown_error"):pending>0?"电脑将在 "+pending+" 秒后请求关机，可点击下方取消。":running?"正在请求 Windows 关机…":state.optBoolean("shutdown_requested")?"Windows 已收到关机请求。如有未保存的文件，请在电脑上处理。":!supported?"关机需要新版 Windows 电脑端。":!allowed?"请在电脑设置 → 局域网 / Android 中允许手机关机。":"已允许手机请求电脑关机。倒计时 15 秒，可取消。");
    }
    private void tracks(boolean subtitles){
        JSONArray entries=state.optJSONArray(subtitles?"subtitles":"audio");if(entries==null)entries=new JSONArray();
        final JSONArray tracks=entries;String[] names=new String[tracks.length()+1];names[0]="关闭";for(int i=0;i<tracks.length();i++)names[i+1]=tracks.optJSONObject(i).optString("name");
        showDialog(new AlertDialog.Builder(this).setTitle(subtitles?"电脑字幕":"电脑音轨").setItems(names,(d,index)->send(subtitles?"subtitle":"audio",index==0?-1:tracks.optJSONObject(index-1).optInt("index"))));
    }
    private void send(String action,Object value){try{JSONObject command=new JSONObject().put("action",action);if(value!=null)command.put("value",value);send(command);}catch(Exception error){status.setText(error.getMessage());}}
    private void send(JSONObject command){network.execute(()->{try{JSONObject result=api.post("/api/remote",command);runOnUiThread(()->{if(!isDestroyed()){commandId=result.optString("command_id");status.setText("命令已发送，等待电脑执行");}});}catch(Exception error){runOnUiThread(()->{if(!isDestroyed())status.setText("遥控失败："+error.getMessage());});}});}
    private String clock(double seconds){long value=(long)Math.max(0,seconds);return String.format(java.util.Locale.ROOT,"%d:%02d:%02d",value/3600,value/60%60,value%60);}
    private void poll(){
        if(polling||!active)return;polling=true;int ticket=generation;
        network.execute(()->{try{JSONObject result=api.get("/api/remote");runOnUiThread(()->{
            if(!active||ticket!=generation)return;state=result;powerState();updateThumbnail();togglePlayback.setSymbol(result.optBoolean("playing")?"pause":"play",result.optBoolean("playing")?"暂停电脑播放":"开始电脑播放");title.setText(result.optBoolean("active")?result.optString("title"):"电脑当前未播放影片");
            time.setText(clock(result.optDouble("position"))+" / "+clock(result.optDouble("duration")));if(!dragging)seek.setProgress((int)(result.optDouble("position")/Math.max(1,result.optDouble("duration"))*10000));
            if(!volume.isPressed())volume.setProgress(result.optInt("volume"));JSONObject last=result.optJSONObject("last_command");
            if(last!=null&&last.optString("id").equals(commandId)){status.setText(last.optBoolean("ok")?(last.optString("action").startsWith("shutdown")?"电源命令已执行，请查看关机状态":result.optBoolean("playing")?"电脑正在播放":"电脑已暂停"):last.optString("error"));commandId="";}
            else if(commandId.isEmpty())status.setText(result.optBoolean("playing")?"电脑正在播放":"已连接电脑");
        });}catch(Exception error){runOnUiThread(()->{if(active&&ticket==generation)status.setText(state.optBoolean("shutdown_requested")?"关机请求已执行，电脑连接已断开":"请确认电脑已启动服务并启用手机遥控："+error.getMessage());});}finally{polling=false;}});
    }
    @Override protected void onStart(){super.onStart();if(api!=null&&title!=null){active=true;images.restore(api,thumbnail);handler.post(refresh);}}
    @Override protected void onStop(){active=false;generation++;handler.removeCallbacks(refresh);images.cancelPage();super.onStop();}
    @Override protected void onDestroy(){active=false;generation++;handler.removeCallbacksAndMessages(null);images.close();network.shutdownNow();super.onDestroy();}
}
