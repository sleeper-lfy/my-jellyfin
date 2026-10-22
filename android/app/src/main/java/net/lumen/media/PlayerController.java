package net.lumen.media;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.media.MediaMetadata;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import java.util.HashMap;
import java.util.Map;

/** Bluetooth HID/gamepads and AVRCP media controls share one action/mapping path. */
final class PlayerController {
    interface Host { void action(ControllerBindings.Action action); void seek(long position); }
    private final Activity activity;
    private final Host host;
    private final ControllerBindings bindings=new ControllerBindings();
    private final SharedPreferences preferences;
    private final MediaSession session;
    private final MediaSession.Callback transport;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final Map<String,Integer> directions=new HashMap<>();
    private final Map<String,ControllerBindings.Action> held=new HashMap<>();
    private final Map<String,Long> repeats=new HashMap<>();
    private boolean active;
    private AlertDialog captureDialog;
    private ControllerBindings.Action capture;
    private String title="";
    private long metadataDuration=-1;
    private final Runnable repeatMotion=new Runnable(){public void run(){
        if(!active||captureDialog!=null)return;
        for(ControllerBindings.Action action:held.values())if(action.repeatable)host.action(action);
        if(!held.isEmpty())handler.postDelayed(this,250);
    }};

    PlayerController(Activity activity,Host host){
        this.activity=activity;this.host=host;preferences=activity.getSharedPreferences("controller_bindings",0);
        for(Map.Entry<String,?> entry:preferences.getAll().entrySet()){
            int separator=entry.getKey().lastIndexOf(':');
            if(separator<0)continue;
            ControllerBindings.Action action=ControllerBindings.parse(String.valueOf(entry.getValue()));
            if(action==null)continue;
            try{bindings.put(entry.getKey().substring(0,separator),Integer.parseInt(entry.getKey().substring(separator+1)),action);}catch(NumberFormatException ignored){}
        }
        session=new MediaSession(activity,"Lumen playback");
        session.setFlags(MediaSession.FLAG_HANDLES_MEDIA_BUTTONS|MediaSession.FLAG_HANDLES_TRANSPORT_CONTROLS);
        transport=new MediaSession.Callback(){
            @Override public boolean onMediaButtonEvent(Intent intent){
                KeyEvent event=intent.getParcelableExtra(Intent.EXTRA_KEY_EVENT);
                return event!=null&&key(event);
            }
            @Override public void onPlay(){mediaKey(KeyEvent.KEYCODE_MEDIA_PLAY);}
            @Override public void onPause(){mediaKey(KeyEvent.KEYCODE_MEDIA_PAUSE);}
            @Override public void onStop(){mediaKey(KeyEvent.KEYCODE_MEDIA_STOP);}
            @Override public void onFastForward(){mediaKey(KeyEvent.KEYCODE_MEDIA_FAST_FORWARD);}
            @Override public void onRewind(){mediaKey(KeyEvent.KEYCODE_MEDIA_REWIND);}
            @Override public void onSkipToNext(){mediaKey(KeyEvent.KEYCODE_MEDIA_NEXT);}
            @Override public void onSkipToPrevious(){mediaKey(KeyEvent.KEYCODE_MEDIA_PREVIOUS);}
            @Override public void onSeekTo(long position){if(active)host.seek(position);}
        };
        session.setCallback(transport,handler);
    }
    void clearHeld(){held.clear();directions.clear();repeats.clear();handler.removeCallbacks(repeatMotion);}
    void active(boolean value){
        active=value;session.setActive(value);
        if(!value)clearHeld();
    }
    void state(boolean playing,boolean buffering,long position,long duration,String name){
        session.setPlaybackState(new PlaybackState.Builder()
            .setActions(PlaybackState.ACTION_PLAY|PlaybackState.ACTION_PAUSE|PlaybackState.ACTION_PLAY_PAUSE|
                PlaybackState.ACTION_STOP|PlaybackState.ACTION_FAST_FORWARD|PlaybackState.ACTION_REWIND|
                PlaybackState.ACTION_SKIP_TO_NEXT|PlaybackState.ACTION_SKIP_TO_PREVIOUS|PlaybackState.ACTION_SEEK_TO)
            .setState(buffering?PlaybackState.STATE_BUFFERING:playing?PlaybackState.STATE_PLAYING:PlaybackState.STATE_PAUSED,
                position,playing&&!buffering?1:0).build());
        if(!title.equals(name)||metadataDuration!=duration){
            title=name;metadataDuration=duration;session.setMetadata(new MediaMetadata.Builder().putString(MediaMetadata.METADATA_KEY_TITLE,name)
                .putLong(MediaMetadata.METADATA_KEY_DURATION,duration).build());
        }
    }
    private void mediaKey(int key){if(active){if(captureDialog!=null){assign("",key);return;}ControllerBindings.Action action=bindings.resolve("",key);if(action!=null)host.action(action);}}
    private static boolean media(int code){
        return code==79||code>=85&&code<=91||code==126||code==127||code==130;
    }
    private String device(KeyEvent event){return media(event.getKeyCode())?"":descriptor(event.getDevice());}
    private static String descriptor(InputDevice device){return device==null?"":device.getDescriptor();}
    boolean key(KeyEvent event){
        if(!active)return false;
        int code=event.getKeyCode();
        if(captureDialog!=null){
            if(event.getAction()==KeyEvent.ACTION_DOWN&&event.getRepeatCount()==0)assign(device(event),code);
            return true;
        }
        ControllerBindings.Action action=bindings.resolve(device(event),code);
        if(action==null)return false;
        if(event.getAction()==KeyEvent.ACTION_DOWN){
            String identity=device(event)+":"+code;
            long now=SystemClock.uptimeMillis();
            if(event.getRepeatCount()==0||(action.repeatable&&now-repeats.getOrDefault(identity,0L)>=250)){
                repeats.put(identity,now);host.action(action);
            }
        }else if(event.getAction()==KeyEvent.ACTION_UP)repeats.remove(device(event)+":"+code);
        return true;
    }
    boolean motion(MotionEvent event){
        if(!active||(event.getSource()&InputDevice.SOURCE_JOYSTICK)!=InputDevice.SOURCE_JOYSTICK)return false;
        int[][] axes={{MotionEvent.AXIS_X,ControllerBindings.STICK_LEFT,ControllerBindings.STICK_RIGHT},
            {MotionEvent.AXIS_Y,ControllerBindings.STICK_UP,ControllerBindings.STICK_DOWN},
            {MotionEvent.AXIS_Z,ControllerBindings.RIGHT_LEFT,ControllerBindings.RIGHT_RIGHT},
            {MotionEvent.AXIS_RZ,ControllerBindings.RIGHT_UP,ControllerBindings.RIGHT_DOWN},
            {MotionEvent.AXIS_HAT_X,ControllerBindings.STICK_LEFT,ControllerBindings.STICK_RIGHT},
            {MotionEvent.AXIS_HAT_Y,ControllerBindings.STICK_UP,ControllerBindings.STICK_DOWN},
            {MotionEvent.AXIS_LTRIGGER,0,ControllerBindings.TRIGGER_LEFT},
            {MotionEvent.AXIS_RTRIGGER,0,ControllerBindings.TRIGGER_RIGHT}};
        boolean handled=false,learning=captureDialog!=null;
        for(int[] axis:axes){
            handled|=axis(event,axis[0],axis[1],axis[2]);
            if(learning&&captureDialog==null)return true;
        }
        return handled;
    }
    private boolean axis(MotionEvent event,int axis,int negative,int positive){
        String device=descriptor(event.getDevice()),identity=device+":"+axis;
        int before=directions.getOrDefault(identity,0),after=ControllerBindings.direction(event.getAxisValue(axis),before);
        if(after==before)return held.containsKey(identity);
        directions.put(identity,after);held.remove(identity);
        if(after==0)return before!=0;
        int code=after<0?negative:positive;
        if(code==0)return false;
        if(captureDialog!=null){assign(device,code);return true;}
        ControllerBindings.Action action=bindings.resolve(device,code);
        if(action==null)return false;
        host.action(action);held.put(identity,action);
        handler.removeCallbacks(repeatMotion);handler.postDelayed(repeatMotion,450);
        return true;
    }
    void settings(){
        held.clear();handler.removeCallbacks(repeatMotion);
        String[] labels=new String[ControllerBindings.Action.values().length+2];
        for(int i=0;i<ControllerBindings.Action.values().length;i++)labels[i]=ControllerBindings.Action.values()[i].label+" · 绑定按键";
        labels[labels.length-2]="查看已保存的映射";labels[labels.length-1]="恢复默认映射";
        new AlertDialog.Builder(activity).setTitle("蓝牙 / 手柄按键映射").setItems(labels,(dialog,index)->{
            if(index<ControllerBindings.Action.values().length)capture(ControllerBindings.Action.values()[index]);
            else if(index==labels.length-2)showSaved();
            else new AlertDialog.Builder(activity).setMessage("清除所有自定义按键，恢复默认映射？")
                .setPositiveButton("恢复",(d,w)->{bindings.clear();preferences.edit().clear().apply();settings();}).setNegativeButton("取消",null).show();
        }).setNegativeButton("关闭",null).show();
    }
    private void capture(ControllerBindings.Action action){
        capture=action;
        TextView info=new TextView(activity);info.setPadding(32,24,32,24);
        info.setText("请按蓝牙遥控器、键盘或手柄上要绑定的按键，也可推动摇杆或按下扳机。\n\nHID 按设备保存；耳机 / AVRCP 媒体按键使用通用映射。系统保留的返回、主页、电源键不可绑定。");
        captureDialog=new AlertDialog(activity){
            @Override public boolean dispatchKeyEvent(KeyEvent event){
                int code=event.getKeyCode();
                if(code==KeyEvent.KEYCODE_BACK||code==KeyEvent.KEYCODE_HOME||code==KeyEvent.KEYCODE_POWER)return super.dispatchKeyEvent(event);
                if(event.getAction()==KeyEvent.ACTION_DOWN&&event.getRepeatCount()==0)assign(device(event),code);
                return true;
            }
            @Override public boolean dispatchGenericMotionEvent(MotionEvent event){return motion(event)||super.dispatchGenericMotionEvent(event);}
        };
        captureDialog.setTitle("绑定："+action.label);captureDialog.setView(info);
        captureDialog.setButton(AlertDialog.BUTTON_NEGATIVE,"取消",(d,w)->{});
        captureDialog.setOnDismissListener(d->{capture=null;captureDialog=null;held.clear();directions.clear();});
        captureDialog.show();
    }
    private void assign(String device,int code){
        if(captureDialog==null||capture==null)return;
        bindings.put(device,code,capture);preferences.edit().putString(device+":"+code,capture.name()).apply();
        Toast.makeText(activity,"已绑定 "+keyName(code)+" → "+capture.label,Toast.LENGTH_SHORT).show();
        AlertDialog dialog=captureDialog;captureDialog=null;capture=null;clearHeld();dialog.dismiss();
    }
    private static String keyName(int code){
        switch(code){
            case -1:return "摇杆 / 方向轴左";case -2:return "摇杆 / 方向轴右";
            case -3:return "摇杆 / 方向轴上";case -4:return "摇杆 / 方向轴下";
            case -5:return "左扳机";case -6:return "右扳机";
            case -7:return "右摇杆左";case -8:return "右摇杆右";case -9:return "右摇杆上";case -10:return "右摇杆下";
            default:return KeyEvent.keyCodeToString(code);
        }
    }
    private void showSaved(){
        StringBuilder text=new StringBuilder("默认：方向左 / 右 ±10 秒；中键 / A / 媒体键 播放暂停；上 / 下 拉近拉远；X 切换投影；Y 回正；Start 恢复初始视角；B 控制栏。\n\n自定义：\n");
        for(Map.Entry<String,?> entry:preferences.getAll().entrySet()){
            int split=entry.getKey().lastIndexOf(':');if(split<0)continue;
            try{
                int code=Integer.parseInt(entry.getKey().substring(split+1));ControllerBindings.Action action=ControllerBindings.parse(String.valueOf(entry.getValue()));
                if(action!=null)text.append(split==0?"通用媒体键":"设备 "+entry.getKey().substring(0,Math.min(12,split)))
                    .append(" · ").append(keyName(code)).append(" → ").append(action.label).append('\n');
            }catch(NumberFormatException ignored){}
        }
        TextView info=new TextView(activity);info.setText(text);info.setPadding(32,16,32,16);
        ScrollView scroll=new ScrollView(activity);scroll.addView(info);
        new AlertDialog.Builder(activity).setTitle("按键映射").setView(scroll).setPositiveButton("关闭",null).show();
    }
    void release(){active(false);handler.removeCallbacksAndMessages(null);if(captureDialog!=null)captureDialog.dismiss();session.release();}
}
