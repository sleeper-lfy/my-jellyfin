package net.lumen.media;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.WindowManager;
import android.widget.*;
import org.videolan.libvlc.LibVLC;
import org.videolan.libvlc.Media;
import org.videolan.libvlc.MediaPlayer;
import org.videolan.libvlc.util.VLCVideoLayout;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.Collections;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

public final class PlayerActivity extends Activity {
    private final ExecutorService network=Executors.newSingleThreadExecutor();
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final AtomicBoolean pendingTick=new AtomicBoolean(false);
    private Api api;
    private MediaPlayer player;
    private LibVLC vlc;
    private PlaybackBridge bridge;
    private VLCVideoLayout video;
    private VrVideoView vrVideo;
    private boolean vrEnabled=false, vrFish=false, vrHeadset=false, vrSwap=false, vrTracking=true, vrImmersive=false;
    private final ArrayList<View> chrome=new ArrayList<>();
    private SeekBar seek;
    private TextView time;
    private Button pause;
    private boolean software=false,dragging=false,ready=false,buffering=false;
    private long lastPosition=0;
    private android.media.AudioManager audio;
    private android.media.AudioFocusRequest audioFocus;
    private TextView title,status;
    private JSONObject work,file;
    private JSONArray subtitles=new JSONArray();
    private String session;
    private long sequence=0,resumeMs=0,desiredWork=0,desiredFile=0;
    private int generation=0,seekGuard=0;
    private boolean started=false,queueMode=false,ending=false;
    private final Runnable heartbeat=new Runnable(){@Override public void run(){updateProgress();tick(false,false);handler.postDelayed(this,1000);}};

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        Connection connection=Connection.load(this);
        if(connection==null){finish();return;}api=new Api(connection);
        LinearLayout layout=new LinearLayout(this);layout.setFitsSystemWindows(true);layout.setOrientation(LinearLayout.VERTICAL);layout.setBackgroundColor(Color.BLACK);
        title=new TextView(this);title.setText("正在载入…");title.setTextColor(Color.WHITE);title.setTextSize(18);title.setPadding(16,16,16,12);layout.addView(title);
        android.content.SharedPreferences prefs=getSharedPreferences("playback",0);
        vrFish=prefs.getBoolean("vr_fish",false);vrHeadset=prefs.getBoolean("vr_headset",false);
        vrSwap=prefs.getBoolean("vr_swap",false);vrTracking=prefs.getBoolean("vr_tracking",true);
        FrameLayout viewport=new FrameLayout(this);
        video=new VLCVideoLayout(this);viewport.addView(video,new FrameLayout.LayoutParams(-1,-1));
        vrVideo=new VrVideoView(this,new VrVideoView.Listener(){
            public void ready(){if(started&&vrEnabled)startPlayback();}
            public void lost(){if(vrEnabled)stopPlayback(false);}
            public void failed(String reason){status.setText("VR 渲染失败："+reason);setVrEnabled(false);}
        });
        vrVideo.setFov(prefs.getInt("vr_fov",90));
        vrVideo.setVisibility(View.GONE);viewport.addView(vrVideo,new FrameLayout.LayoutParams(-1,-1));
        Button vrControls=new Button(this);vrControls.setText("控制");
        vrControls.setOnClickListener(v->setVrImmersive(!vrImmersive));
        FrameLayout.LayoutParams controlPosition=new FrameLayout.LayoutParams(-2,-2,android.view.Gravity.TOP|android.view.Gravity.END);
        viewport.addView(vrControls,controlPosition);vrControls.setVisibility(View.GONE);
        vrVideo.setTag(vrControls);
        layout.addView(viewport,new LinearLayout.LayoutParams(-1,0,1));
        seek=new SeekBar(this);seek.setMax(10000);layout.addView(seek);
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){
            public void onStartTrackingTouch(SeekBar bar){dragging=true;}
            public void onProgressChanged(SeekBar bar,int value,boolean user){}
            public void onStopTrackingTouch(SeekBar bar){dragging=false;if(player!=null && player.isSeekable()){seekGuard=2;player.setTime(durationMs()*bar.getProgress()/10000);tick(false,false);}}
        });
        time=new TextView(this);time.setTextColor(Color.LTGRAY);layout.addView(time);
        LinearLayout playback=new LinearLayout(this);
        pause=addButton(playback,"暂停",()->{if(player!=null){if(player.isPlaying())player.pause();else if(focus())player.play();tick(false,false);}});
        addButton(playback,"音轨",()->tracks(false));addButton(playback,"字幕",()->tracks(true));
        addButton(playback,"解码",this::decoder);addButton(playback,"VR",this::vrSettings);layout.addView(playback);
        audio=(android.media.AudioManager)getSystemService(AUDIO_SERVICE);
        audioFocus=new android.media.AudioFocusRequest.Builder(android.media.AudioManager.AUDIOFOCUS_GAIN)
            .setAudioAttributes(new android.media.AudioAttributes.Builder().setUsage(android.media.AudioAttributes.USAGE_MEDIA).setContentType(android.media.AudioAttributes.CONTENT_TYPE_MOVIE).build())
            .setOnAudioFocusChangeListener(change->{if(change<0 && player!=null){player.pause();tick(false,false);}},handler).build();
        setVolumeControlStream(android.media.AudioManager.STREAM_MUSIC);
        LinearLayout controls=new LinearLayout(this);
        addButton(controls,"返回",this::finish);
        addButton(controls,"下一集",()->nextEpisode(false));
        addButton(controls,"下一作品",()->nextWork(false));
        layout.addView(controls);
        chrome.add(title);chrome.add(seek);chrome.add(time);chrome.add(playback);chrome.add(controls);
        status=new TextView(this);status.setTextColor(Color.LTGRAY);status.setPadding(16,6,16,14);layout.addView(status);chrome.add(status);setContentView(layout);
        queueMode=getIntent().getBooleanExtra("queue",false);
        desiredWork=getIntent().getLongExtra("work_id",0);desiredFile=getIntent().getLongExtra("file_id",0);
    }
    private Button addButton(LinearLayout layout,String label,Runnable action) {
        Button button=new Button(this);button.setText(label);button.setAllCaps(false);button.setOnClickListener(v->action.run());layout.addView(button,new LinearLayout.LayoutParams(0,-2,1));return button;
    }
    private void error(Exception exception) {
        runOnUiThread(()->{if(!isDestroyed()){status.setText("无法播放："+exception.getMessage());new AlertDialog.Builder(this).setTitle("播放失败").setMessage(exception.getMessage()).setPositiveButton("返回",(d,w)->finish()).setNegativeButton("关闭",null).show();}});
    }
    private void load(long workId,long fileId) {
        desiredWork=workId;desiredFile=fileId;file=null;software=getSharedPreferences("playback",0).getBoolean("software",false);
        final int ticket=++generation;
        network.execute(()->{
            try {
                JSONObject data=api.get("/api/works/"+workId);long selected=fileId>0?fileId:data.optLong("resume_file_id");
                JSONArray files=data.getJSONArray("files");JSONObject chosen=null;
                for(int i=0;i<files.length();i++)if(files.getJSONObject(i).getLong("id")==selected)chosen=files.getJSONObject(i);
                if(chosen==null)throw new Exception("媒体没有可播放的视频");
                JSONObject selectedFile=chosen;JSONArray captions=api.get("/api/files/"+selected+"/subtitles").getJSONArray("items");
                runOnUiThread(()->{
                    if(isDestroyed()||ticket!=generation)return;
                    work=data;setVrEnabled(VrProjection.autoEnable(data.optString("kind")));vrVideo.recenter();file=selectedFile;subtitles=captions;resumeMs=file.optInt("completed")==1?0:(long)(file.optDouble("position")*1000);
                    title.setText(work.optString("title")+(work.optString("kind").equals("series")?" · S"+file.optInt("season")+" E"+file.optInt("episode"):""));
                    if(started)startPlayback();
                });
            }catch(Exception exception){runOnUiThread(()->{if(ticket==generation&&started)error(exception);});}
        });
    }
    private void startPlayback() {
        if(player!=null||file==null||!started||(vrEnabled&&vrVideo.videoTexture()==null))return;
        ending=false;sequence=0;seekGuard=2;session=null;
        ready=false;buffering=true;lastPosition=resumeMs;
        try {
            bridge=new PlaybackBridge(api.connection.base,api.connection.token,file.optLong("id"));
            ArrayList<String> options=new ArrayList<>();options.add("--network-caching=1500");
            vlc=new LibVLC(this,options);player=new MediaPlayer(vlc);
            player.setAudioOutputDevice("stereo");
            if(vrEnabled){
                player.getVLCVout().setVideoSurface(vrVideo.videoTexture());
                player.getVLCVout().setWindowSize(1920,1080);
                player.getVLCVout().attachViews();
            }else player.attachViews(video,null,true,false);
            Media media=new Media(vlc,Uri.parse(bridge.url(file.optString("stream"))));
            media.setHWDecoderEnabled(!software,false);
            media.addOption(":start-time="+(resumeMs/1000.0));
            player.setMedia(media);media.release();
            final MediaPlayer current=player;
            player.setEventListener(event->{
                if(player!=current||!started)return;
                if(event.type==MediaPlayer.Event.Buffering)buffering=event.getBuffering()<100;
                if(event.type==MediaPlayer.Event.Playing){
                    buffering=false;
                    if(!ready){
                        ready=true;
                        for(int i=0;i<subtitles.length();i++)current.addSlave(Media.Slave.Type.Subtitle,Uri.parse(bridge.url(subtitles.optJSONObject(i).optString("url"))),i==0);
                    }
                    if(vrEnabled){
                        org.videolan.libvlc.interfaces.IMedia.VideoTrack track=current.getCurrentVideoTrack();
                        if(track!=null){int[] size=vrVideo.setVideoSize(track.width,track.height);current.getVLCVout().setWindowSize(size[0],size[1]);}
                    }
                    status.setText(software?"软件解码 · 原画直传":"自动解码 · 硬件优先，软件兜底");
                }
                if(event.type==MediaPlayer.Event.EncounteredError){
                    if(!software){
                        handler.post(()->{if(player==current && started){restartDecoder(true);status.setText("正在改用软件解码重试…");}});
                    }else {buffering=true;tick(false,false);status.setText("播放失败，请检查网络或文件是否损坏。可切换音轨、字幕或解码模式后重试。");}
                }
                if(event.type==MediaPlayer.Event.EndReached&&!ending){
                    ending=true;handler.post(()->{if(player==current){stopPlayback(true);if(!nextEpisode(true))nextWork(true);}});
                }
                updateProgress();
            });
        }catch(Exception exception){stopPlayback(false);error(exception);return;}
        final int ticket=generation;final long fileId=file.optLong("id");final double initial=resumeMs/1000.0;
        network.execute(()->{
            try {
                String id=api.post("/api/playback/start",new JSONObject().put("file_id",fileId)).getString("session_id");
                runOnUiThread(()->{
                    if(isDestroyed()||ticket!=generation||player==null||!started) {
                        new Thread(()->{try{api.post("/api/playback/"+id+"/stop",new JSONObject().put("seq",0).put("position",initial).put("playing",false));}catch(Exception ignored){}},"playback-cleanup").start();
                    }else {session=id;status.setText("原画直传 · 播放进度同步至电脑");tick(false,false);}
                });
            } catch(Exception exception){runOnUiThread(()->{if(!isDestroyed())status.setText("视频可播放，观看记录暂未连接："+exception.getMessage());});}
        });
        if(focus())player.play();handler.removeCallbacks(heartbeat);handler.postDelayed(heartbeat,1000);
    }
    private void tick(boolean stop,boolean completed) {
        if(player==null||session==null)return;
        if(!stop&&!pendingTick.compareAndSet(false,true))return;
        String id=session;double position=positionMs()/1000.0;
        if(completed)position=file.optDouble("duration");
        final boolean playing=player.isPlaying()&&!buffering;final long seq=++sequence;final boolean seeking=seekGuard>0;seekGuard=Math.max(0,seekGuard-1);
        double rate=player.getRate();double value=position;
        if(stop)session=null;
        network.execute(()->{
            try {
                api.post("/api/playback/"+id+(stop?"/stop":"/tick"),new JSONObject().put("seq",seq).put("position",value)
                    .put("playing",playing).put("seeking",seeking).put("rate",rate).put("completed",completed));
            }catch(Exception exception){runOnUiThread(()->{if(!isDestroyed())status.setText("进度同步失败，请检查局域网连接");});}
            finally{if(!stop)pendingTick.set(false);}
        });
    }
    private void stopPlayback(boolean completed) {
        handler.removeCallbacks(heartbeat);
        if(player!=null) {
            resumeMs=completed?0:positionMs();
            tick(true,completed);player.setEventListener(null);player.stop();
            if(vrEnabled)player.getVLCVout().detachViews();else player.detachViews();
            player.release();player=null;
        }
        if(bridge!=null){bridge.close();bridge=null;}
        if(vlc!=null){vlc.release();vlc=null;}
        if(audio!=null)audio.abandonAudioFocusRequest(audioFocus);
    }
    private boolean focus(){return audio.requestAudioFocus(audioFocus)==android.media.AudioManager.AUDIOFOCUS_REQUEST_GRANTED;}
    private long positionMs(){if(!ready)return resumeMs;long value=player.getTime();return value>=0?value:lastPosition;}
    private long durationMs(){return player==null?0:Math.max(player.getLength(),(long)(file.optDouble("duration")*1000));}
    private String clock(long ms){long seconds=Math.max(0,ms/1000);return String.format(java.util.Locale.ROOT,"%d:%02d:%02d",seconds/3600,(seconds/60)%60,seconds%60);}
    private void updateProgress(){
        if(player==null)return;
        long position=positionMs();if(ready)lastPosition=position;
        long duration=durationMs();if(!dragging&&duration>0)seek.setProgress((int)(Math.max(0,position)*10000/duration));
        seek.setEnabled(player.isSeekable());pause.setText(player.isPlaying()?"暂停":"播放");
        time.setText(clock(position)+" / "+clock(duration));
    }
    private void restartDecoder(boolean useSoftware){
        generation++;stopPlayback(false);software=useSoftware;startPlayback();
    }
    private void setVrImmersive(boolean enabled){
        setRequestedOrientation(vrEnabled&&vrHeadset
            ? android.content.pm.ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
            : android.content.pm.ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED);
        vrImmersive=enabled && vrEnabled;
        for(View item:chrome)item.setVisibility(vrImmersive?View.GONE:View.VISIBLE);
        getWindow().getDecorView().setSystemUiVisibility(vrImmersive
            ? View.SYSTEM_UI_FLAG_FULLSCREEN|View.SYSTEM_UI_FLAG_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            : View.SYSTEM_UI_FLAG_VISIBLE);
    }
    private void setVrEnabled(boolean enabled){
        if(vrEnabled==enabled)return;
        generation++;stopPlayback(false);
        if(vrEnabled)vrVideo.onPause();
        vrEnabled=enabled;
        video.setVisibility(enabled?View.GONE:View.VISIBLE);vrVideo.setVisibility(enabled?View.VISIBLE:View.GONE);
        ((View)vrVideo.getTag()).setVisibility(enabled?View.VISIBLE:View.GONE);
        vrVideo.configure(vrFish,vrHeadset,vrSwap,vrTracking);
        vrVideo.recenter();
        if(enabled&&started)vrVideo.onResume();
        setVrImmersive(enabled&&vrHeadset);
        startPlayback();
    }
    private void vrSettings(){
        LinearLayout choices=new LinearLayout(this);choices.setOrientation(LinearLayout.VERTICAL);choices.setPadding(24,12,24,12);
        TextView info=new TextView(this);info.setText("VR180 · 180° 全景 · 左右 3D · 立体声音频\n拖动转向；无陀螺仪时使用触摸。普通视频请关闭 VR。");choices.addView(info);
        CheckBox enabled=new CheckBox(this);enabled.setText("启用 VR180 播放");enabled.setChecked(vrEnabled);choices.addView(enabled);
        CheckBox fish=new CheckBox(this);fish.setText("鱼眼模式（关闭为标准等距柱状投影）");fish.setChecked(vrFish);choices.addView(fish);
        CheckBox headset=new CheckBox(this);headset.setText("双眼观看（关闭为单屏左眼预览）");headset.setChecked(vrHeadset);choices.addView(headset);
        CheckBox swap=new CheckBox(this);swap.setText("交换左右眼");swap.setChecked(vrSwap);choices.addView(swap);
        CheckBox tracking=new CheckBox(this);tracking.setText(vrVideo.hasTracking()?"陀螺仪转向":"此设备无旋转传感器，使用触摸转向");tracking.setChecked(vrTracking&&vrVideo.hasTracking());tracking.setEnabled(vrVideo.hasTracking());choices.addView(tracking);
        Button center=new Button(this);center.setText("重置朝向");center.setOnClickListener(v->vrVideo.recenter());choices.addView(center);
        TextView fovLabel=new TextView(this);fovLabel.setText("视场角（50°–110°，默认 90°）");choices.addView(fovLabel);
        SeekBar fov=new SeekBar(this);fov.setMax(60);fov.setProgress(getSharedPreferences("playback",0).getInt("vr_fov",90)-50);choices.addView(fov);
        new AlertDialog.Builder(this).setTitle("VR 播放设置").setView(choices).setPositiveButton("应用",(d,w)->{
            vrFish=fish.isChecked();vrHeadset=headset.isChecked();vrSwap=swap.isChecked();vrTracking=tracking.isChecked();
            getSharedPreferences("playback",0).edit().putBoolean("vr_fish",vrFish).putBoolean("vr_headset",vrHeadset)
                .putBoolean("vr_swap",vrSwap).putBoolean("vr_tracking",vrTracking).putInt("vr_fov",fov.getProgress()+50).apply();
            vrVideo.configure(vrFish,vrHeadset,vrSwap,vrTracking);vrVideo.setFov(fov.getProgress()+50);
            setVrEnabled(enabled.isChecked());setVrImmersive(vrEnabled&&vrHeadset);
        }).setNegativeButton("取消",null).show();
    }
    private void decoder(){
        new AlertDialog.Builder(this).setTitle("解码模式（保留播放位置）")
            .setSingleChoiceItems(new String[]{"自动：硬件优先，软件兜底","软件：兼容性优先，耗电更高"},software?1:0,(dialog,index)->{
                getSharedPreferences("playback",0).edit().putBoolean("software",index==1).apply();dialog.dismiss();restartDecoder(index==1);
            }).setNegativeButton("取消",null).show();
    }
    private void tracks(boolean captions){
        if(player==null)return;
        MediaPlayer.TrackDescription[] tracks=captions?player.getSpuTracks():player.getAudioTracks();
        if(tracks==null||tracks.length==0){Toast.makeText(this,"暂无可选轨道，请等待视频载入",Toast.LENGTH_SHORT).show();return;}
        String[] names=new String[tracks.length];int selected=-1;int active=captions?player.getSpuTrack():player.getAudioTrack();
        for(int i=0;i<tracks.length;i++){names[i]=tracks[i].id==-1?"关闭":tracks[i].name;if(active==tracks[i].id)selected=i;}
        new AlertDialog.Builder(this).setTitle(captions?"字幕":"音轨").setSingleChoiceItems(names,selected,(dialog,index)->{
            if(player!=null){if(captions)player.setSpuTrack(tracks[index].id);else player.setAudioTrack(tracks[index].id);}dialog.dismiss();
        }).setNegativeButton("取消",null).show();
    }
    private boolean nextEpisode(boolean automatic) {
        if(work==null||file==null||!work.optString("kind").equals("series")) {
            if(!automatic)Toast.makeText(this,"当前不是电视剧",Toast.LENGTH_SHORT).show();return false;
        }
        JSONArray files=work.optJSONArray("files");
        for(int i=0;i<files.length()-1;i++)if(files.optJSONObject(i).optLong("id")==file.optLong("id")) {
            long nextId=files.optJSONObject(i+1).optLong("id");stopPlayback(false);load(work.optLong("id"),nextId);return true;
        }
        if(!automatic)Toast.makeText(this,"已经是最后一集",Toast.LENGTH_SHORT).show();return false;
    }
    private void nextWork(boolean automatic) {
        if(!queueMode) {
            if(automatic)finish();else Toast.makeText(this,"请从媒体库菜单创建随机队列",Toast.LENGTH_SHORT).show();return;
        }
        try {
            android.content.SharedPreferences prefs=getSharedPreferences("queue",0);JSONArray ids=new JSONArray(prefs.getString("ids","[]"));int next=prefs.getInt("index",0)+1;
            if(next>=ids.length()){Toast.makeText(this,"本轮随机队列已结束",Toast.LENGTH_LONG).show();finish();return;}
            prefs.edit().putInt("index",next).apply();stopPlayback(false);load(ids.getLong(next),0);
        }catch(Exception exception){error(exception);}
    }
    @Override protected void onStart(){super.onStart();started=true;if(vrEnabled&&vrVideo!=null)vrVideo.onResume();if(api!=null){if(file!=null)startPlayback();else load(desiredWork,desiredFile);}}
    @Override protected void onPause(){if(player!=null){player.pause();tick(false,false);}super.onPause();}
    @Override protected void onStop(){started=false;generation++;stopPlayback(false);if(vrEnabled&&vrVideo!=null)vrVideo.onPause();super.onStop();}
    @Override protected void onDestroy(){handler.removeCallbacksAndMessages(null);network.shutdown();if(vrVideo!=null)vrVideo.release();super.onDestroy();}
}
