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
    private Button pause,previousVideo,nextVideo;
    private boolean navigationPending=false;
    private int browsePosition=-1;
    private boolean software=false,dragging=false,ready=false,buffering=false;
    private long lastPosition=0;
    private android.media.AudioManager audio;
    private android.media.AudioFocusRequest audioFocus;
    private TextView title,status;
    private JSONObject work,file;
    private JSONObject filePreferences=new JSONObject();
    private boolean preferencesDirty=false,pauseAfterStyleChange=false;
    private final Runnable persistPreferences=this::flushPreferences;
    private JSONArray subtitles=new JSONArray();
    private String session;
    private long sequence=0,resumeMs=0,desiredWork=0,desiredFile=0;
    private volatile int generation=0;
    private int seekGuard=0;
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
        queueMode=getIntent().getBooleanExtra("queue",false);browsePosition=getIntent().getIntExtra("browse_position",-1);
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
            public void viewChanged(){saveVrPreferences();}
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
        Button bookmarks=button("书签",()->{});bookmarks.setContentDescription("时间点书签");
        bookmarks.setOnClickListener(view->{PopupMenu menu=new PopupMenu(this,view);menu.getMenu().add("添加当前时间点");menu.getMenu().add("查看 / 跳转书签");for(int i=0;i<menu.getMenu().size();i++)menu.getMenu().getItem(i).setEnabled(file!=null);menu.setOnMenuItemClickListener(item->{if(item.getTitle().toString().startsWith("添加"))addBookmark();else showBookmarks();return true;});menu.show();});
        topBar.addView(bookmarks,new LinearLayout.LayoutParams(dp(64),dp(48)));
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
        previousVideo=addButton(playback,"",()->stepVideo(-1));MediaStyle.icon(previousVideo,"previous",false);previousVideo.setCompoundDrawablePadding(0);previousVideo.setContentDescription("上个视频");previousVideo.setTooltipText("上个视频 / 上一集");
        addButton(playback,"−10 秒",()->performAction(ControllerBindings.Action.BACKWARD));
        pause=addButton(playback,"播放",()->performAction(ControllerBindings.Action.TOGGLE));
        addButton(playback,"+10 秒",()->performAction(ControllerBindings.Action.FORWARD));
        nextVideo=addButton(playback,"",()->stepVideo(1));MediaStyle.icon(nextVideo,"next",false);nextVideo.setCompoundDrawablePadding(0);nextVideo.setContentDescription("下个视频");nextVideo.setTooltipText("下个视频 / 下一集");
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
        new AlertDialog.Builder(this).setTitle("播放设置").setItems(new String[]{"音轨","字幕","解码模式","屏幕方向","VR 设置","蓝牙 / 手柄映射","下个视频","下一作品","字幕同步与样式","添加时间点书签","查看时间点书签","播放诊断","上个视频","播放速度","自动播放下一集"},(d,index)->{
            switch(index){case 0:tracks(false);break;case 1:tracks(true);break;case 2:decoder();break;case 3:orientationSettings();break;
                case 4:vrSettings();break;case 5:controller.settings();break;case 6:stepVideo(1);break;case 7:nextWork(false);break;
                case 8:subtitleSettings();break;case 9:addBookmark();break;case 10:showBookmarks();break;case 11:diagnostics();break;case 12:stepVideo(-1);break;case 13:new AlertDialog.Builder(this).setTitle("播放速度").setItems(new String[]{"0.5×","0.75×","1×","1.25×","1.5×","1.75×","2×"},(a,n)->{float rate=new float[]{.5f,.75f,1f,1.25f,1.5f,1.75f,2f}[n];getSharedPreferences("player",0).edit().putFloat("speed",rate).apply();if(player!=null)player.setRate(rate);}).show();break;
                case 14:new AlertDialog.Builder(this).setTitle("自动播放下一集").setSingleChoiceItems(new String[]{"开启","关闭"},getSharedPreferences("player",0).getBoolean("auto_next",true)?0:1,(a,n)->{getSharedPreferences("player",0).edit().putBoolean("auto_next",n==0).apply();a.dismiss();}).show();break;}
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
    private void saveFov(float value){getSharedPreferences("playback",0).edit().putInt("vr_fov",Math.round(value)).apply();saveVrPreferences();}
    private void performAction(ControllerBindings.Action action){
        switch(action){
            case TOGGLE:if(player!=null){if(player.isPlaying())player.pause();else if(focus())player.play();tick(false,false);updateProgress();}break;
            case PLAY:if(player!=null&&focus())player.play();break;
            case PAUSE:if(player!=null){player.pause();tick(false,false);updateProgress();}break;
            case FORWARD:if(player!=null)seekTo(PlaybackPolicy.seek(positionMs(),durationMs(),10000));break;
            case BACKWARD:if(player!=null)seekTo(PlaybackPolicy.seek(positionMs(),durationMs(),-10000));break;
            case NEXT_EPISODE:stepVideo(1);break;
            case PREVIOUS_EPISODE:stepVideo(-1);break;
            case PROJECTION:if(vrEnabled){vrFish=!vrFish;vrVideo.configure(vrFish,vrHeadset,vrSwap,vrTracking);projection.setText(vrFish?"鱼眼":"标准");
                getSharedPreferences("playback",0).edit().putBoolean("vr_fish",vrFish).apply();saveVrPreferences();Toast.makeText(this,vrFish?"鱼眼模式":"标准模式",Toast.LENGTH_SHORT).show();}break;
            case ZOOM_IN:case ZOOM_OUT:if(vrEnabled){vrVideo.setFov(vrVideo.getFov()+(action==ControllerBindings.Action.ZOOM_IN?-5:5));saveFov(vrVideo.getFov());}break;
            case RECENTER:if(vrEnabled){vrVideo.recenter();saveVrPreferences();}break;
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
        flushPreferences();
        pauseAfterStyleChange=false;
        desiredWork=workId;desiredFile=fileId;videoOrientation=PlaybackPolicy.UNKNOWN;file=null;software=getSharedPreferences("playback",0).getBoolean("software",false);
        final int ticket=++generation;setNavigationPending(true);
        network.execute(()->{
            try {
                JSONObject data=api.get("/api/works/"+workId);long selected=fileId>0?fileId:data.optLong("resume_file_id");
                JSONArray files=data.getJSONArray("files");if(fileId<0&&files.length()>0)selected=files.getJSONObject(files.length()-1).getLong("id");JSONObject chosen=null;
                for(int i=0;i<files.length();i++)if(files.getJSONObject(i).getLong("id")==selected)chosen=files.getJSONObject(i);
                if(chosen==null&&fileId==0&&files.length()>0){chosen=files.getJSONObject(0);selected=chosen.getLong("id");}
                if(chosen==null)throw new Exception("媒体没有可播放的视频");
                JSONObject selectedFile=chosen;JSONArray captions=api.get("/api/files/"+selected+"/subtitles").getJSONArray("items");
                JSONObject savedPreferences=readPreferences(selected);
                runOnUiThread(()->{
                    if(isDestroyed()||ticket!=generation)return;
                    boolean sameWork=work!=null&&work.optLong("id")==data.optLong("id");setNavigationPending(false);work=data;if(!sameWork)setVrEnabled(VrProjection.autoEnable(data.optString("kind")));vrVideo.recenter();file=selectedFile;filePreferences=savedPreferences;applyFilePreferences();applyOrientation();showControls(true);subtitles=captions;resumeMs=file.optInt("completed")==1?0:(long)(file.optDouble("position")*1000);
                    if(getIntent().hasExtra("start_position")){resumeMs=Math.max(0,Math.min((long)(getIntent().getDoubleExtra("start_position",0)*1000),durationFromFile()));getIntent().removeExtra("start_position");}
                    title.setText(work.optString("title")+(work.optString("kind").equals("series")?" · S"+file.optInt("season")+" E"+file.optInt("episode"):""));
                    if(started)startPlayback();
                });
            }catch(Exception exception){runOnUiThread(()->{if(ticket==generation){setNavigationPending(false);if(started)error(exception);}});}
        });
    }
    private void startPlayback() {
        if(player!=null||file==null||!started||(vrEnabled&&vrVideo.videoTexture()==null))return;
        ending=false;sequence=0;seekGuard=2;session=null;
        ready=false;buffering=true;lastPosition=resumeMs;
        try {
            bridge=new PlaybackBridge(api.connection.base,api.connection.token,file.optLong("id"));
            ArrayList<String> options=new ArrayList<>();options.add("--network-caching=1500");
            options.add("--freetype-fontsize="+dp(filePreferences.optInt("subtitle_size",22)));
            options.add("--sub-margin="+Math.max(0,(root.getHeight()>0?root.getHeight():getResources().getDisplayMetrics().heightPixels)*(100-filePreferences.optInt("subtitle_position",90))/100));
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
                    current.setSpuDelay((long)(filePreferences.optDouble("subtitle_delay",0)*1_000_000));
                    if(pauseAfterStyleChange){pauseAfterStyleChange=false;current.pause();showControls(true);}
                    current.setRate(getSharedPreferences("player",0).getFloat("speed",1f));
                    status.setText(software?"软件解码 · 原画直传":"自动解码 · 硬件优先，软件兜底");
                }
                if(event.type==MediaPlayer.Event.EncounteredError){
                    if(!software){
                        handler.post(()->{if(player==current && started){restartDecoder(true);status.setText("正在改用软件解码重试…");}});
                    }else {buffering=true;tick(false,false);status.setText("播放失败，请检查网络或文件是否损坏。可切换音轨、字幕或解码模式后重试。");}
                }
                if(event.type==MediaPlayer.Event.EndReached&&!ending){
                    ending=true;handler.post(()->{if(player==current){stopPlayback(true);if(work.optString("kind").equals("series")&&!getSharedPreferences("player",0).getBoolean("auto_next",true)){showControls(true);return;}if(!nextEpisode(true)){if(queueMode&&getSharedPreferences("queue",0).getInt("repeat",0)==2)load(work.optLong("id"),0);else nextWork(true);}}});
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
        generation++;setNavigationPending(false);stopPlayback(false);software=useSoftware;startPlayback();
    }
    private void setVrImmersive(boolean enabled){applyOrientation();showControls(!enabled);}
    private void setVrEnabled(boolean enabled){
        if(vrEnabled==enabled)return;
        generation++;setNavigationPending(false);stopPlayback(false);
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
        CheckBox invertPitch=new CheckBox(this);invertPitch.setText("反转陀螺仪上下方向");invertPitch.setChecked(vrVideo.getTrackingInvertPitch());choices.addView(invertPitch);
        TextView sensitivityLabel=new TextView(this);choices.addView(sensitivityLabel);
        SeekBar sensitivity=new SeekBar(this);sensitivity.setContentDescription("陀螺仪灵敏度");sensitivity.setMax(125);sensitivity.setProgress(Math.round(vrVideo.getTrackingSensitivity()*100)-25);choices.addView(sensitivity);
        TextView smoothingLabel=new TextView(this);choices.addView(smoothingLabel);
        SeekBar smoothing=new SeekBar(this);smoothing.setContentDescription("陀螺仪平滑");smoothing.setMax(150);smoothing.setProgress(vrVideo.getTrackingSmoothing());choices.addView(smoothing);
        Runnable updateTrackingLabels=()->{sensitivityLabel.setText("陀螺仪灵敏度："+(sensitivity.getProgress()+25)+"%（头显建议 100%）");smoothingLabel.setText("平滑时间："+smoothing.getProgress()+" ms（默认 40，越高越稳、延迟越大）");};updateTrackingLabels.run();
        SeekBar.OnSeekBarChangeListener trackingChange=new SeekBar.OnSeekBarChangeListener(){public void onStartTrackingTouch(SeekBar bar){}public void onProgressChanged(SeekBar bar,int value,boolean user){updateTrackingLabels.run();}public void onStopTrackingTouch(SeekBar bar){}};
        sensitivity.setOnSeekBarChangeListener(trackingChange);smoothing.setOnSeekBarChangeListener(trackingChange);
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
            getSharedPreferences("playback",0).edit().putFloat("vr_tracking_sensitivity",(sensitivity.getProgress()+25)/100f).putInt("vr_tracking_smoothing",smoothing.getProgress()).putBoolean("vr_tracking_invert_pitch",invertPitch.isChecked()).apply();
            vrVideo.setTrackingParameters((sensitivity.getProgress()+25)/100f,smoothing.getProgress(),invertPitch.isChecked());
            vrVideo.configure(vrFish,vrHeadset,vrSwap,vrTracking);vrVideo.setFov(fov.getProgress()+50);projection.setText(vrFish?"鱼眼":"标准");
            setVrEnabled(enabled.isChecked());setVrImmersive(vrEnabled&&vrHeadset);
            saveVrPreferences();
        }).setNegativeButton("取消",null).show();
    }
    private long durationFromFile(){return file==null?0:(long)(file.optDouble("duration")>0?file.optDouble("duration")*1000:864_000_000);}
    private String preferenceKey(long id){return api.connection.base+"#"+id;}
    private JSONObject readPreferences(long id){
        JSONObject local=new JSONObject();try{local=new JSONObject(getSharedPreferences("media-preferences",0).getString(preferenceKey(id),"{}"));}catch(Exception ignored){}
        try{JSONObject remote=api.get("/api/files/"+id+"/preferences");if(remote.length()>0){
            JSONObject oldVr=local.optJSONObject("vr"),remoteVr=remote.optJSONObject("vr");
            if(oldVr!=null){if(remoteVr==null){remoteVr=new JSONObject();remote.put("vr",remoteVr);}for(String key:new String[]{"tracking_sensitivity","tracking_smoothing","tracking_invert_pitch"})if(!remoteVr.has(key)&&oldVr.has(key))remoteVr.put(key,oldVr.get(key));}
            local=remote;
        }}catch(Exception ignored){/* Per-file local settings also work with older servers. */}
        return local;
    }
    private double bounded(JSONObject value,String key,double fallback,double low,double high){double number=value.optDouble(key,fallback);return Double.isFinite(number)?Math.max(low,Math.min(high,number)):fallback;}
    private void applyFilePreferences(){
        JSONObject vr=filePreferences.optJSONObject("vr");if(vr==null)vr=new JSONObject();android.content.SharedPreferences defaults=getSharedPreferences("playback",0);
        vrFish=vr.optBoolean("fish",defaults.getBoolean("vr_fish",false));vrHeadset=vr.optBoolean("headset",defaults.getBoolean("vr_headset",false));vrSwap=vr.optBoolean("swap",defaults.getBoolean("vr_swap",false));
        vrTracking=vr.optBoolean("tracking",defaults.getBoolean("vr_tracking",true));vrSwipeSeek=vr.optBoolean("swipe_seek",defaults.getBoolean("vr_swipe_seek",true));
        vrVideo.configure(vrFish,vrHeadset,vrSwap,vrTracking);vrVideo.setSwipeSeeking(vrSwipeSeek);vrVideo.setFov((float)bounded(vr,"fov",defaults.getInt("vr_fov",90),50,110));
        vrVideo.setTrackingParameters((float)bounded(vr,"tracking_sensitivity",defaults.getFloat("vr_tracking_sensitivity",vrHeadset?1f:.75f),.25,1.5),(int)bounded(vr,"tracking_smoothing",defaults.getInt("vr_tracking_smoothing",40),0,150),vr.optBoolean("tracking_invert_pitch",defaults.getBoolean("vr_tracking_invert_pitch",false)));
        vrVideo.setViewAngles((float)bounded(vr,"yaw",0,-180,180),(float)bounded(vr,"pitch",0,-85,85));projection.setText(vrFish?"鱼眼":"标准");setVrImmersive(vrEnabled&&vrHeadset);
    }
    private void saveVrPreferences(){
        if(file==null)return;
        try{filePreferences.put("vr",new JSONObject().put("fish",vrFish).put("headset",vrHeadset).put("swap",vrSwap).put("tracking",vrTracking).put("swipe_seek",vrSwipeSeek)
            .put("fov",vrVideo.getFov()).put("yaw",vrVideo.getViewYaw()).put("pitch",vrVideo.getViewPitch()).put("tracking_sensitivity",vrVideo.getTrackingSensitivity()).put("tracking_smoothing",vrVideo.getTrackingSmoothing()).put("tracking_invert_pitch",vrVideo.getTrackingInvertPitch()));changedPreferences();}catch(Exception error){featureError(error);}
    }
    private void changedPreferences(){
        if(file==null)return;preferencesDirty=true;getSharedPreferences("media-preferences",0).edit().putString(preferenceKey(file.optLong("id")),filePreferences.toString()).apply();
        handler.removeCallbacks(persistPreferences);handler.postDelayed(persistPreferences,600);
    }
    private void flushPreferences(){
        handler.removeCallbacks(persistPreferences);if(!preferencesDirty||file==null||api==null)return;preferencesDirty=false;
        long id=file.optLong("id");String value=filePreferences.toString();
        network.execute(()->{try{api.post("/api/files/"+id+"/preferences",new JSONObject(value));}catch(Exception error){runOnUiThread(()->{if(!isDestroyed())Toast.makeText(this,"设置已保存在本机，服务端同步失败",Toast.LENGTH_SHORT).show();});}});
    }
    private void featureError(Exception error){runOnUiThread(()->{if(!isDestroyed())Toast.makeText(this,error.getMessage(),Toast.LENGTH_LONG).show();});}
    private void subtitleSettings(){
        if(file==null)return;LinearLayout fields=new LinearLayout(this);fields.setOrientation(LinearLayout.VERTICAL);fields.setPadding(dp(20),0,dp(20),0);
        EditText delay=new EditText(this),size=new EditText(this),position=new EditText(this);
        fields.addView(label("延后秒数（负数提前，±600 秒）",14));delay.setInputType(android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL|android.text.InputType.TYPE_NUMBER_FLAG_SIGNED);delay.setText(String.valueOf(filePreferences.optDouble("subtitle_delay",0)));fields.addView(delay);
        fields.addView(label("字号（12–64）",14));size.setInputType(android.text.InputType.TYPE_CLASS_NUMBER);size.setText(String.valueOf(filePreferences.optInt("subtitle_size",22)));fields.addView(size);
        fields.addView(label("垂直位置（5–95%，数值大更靠下）",14));position.setInputType(android.text.InputType.TYPE_CLASS_NUMBER);position.setText(String.valueOf(filePreferences.optInt("subtitle_position",90)));fields.addView(position);
        fields.addView(label("按视频记忆。字号和位置应用时重建播放内核并保留位置；ASS 自带样式可能优先。",13));
        ScrollView scroll=new ScrollView(this);scroll.addView(fields);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("字幕同步与样式").setView(scroll).setPositiveButton("应用",null).setNegativeButton("取消",null).create();dialog.show();
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view->{try{
            double seconds=Double.parseDouble(delay.getText().toString());int font=Integer.parseInt(size.getText().toString()),vertical=Integer.parseInt(position.getText().toString());
            if(!Double.isFinite(seconds)||Math.abs(seconds)>600||font<12||font>64||vertical<5||vertical>95)throw new Exception("请输入范围内的字幕参数");
            boolean restart=font!=filePreferences.optInt("subtitle_size",22)||vertical!=filePreferences.optInt("subtitle_position",90);
            filePreferences.put("subtitle_delay",seconds).put("subtitle_size",font).put("subtitle_position",vertical);changedPreferences();
            if(player!=null){if(restart){boolean paused=!player.isPlaying();restartDecoder(software);pauseAfterStyleChange=paused;}else player.setSpuDelay((long)(seconds*1_000_000));}dialog.dismiss();
        }catch(Exception error){featureError(error);}});
    }
    private void addBookmark(){
        if(file==null||player==null)return;long id=file.optLong("id"),moment=positionMs();LinearLayout fields=new LinearLayout(this);fields.setOrientation(LinearLayout.VERTICAL);fields.setPadding(dp(20),0,dp(20),0);
        EditText name=new EditText(this);name.setHint("名称（可留空）");name.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(120)});fields.addView(name);
        EditText note=new EditText(this);note.setHint("备注（可留空）");note.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(2000)});fields.addView(note);
        new AlertDialog.Builder(this).setTitle("添加书签 · "+clock(moment)).setView(fields).setPositiveButton("保存",(d,w)->{
            String title=name.getText().toString(),description=note.getText().toString();
            network.execute(()->{try{api.post("/api/files/"+id+"/bookmarks",new JSONObject().put("position",moment/1000.0).put("title",title).put("note",description));runOnUiThread(()->{if(!isDestroyed())Toast.makeText(this,"书签已保存，截图在电脑后台生成",Toast.LENGTH_SHORT).show();});}catch(Exception error){featureError(error);}});
        }).setNegativeButton("取消",null).show();
    }
    private void showBookmarks(){
        if(file==null)return;long id=file.optLong("id");network.execute(()->{try{JSONArray items=api.get("/api/files/"+id+"/bookmarks").getJSONArray("items");runOnUiThread(()->{
            if(isDestroyed()||file==null||file.optLong("id")!=id)return;if(items.length()==0){Toast.makeText(this,"还没有书签，可在播放设置中添加当前时间点",Toast.LENGTH_SHORT).show();return;}String[] names=new String[items.length()];for(int i=0;i<items.length();i++){JSONObject item=items.optJSONObject(i);names[i]=clock((long)(item.optDouble("position")*1000))+" · "+item.optString("title")+"\n"+item.optString("note");}
            AlertDialog dialog=new AlertDialog.Builder(this).setTitle("书签：点击跳转，长按删除").setItems(names,(d,index)->seekTo((long)(items.optJSONObject(index).optDouble("position")*1000))).setNegativeButton("关闭",null).create();dialog.show();
            dialog.getListView().setOnItemLongClickListener((parent,view,index,row)->{String mark=items.optJSONObject(index).optString("id");new AlertDialog.Builder(this).setTitle("书签操作").setItems(new String[]{"重新生成截图","删除书签"},(choice,selected)->network.execute(()->{try{api.post("/api/bookmarks/"+mark+(selected==0?"/capture":"/delete"),new JSONObject());runOnUiThread(()->{dialog.dismiss();if(!isDestroyed())showBookmarks();});}catch(Exception error){featureError(error);}})).show();return true;});
        });}catch(Exception error){featureError(error);}});
    }
    private void diagnostics(){
        TextView text=label("正在读取播放信息…",14);text.setTextIsSelectable(true);text.setPadding(dp(20),dp(12),dp(20),dp(12));ScrollView scroll=new ScrollView(this);scroll.addView(text);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("播放诊断").setView(scroll).setPositiveButton("关闭",null).setNeutralButton("复制",(d,w)->{
            android.content.ClipboardManager clipboard=(android.content.ClipboardManager)getSystemService(CLIPBOARD_SERVICE);clipboard.setPrimaryClip(android.content.ClipData.newPlainText("Lumen 播放诊断",text.getText()));}).create();
        final long[] previous={0,0};Runnable update=new Runnable(){public void run(){
            if(!dialog.isShowing()||player==null)return;
            StringBuilder data=new StringBuilder("内核：LibVLC\n解码策略：").append(software?"软件解码":"硬件优先，软件兜底（内核未公开实际硬解状态）");
            org.videolan.libvlc.interfaces.IMedia.VideoTrack track=player.getCurrentVideoTrack();if(track!=null)data.append("\n视频：").append(track.codec).append(" · ").append(track.width).append('×').append(track.height).append(" · ").append(track.frameRateNum/(double)Math.max(1,track.frameRateDen)).append(" fps");
            org.videolan.libvlc.interfaces.IMedia media=player.getMedia();if(media!=null){try{
                org.videolan.libvlc.interfaces.IMedia.Stats stats=media.getStats();if(stats!=null){long now=android.os.SystemClock.elapsedRealtime(),bytes=Integer.toUnsignedLong(stats.readBytes);double speed=previous[0]>0?((bytes-previous[1])&0xffffffffL)/1048576.0/Math.max(.001,(now-previous[0])/1000.0):0;previous[0]=now;previous[1]=bytes;
                    data.append("\n已解码帧：").append(stats.decodedVideo).append("\n已显示帧：").append(stats.displayedPictures).append("\n丢帧：").append(stats.lostPictures).append(String.format(java.util.Locale.ROOT,"\n网络读取：%.2f MiB/s",speed));}
            }finally{media.release();}}
            data.append("\n状态：").append(buffering?"缓冲":player.isPlaying()?"播放":"暂停").append("\n播放位置：").append(clock(positionMs())).append("\n字幕延后：").append(filePreferences.optDouble("subtitle_delay",0)).append(" 秒\n诊断不包含文件路径、服务器地址或访问密钥。");text.setText(data);handler.postDelayed(this,1000);
        }};dialog.setOnDismissListener(d->handler.removeCallbacks(update));dialog.show();handler.post(update);
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
        return stepEpisode(1,automatic);
    }
    private boolean stepEpisode(int direction,boolean automatic) {
        if(work==null||file==null)return false;
        JSONArray files=work.optJSONArray("files");
        if(files==null)return false;
        for(int i=0;i<files.length();i++)if(files.optJSONObject(i).optLong("id")==file.optLong("id")) {
            int next=i+direction;if(next<0||next>=files.length())break;
            long nextId=files.optJSONObject(next).optLong("id");stopPlayback(false);load(work.optLong("id"),nextId);return true;
        }
        if(!automatic)Toast.makeText(this,direction<0?"已经是第一个视频":"已经是最后一个视频",Toast.LENGTH_SHORT).show();return false;
    }
    private void setNavigationPending(boolean value){
        navigationPending=value;if(previousVideo!=null)previousVideo.setEnabled(!value);if(nextVideo!=null)nextVideo.setEnabled(!value);
    }
    private void stepVideo(int direction){
        if(navigationPending||work==null||file==null)return;
        if(stepEpisode(direction,true))return;
        if(queueMode){stepQueue(direction,false);return;}
        if(work.optString("kind").equals("series")){Toast.makeText(this,direction<0?"已经是第一集":"已经是最后一集",Toast.LENGTH_SHORT).show();return;}
        final long current=work.optLong("id");final int ticket=generation,hint=browsePosition;
        String supplied=getIntent().getStringExtra("browse_path");
        final String path=supplied!=null?supplied:"/api/works?kind="+Uri.encode(work.optString("kind"));
        setNavigationPending(true);status.setText(direction<0?"正在查找上个视频…":"正在查找下个视频…");
        network.execute(()->{try{
            VideoNavigator.Target target=VideoNavigator.adjacent(api,current,direction,path,hint,()->Thread.currentThread().isInterrupted()||ticket!=generation);
            runOnUiThread(()->{if(isDestroyed()||ticket!=generation)return;setNavigationPending(false);
                if(target==null){status.setText("当前列表没有更多视频");Toast.makeText(this,direction<0?"已经是第一个视频":"已经是最后一个视频",Toast.LENGTH_SHORT).show();return;}
                browsePosition=target.position;stopPlayback(false);load(target.id,direction<0?-1:0);
            });
        }catch(Exception error){runOnUiThread(()->{if(!isDestroyed()&&ticket==generation){setNavigationPending(false);status.setText("切换失败："+error.getMessage());Toast.makeText(this,"无法读取相邻视频，请检查连接后重试",Toast.LENGTH_SHORT).show();}});}});
    }
    private void stepQueue(int direction,boolean automatic){
        try{
            android.content.SharedPreferences prefs=getSharedPreferences("queue",0);JSONArray ids=new JSONArray(prefs.getString("ids","[]"));int current=-1;
            for(int i=0;i<ids.length();i++)if(ids.optLong(i)==work.optLong("id")){current=i;break;}
            int next=current+direction;
            if(current>=0&&prefs.getInt("repeat",0)==1&&ids.length()>0)next=(next+ids.length())%ids.length();
            if(current<0||next<0||next>=ids.length()){if(automatic)finish();else Toast.makeText(this,direction<0?"已经是队列第一个视频":"本轮队列已结束",Toast.LENGTH_SHORT).show();return;}
            prefs.edit().putInt("index",next).apply();stopPlayback(false);load(ids.getLong(next),direction<0?-1:0);
        }catch(Exception exception){error(exception);}
    }
    private void nextWork(boolean automatic) {
        if(!queueMode) {
            if(automatic)finish();else Toast.makeText(this,"请从媒体库菜单创建随机队列",Toast.LENGTH_SHORT).show();return;
        }
        stepQueue(1,automatic);
    }
    @Override protected void onStart(){super.onStart();started=true;if(controller!=null)controller.active(true);if(vrEnabled&&vrVideo!=null)vrVideo.onResume();if(api!=null){if(file!=null)startPlayback();else load(desiredWork,desiredFile);}}
    @Override protected void onPause(){if(controller!=null)controller.active(false);if(player!=null){player.pause();tick(false,false);}super.onPause();}
    @Override protected void onResume(){super.onResume();if(controller!=null)controller.active(true);if(root!=null){setPlayerImmersive(immersive);showControls(true);}}
    @Override protected void onStop(){flushPreferences();started=false;generation++;setNavigationPending(false);stopPlayback(false);if(vrEnabled&&vrVideo!=null)vrVideo.onPause();super.onStop();}
    @Override protected void onDestroy(){if(controller!=null)controller.release();handler.removeCallbacksAndMessages(null);network.shutdown();if(vrVideo!=null)vrVideo.release();super.onDestroy();}
}
