package net.lumen.media;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.content.pm.ActivityInfo;
import android.content.res.Configuration;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.text.TextUtils;
import android.view.WindowManager;
import android.widget.*;
import org.videolan.libvlc.LibVLC;
import org.videolan.libvlc.Media;
import org.videolan.libvlc.MediaPlayer;
import org.videolan.libvlc.util.VLCVideoLayout;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayList;
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
    private boolean vrEnabled=false, vrFish=false, vrHeadset=false, vrSwap=false, vrTracking=true;
    private FrameLayout root,overlay;
    private LinearLayout topBar,bottomBar,vrBar;
    private PlayerController controller;
    private Button projection;
    private TextView gestureHint;
    private boolean vrSwipeSeek=true,swipeSeeking=false,swipeCancelled=false;
    private float swipeX,swipeY;
    private long swipeStart,swipeTarget;
    private final Runnable hideGesture=()->gestureHint.setVisibility(View.GONE);
    private boolean controlsVisible=true,immersive=true;
    private int orientationMode=0,videoOrientation=PlaybackPolicy.UNKNOWN;
    private int lastRequestedOrientation=Integer.MIN_VALUE;
    private final Runnable hideControls=()->showControls(false);
    private final Runnable refreshSurfaces=()->{if(player!=null&&!vrEnabled)player.updateVideoSurfaces();};
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
        android.content.SharedPreferences prefs=getSharedPreferences("playback",0);
        vrFish=prefs.getBoolean("vr_fish",false);vrHeadset=prefs.getBoolean("vr_headset",false);
        vrSwap=prefs.getBoolean("vr_swap",false);vrTracking=prefs.getBoolean("vr_tracking",true);
        orientationMode=prefs.getInt("orientation",0);vrSwipeSeek=prefs.getBoolean("vr_swipe_seek",true);
        buildPlayerUi(prefs);
        controller=new PlayerController(this,new PlayerController.Host(){
            public void action(ControllerBindings.Action action){performAction(action);}
            public void seek(long position){seekTo(position);}
        });
        audio=(android.media.AudioManager)getSystemService(AUDIO_SERVICE);
        audioFocus=new android.media.AudioFocusRequest.Builder(android.media.AudioManager.AUDIOFOCUS_GAIN)
            .setAudioAttributes(new android.media.AudioAttributes.Builder().setUsage(android.media.AudioAttributes.USAGE_MEDIA).setContentType(android.media.AudioAttributes.CONTENT_TYPE_MOVIE).build())
            .setOnAudioFocusChangeListener(change->{if(change<0 && player!=null){player.pause();tick(false,false);showControls(true);}},handler).build();
        setVolumeControlStream(android.media.AudioManager.STREAM_MUSIC);
        setPlayerImmersive(true);applyOrientation();
        queueMode=getIntent().getBooleanExtra("queue",false);
        desiredWork=getIntent().getLongExtra("work_id",0);desiredFile=getIntent().getLongExtra("file_id",0);
    }
    private int dp(int value){return Math.round(value*getResources().getDisplayMetrics().density);}
    private TextView label(String text,int size){
        TextView view=new TextView(this);view.setText(text);view.setTextColor(Color.WHITE);view.setTextSize(size);
        return view;
    }
    private Button button(String label,Runnable action){
        Button button=new Button(this);button.setText(label);button.setTextColor(Color.WHITE);button.setTextSize(14);
        button.setAllCaps(false);button.setMinWidth(0);button.setMinimumWidth(0);button.setMinHeight(dp(48));
        button.setMinimumHeight(dp(48));button.setPadding(dp(4),0,dp(4),0);
        button.setBackgroundColor(Color.TRANSPARENT);button.setContentDescription(label);
        button.setOnClickListener(v->{showControls(true);action.run();scheduleHide();});return button;
    }
    private Button addButton(LinearLayout layout,String label,Runnable action){
        Button button=button(label,action);layout.addView(button,new LinearLayout.LayoutParams(0,dp(48),1));return button;
    }
    private GradientDrawable shade(boolean top){
        return new GradientDrawable(top?GradientDrawable.Orientation.TOP_BOTTOM:GradientDrawable.Orientation.BOTTOM_TOP,
            new int[]{0xEE000000,0xA0000000,0x00000000});
    }
    private void buildPlayerUi(android.content.SharedPreferences prefs){
        root=new FrameLayout(this);root.setBackgroundColor(Color.BLACK);
        video=new VLCVideoLayout(this);root.addView(video,new FrameLayout.LayoutParams(-1,-1));
        // A normal video surface does not need to receive touches; its sibling wakes the overlay.
        View touch=new View(this);root.addView(touch,new FrameLayout.LayoutParams(-1,-1));touch.setOnClickListener(v->showControls(!controlsVisible));
        touch.setOnTouchListener((view,event)->playbackTouch(view,event));
        vrVideo=new VrVideoView(this,new VrVideoView.Listener(){
            public void ready(){if(started&&vrEnabled)startPlayback();}
            public void lost(){if(vrEnabled&&player!=null)stopPlayback(false);}
            public void failed(String reason){status.setText("VR 渲染失败："+reason);setVrEnabled(false);showControls(true);}
            public void tap(){showControls(!controlsVisible);}
            public void zoom(float fov){saveFov(fov);}
            public boolean gesture(View view,MotionEvent event){return playbackTouch(view,event);}
        });
        vrVideo.setSwipeSeeking(vrSwipeSeek);vrVideo.setFov(prefs.getInt("vr_fov",90));vrVideo.setVisibility(View.GONE);
        root.addView(vrVideo,new FrameLayout.LayoutParams(-1,-1));
        overlay=new FrameLayout(this);root.addView(overlay,new FrameLayout.LayoutParams(-1,-1));
        gestureHint=label("",18);gestureHint.setGravity(Gravity.CENTER);gestureHint.setPadding(dp(16),dp(12),dp(16),dp(12));
        gestureHint.setBackgroundColor(0xDD101010);gestureHint.setVisibility(View.GONE);
        overlay.addView(gestureHint,new FrameLayout.LayoutParams(-2,-2,Gravity.CENTER));
        topBar=new LinearLayout(this);topBar.setGravity(Gravity.CENTER_VERTICAL);topBar.setBackground(shade(true));
        Button back=button("返回",this::finish);topBar.addView(back,new LinearLayout.LayoutParams(dp(64),dp(48)));
        title=label("正在载入…",16);title.setMaxLines(1);title.setEllipsize(TextUtils.TruncateAt.END);
        topBar.addView(title,new LinearLayout.LayoutParams(0,-2,1));
        topBar.addView(button("设置",this::playbackSettings),new LinearLayout.LayoutParams(dp(64),dp(48)));
        overlay.addView(topBar,new FrameLayout.LayoutParams(-1,-2,Gravity.TOP));
        bottomBar=new LinearLayout(this);bottomBar.setOrientation(LinearLayout.VERTICAL);bottomBar.setBackground(shade(false));
        status=label("正在连接视频…",12);status.setMaxLines(1);status.setEllipsize(TextUtils.TruncateAt.END);bottomBar.addView(status);
        time=label("0:00:00 / 0:00:00",12);bottomBar.addView(time);
        seek=new SeekBar(this);seek.setMax(10000);seek.setContentDescription("播放进度");
        bottomBar.addView(seek,new LinearLayout.LayoutParams(-1,dp(32)));
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){
            public void onStartTrackingTouch(SeekBar bar){dragging=true;handler.removeCallbacks(hideControls);}
            public void onProgressChanged(SeekBar bar,int value,boolean user){if(user)time.setText(clock(durationMs()*value/10000)+" / "+clock(durationMs()));}
            public void onStopTrackingTouch(SeekBar bar){dragging=false;seekTo(durationMs()*bar.getProgress()/10000);scheduleHide();}
        });
        LinearLayout playback=new LinearLayout(this);
        addButton(playback,"−10 秒",()->performAction(ControllerBindings.Action.BACKWARD));
        pause=addButton(playback,"播放",()->performAction(ControllerBindings.Action.TOGGLE));
        addButton(playback,"+10 秒",()->performAction(ControllerBindings.Action.FORWARD));
        addButton(playback,"全屏",()->{setPlayerImmersive(!immersive);showControls(true);});bottomBar.addView(playback);
        vrBar=new LinearLayout(this);
        addButton(vrBar,"回正",()->performAction(ControllerBindings.Action.RECENTER));
        addButton(vrBar,"拉远 −",()->performAction(ControllerBindings.Action.ZOOM_OUT));
        addButton(vrBar,"拉近 +",()->performAction(ControllerBindings.Action.ZOOM_IN));
        projection=addButton(vrBar,vrFish?"鱼眼":"标准",()->performAction(ControllerBindings.Action.PROJECTION));
        bottomBar.addView(vrBar);vrBar.setVisibility(View.GONE);
        overlay.addView(bottomBar,new FrameLayout.LayoutParams(-1,-2,Gravity.BOTTOM));
        setContentView(root);
        if(Build.VERSION.SDK_INT>=30)getWindow().setDecorFitsSystemWindows(false);
        else getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE|View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN|View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
        if(Build.VERSION.SDK_INT>=28){
            WindowManager.LayoutParams attributes=getWindow().getAttributes();
            attributes.layoutInDisplayCutoutMode=WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;getWindow().setAttributes(attributes);
        }
        root.setOnApplyWindowInsetsListener((view,insets)->{
            int left,right,top,bottom;
            if(Build.VERSION.SDK_INT>=30){
                android.graphics.Insets safe=insets.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout());
                left=safe.left;right=safe.right;top=safe.top;bottom=safe.bottom;
            }else{
                left=insets.getSystemWindowInsetLeft();right=insets.getSystemWindowInsetRight();top=insets.getSystemWindowInsetTop();bottom=insets.getSystemWindowInsetBottom();
                if(Build.VERSION.SDK_INT>=28&&insets.getDisplayCutout()!=null){
                    android.view.DisplayCutout cutout=insets.getDisplayCutout();left=Math.max(left,cutout.getSafeInsetLeft());right=Math.max(right,cutout.getSafeInsetRight());
                    top=Math.max(top,cutout.getSafeInsetTop());bottom=Math.max(bottom,cutout.getSafeInsetBottom());
                }
            }
            overlay.setPadding(left+dp(8),top+dp(4),right+dp(8),bottom+dp(8));return insets;
        });
        root.addOnLayoutChangeListener((v,l,t,r,b,ol,ot,or,ob)->{
            boolean compact=(b-t)/getResources().getDisplayMetrics().density<340;
            status.setVisibility(compact?View.GONE:View.VISIBLE);
            handler.removeCallbacks(refreshSurfaces);handler.post(refreshSurfaces);
        });
        root.requestApplyInsets();
    }
    private boolean playbackTouch(View view,MotionEvent event){
        switch(event.getActionMasked()){
            case MotionEvent.ACTION_DOWN:
                swipeX=event.getX();swipeY=event.getY();swipeStart=player==null?0:positionMs();swipeTarget=swipeStart;
                swipeSeeking=false;swipeCancelled=false;handler.removeCallbacks(hideControls);return true;
            case MotionEvent.ACTION_POINTER_DOWN:
                swipeCancelled=true;swipeSeeking=false;gestureHint.setVisibility(View.GONE);return true;
            case MotionEvent.ACTION_MOVE:
                if(swipeCancelled||event.getPointerCount()!=1)return true;
                float dx=event.getX()-swipeX,dy=event.getY()-swipeY;
                if(!swipeSeeking&&SeekGesture.horizontal(dx,dy,android.view.ViewConfiguration.get(this).getScaledTouchSlop()))swipeSeeking=true;
                if(swipeSeeking){
                    swipeTarget=SeekGesture.target(swipeStart,durationMs(),dx,view.getWidth());
                    gestureHint.setText(player!=null&&player.isSeekable()?(swipeTarget>=swipeStart?"快进 ":"后退 ")+clock(Math.abs(swipeTarget-swipeStart))+"\n"+clock(swipeTarget)+" / "+clock(durationMs()):"当前视频暂不可跳转");
                    handler.removeCallbacks(hideGesture);gestureHint.setVisibility(View.VISIBLE);
                }
                return true;
            case MotionEvent.ACTION_UP:
                if(swipeSeeking&&!swipeCancelled){seekTo(swipeTarget);handler.postDelayed(hideGesture,700);showControls(true);}
                else if(!swipeCancelled&&Math.hypot(event.getX()-swipeX,event.getY()-swipeY)<android.view.ViewConfiguration.get(this).getScaledTouchSlop())view.performClick();
                swipeSeeking=false;scheduleHide();return true;
            case MotionEvent.ACTION_CANCEL:
                swipeCancelled=true;swipeSeeking=false;gestureHint.setVisibility(View.GONE);scheduleHide();return true;
            default:return true;
        }
    }
    private void scheduleHide(){
        handler.removeCallbacks(hideControls);
        if(player!=null&&player.isPlaying()&&!dragging)handler.postDelayed(hideControls,4500);
    }
    private void showControls(boolean visible){
        controlsVisible=visible;
        topBar.setVisibility(visible?View.VISIBLE:View.GONE);bottomBar.setVisibility(visible?View.VISIBLE:View.GONE);
        if(visible)scheduleHide();else handler.removeCallbacks(hideControls);
    }
    private void setPlayerImmersive(boolean enabled){
        immersive=enabled;
        if(Build.VERSION.SDK_INT>=30){
            WindowInsetsController bars=getWindow().getInsetsController();
            if(bars!=null){bars.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
                if(enabled)bars.hide(WindowInsets.Type.systemBars());else bars.show(WindowInsets.Type.systemBars());}
        }else getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE|View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN|View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION|
            (enabled?View.SYSTEM_UI_FLAG_FULLSCREEN|View.SYSTEM_UI_FLAG_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY:0));
        root.requestApplyInsets();
    }
    private void playbackSettings(){
        new AlertDialog.Builder(this).setTitle("播放设置").setItems(new String[]{"音轨","字幕","解码模式","屏幕方向","VR 设置","蓝牙 / 手柄映射","下一集","下一作品"},(d,index)->{
            switch(index){case 0:tracks(false);break;case 1:tracks(true);break;case 2:decoder();break;case 3:orientationSettings();break;
                case 4:vrSettings();break;case 5:controller.settings();break;case 6:nextEpisode(false);break;case 7:nextWork(false);break;}
        }).setNegativeButton("关闭",null).show();
    }
    private void orientationSettings(){
        new AlertDialog.Builder(this).setTitle("屏幕方向").setSingleChoiceItems(new String[]{"自动：按视频显示比例","横屏","竖屏"},orientationMode,(d,index)->{
            orientationMode=index;getSharedPreferences("playback",0).edit().putInt("orientation",index).apply();applyOrientation();d.dismiss();
        }).setNegativeButton("取消",null).show();
    }
    private void updateVideoGeometry(){
        if(player==null)return;
        org.videolan.libvlc.interfaces.IMedia.VideoTrack track=player.getCurrentVideoTrack();
        if(track==null)return;
        videoOrientation=PlaybackPolicy.orientation(track.width,track.height,track.sarNum,track.sarDen,
            track.orientation>=org.videolan.libvlc.interfaces.IMedia.VideoTrack.Orientation.LeftTop);
        applyOrientation();
    }
    private void applyOrientation(){
        int mode=orientationMode==0?videoOrientation:orientationMode;
        int orientation=vrEnabled||mode==PlaybackPolicy.LANDSCAPE?ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE:
            mode==PlaybackPolicy.PORTRAIT?ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT:ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED;
        if(orientation!=lastRequestedOrientation){lastRequestedOrientation=orientation;setRequestedOrientation(orientation);}
    }
    private void seekTo(long position){
        if(player==null||!player.isSeekable())return;
        seekGuard=2;lastPosition=PlaybackPolicy.seek(position,durationMs(),0);player.setTime(lastPosition);tick(false,false);updateProgress();
    }
    private void saveFov(float value){getSharedPreferences("playback",0).edit().putInt("vr_fov",Math.round(value)).apply();}
    private void performAction(ControllerBindings.Action action){
        switch(action){
            case TOGGLE:if(player!=null){if(player.isPlaying())player.pause();else if(focus())player.play();tick(false,false);updateProgress();}break;
            case PLAY:if(player!=null&&focus())player.play();break;
            case PAUSE:if(player!=null){player.pause();tick(false,false);updateProgress();}break;
            case FORWARD:if(player!=null)seekTo(PlaybackPolicy.seek(positionMs(),durationMs(),10000));break;
            case BACKWARD:if(player!=null)seekTo(PlaybackPolicy.seek(positionMs(),durationMs(),-10000));break;
            case PROJECTION:if(vrEnabled){vrFish=!vrFish;vrVideo.configure(vrFish,vrHeadset,vrSwap,vrTracking);projection.setText(vrFish?"鱼眼":"标准");
                getSharedPreferences("playback",0).edit().putBoolean("vr_fish",vrFish).apply();Toast.makeText(this,vrFish?"鱼眼模式":"标准模式",Toast.LENGTH_SHORT).show();}break;
            case ZOOM_IN:case ZOOM_OUT:if(vrEnabled){vrVideo.setFov(vrVideo.getFov()+(action==ControllerBindings.Action.ZOOM_IN?-5:5));saveFov(vrVideo.getFov());}break;
            case RECENTER:if(vrEnabled)vrVideo.recenter();break;
            case RESET_VIEW:if(vrEnabled){vrVideo.recenter();vrVideo.setFov(90);saveFov(90);}break;
            case CONTROLS:showControls(!controlsVisible);return;
            case NONE:return;
        }
        if(!vrEnabled||!vrHeadset)showControls(true);
    }
    @Override public boolean dispatchKeyEvent(KeyEvent event){return controller!=null&&controller.key(event)||super.dispatchKeyEvent(event);}
    @Override public boolean dispatchGenericMotionEvent(MotionEvent event){return controller!=null&&controller.motion(event)||super.dispatchGenericMotionEvent(event);}
    @Override public void onConfigurationChanged(Configuration configuration){
        super.onConfigurationChanged(configuration);if(root!=null){root.requestApplyInsets();handler.post(refreshSurfaces);}
    }
    @Override public void onWindowFocusChanged(boolean focused){super.onWindowFocusChanged(focused);if(focused&&root!=null)setPlayerImmersive(immersive);if(!focused&&controller!=null)controller.clearHeld();}
    private void error(Exception exception) {
        runOnUiThread(()->{if(!isDestroyed()){status.setText("无法播放："+exception.getMessage());new AlertDialog.Builder(this).setTitle("播放失败").setMessage(exception.getMessage()).setPositiveButton("返回",(d,w)->finish()).setNegativeButton("关闭",null).show();}});
    }
    private void load(long workId,long fileId) {
        desiredWork=workId;desiredFile=fileId;videoOrientation=PlaybackPolicy.UNKNOWN;file=null;software=getSharedPreferences("playback",0).getBoolean("software",false);
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
                    work=data;setVrEnabled(VrProjection.autoEnable(data.optString("kind")));vrVideo.recenter();file=selectedFile;applyOrientation();showControls(true);subtitles=captions;resumeMs=file.optInt("completed")==1?0:(long)(file.optDouble("position")*1000);
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
            }else {player.attachViews(video,null,true,false);player.setVideoScale(MediaPlayer.ScaleType.SURFACE_BEST_FIT);}
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
                    updateVideoGeometry();scheduleHide();
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
        handler.removeCallbacks(heartbeat);handler.removeCallbacks(hideControls);
        if(controller!=null)controller.state(false,false,resumeMs,durationMs(),title.getText().toString());
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
        updateVideoGeometry();
        if(controller!=null)controller.state(player.isPlaying(),buffering,position,duration,title.getText().toString());
        if(!player.isPlaying()&&!controlsVisible)showControls(true);
    }
    private void restartDecoder(boolean useSoftware){
        generation++;stopPlayback(false);software=useSoftware;startPlayback();
    }
    private void setVrImmersive(boolean enabled){applyOrientation();showControls(!enabled);}
    private void setVrEnabled(boolean enabled){
        if(vrEnabled==enabled)return;
        generation++;stopPlayback(false);
        if(vrEnabled)vrVideo.onPause();
        vrEnabled=enabled;
        video.setVisibility(enabled?View.GONE:View.VISIBLE);vrVideo.setVisibility(enabled?View.VISIBLE:View.GONE);
        vrBar.setVisibility(enabled?View.VISIBLE:View.GONE);
        vrVideo.configure(vrFish,vrHeadset,vrSwap,vrTracking);
        vrVideo.recenter();
        if(enabled&&started)vrVideo.onResume();
        setVrImmersive(enabled&&vrHeadset);
        startPlayback();
    }
    private void vrSettings(){
        LinearLayout choices=new LinearLayout(this);choices.setOrientation(LinearLayout.VERTICAL);choices.setPadding(24,12,24,12);
        TextView info=new TextView(this);info.setText("VR180 · 180° 全景 · 左右 3D · 立体声音频\n默认单指横滑调进度、双指缩放；可关闭横滑调进度以拖动转向。普通视频请关闭 VR。");choices.addView(info);
        CheckBox enabled=new CheckBox(this);enabled.setText("启用 VR180 播放");enabled.setChecked(vrEnabled);choices.addView(enabled);
        CheckBox fish=new CheckBox(this);fish.setText("鱼眼模式（关闭为标准等距柱状投影）");fish.setChecked(vrFish);choices.addView(fish);
        CheckBox headset=new CheckBox(this);headset.setText("双眼观看（关闭为单屏左眼预览）");headset.setChecked(vrHeadset);choices.addView(headset);
        CheckBox swap=new CheckBox(this);swap.setText("交换左右眼");swap.setChecked(vrSwap);choices.addView(swap);
        CheckBox tracking=new CheckBox(this);tracking.setText(vrVideo.hasTracking()?"陀螺仪转向":"此设备无旋转传感器，使用触摸转向");tracking.setChecked(vrTracking&&vrVideo.hasTracking());tracking.setEnabled(vrVideo.hasTracking());choices.addView(tracking);
        CheckBox swipeMode=new CheckBox(this);swipeMode.setText("单指横滑调进度（关闭后拖动转向）");swipeMode.setChecked(vrSwipeSeek);choices.addView(swipeMode);
        Button center=new Button(this);center.setText("回正朝向");center.setOnClickListener(v->vrVideo.recenter());choices.addView(center);
        Button reset=new Button(this);reset.setText("恢复初始位置及默认缩放");choices.addView(reset);
        TextView fovLabel=new TextView(this);fovLabel.setText("视场角（50°–110°，默认 90°）");choices.addView(fovLabel);
        SeekBar fov=new SeekBar(this);fov.setMax(60);fov.setProgress(Math.round(vrVideo.getFov())-50);choices.addView(fov);
        reset.setOnClickListener(v->{vrVideo.recenter();fov.setProgress(40);vrVideo.setFov(90);saveFov(90);});
        fov.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){
            public void onStartTrackingTouch(SeekBar b){}
            public void onProgressChanged(SeekBar b,int value,boolean user){if(user){vrVideo.setFov(value+50);saveFov(value+50);}}
            public void onStopTrackingTouch(SeekBar b){}
        });
        ScrollView scroll=new ScrollView(this);scroll.addView(choices);
        new AlertDialog.Builder(this).setTitle("VR 播放设置").setView(scroll).setPositiveButton("应用",(d,w)->{
            vrFish=fish.isChecked();vrHeadset=headset.isChecked();vrSwap=swap.isChecked();vrTracking=tracking.isChecked();vrSwipeSeek=swipeMode.isChecked();
            vrVideo.setSwipeSeeking(vrSwipeSeek);
            getSharedPreferences("playback",0).edit().putBoolean("vr_fish",vrFish).putBoolean("vr_headset",vrHeadset)
                .putBoolean("vr_swap",vrSwap).putBoolean("vr_tracking",vrTracking).putBoolean("vr_swipe_seek",vrSwipeSeek).putInt("vr_fov",fov.getProgress()+50).apply();
            vrVideo.configure(vrFish,vrHeadset,vrSwap,vrTracking);vrVideo.setFov(fov.getProgress()+50);projection.setText(vrFish?"鱼眼":"标准");
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
    @Override protected void onStart(){super.onStart();started=true;if(controller!=null)controller.active(true);if(vrEnabled&&vrVideo!=null)vrVideo.onResume();if(api!=null){if(file!=null)startPlayback();else load(desiredWork,desiredFile);}}
    @Override protected void onPause(){if(controller!=null)controller.active(false);if(player!=null){player.pause();tick(false,false);}super.onPause();}
    @Override protected void onResume(){super.onResume();if(controller!=null)controller.active(true);if(root!=null){setPlayerImmersive(immersive);showControls(true);}}
    @Override protected void onStop(){started=false;generation++;stopPlayback(false);if(vrEnabled&&vrVideo!=null)vrVideo.onPause();super.onStop();}
    @Override protected void onDestroy(){if(controller!=null)controller.release();handler.removeCallbacksAndMessages(null);network.shutdown();if(vrVideo!=null)vrVideo.release();super.onDestroy();}
}
