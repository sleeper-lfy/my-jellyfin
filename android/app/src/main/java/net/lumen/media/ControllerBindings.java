package net.lumen.media;

import java.util.HashMap;
import java.util.Map;

/** Stable action IDs and per-device HID / global media-key mappings. */
public final class ControllerBindings {
    public enum Action {
        TOGGLE("播放 / 暂停",false), PLAY("播放",false), PAUSE("暂停",false),
        FORWARD("快进 10 秒",true), BACKWARD("回退 10 秒",true),
        PROJECTION("标准 / 鱼眼切换",false), ZOOM_IN("拉近",true), ZOOM_OUT("拉远",true),
        RECENTER("回正朝向",false), RESET_VIEW("恢复初始视角与缩放",false), CONTROLS("显示 / 隐藏控制栏",false),
        NONE("不执行操作",false);
        public final String label;
        public final boolean repeatable;
        Action(String label,boolean repeatable){this.label=label;this.repeatable=repeatable;}
    }
    // Key codes follow android.view.KeyEvent; negative codes represent joystick directions/triggers.
    public static final int STICK_LEFT=-1,STICK_RIGHT=-2,STICK_UP=-3,STICK_DOWN=-4,TRIGGER_LEFT=-5,TRIGGER_RIGHT=-6,RIGHT_LEFT=-7,RIGHT_RIGHT=-8,RIGHT_UP=-9,RIGHT_DOWN=-10;
    private final Map<Integer,Action> defaults=new HashMap<>();
    private final Map<String,Map<Integer,Action>> overrides=new HashMap<>();
    public ControllerBindings(){
        bind(Action.TOGGLE,23,66,62,79,85,96); // DPAD center, enter, space, headset hook, play/pause, A
        bind(Action.PLAY,126);bind(Action.PAUSE,127,86);
        bind(Action.FORWARD,22,90,87,103,STICK_RIGHT,RIGHT_RIGHT);bind(Action.BACKWARD,21,89,88,102,STICK_LEFT,RIGHT_LEFT);
        bind(Action.ZOOM_IN,19,105,STICK_UP,RIGHT_UP,TRIGGER_RIGHT);bind(Action.ZOOM_OUT,20,104,STICK_DOWN,RIGHT_DOWN,TRIGGER_LEFT);
        bind(Action.PROJECTION,99);bind(Action.RECENTER,100);bind(Action.CONTROLS,97);bind(Action.RESET_VIEW,108);
    }
    private void bind(Action action,int... keys){for(int key:keys)defaults.put(key,action);}
    public void put(String device,int key,Action action){overrides.computeIfAbsent(device,k->new HashMap<>()).put(key,action);}
    public Action resolve(String device,int key){
        Map<Integer,Action> own=overrides.get(device),global=overrides.get("");
        if(own!=null&&own.containsKey(key))return own.get(key);
        if(global!=null&&global.containsKey(key))return global.get(key);
        return defaults.get(key);
    }
    public void clear(){overrides.clear();}
    public static Action parse(String name){try{return Action.valueOf(name);}catch(IllegalArgumentException|NullPointerException ignored){return null;}}
    /** Dead zone + hysteresis avoid accidental actions and chatter from analog controllers. */
    public static int direction(float value,int previous){
        if(previous<0&&value<-.35f)return -1;
        if(previous>0&&value>.35f)return 1;
        return value<-.65f?-1:value>.65f?1:0;
    }
}
