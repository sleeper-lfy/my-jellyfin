package net.lumen.media;

/** Time-based filtering in degrees; wraparound never becomes a 360-degree jump. */
final class VrMotionFilter {
    private final VrPoseTracker pose=new VrPoseTracker();
    void update(float[] matrix,long nanos){if(pose.update(matrix))update(pose.yaw(),pose.pitch(),nanos);}
    private boolean ready,invertPitch;
    private long timestamp;
    private float lastYaw,originPitch,totalYaw,yaw,pitch;
    private float sensitivity=1;
    private int smoothingMs=40;
    void configure(float gain,int smoothing,boolean inverted){sensitivity=Float.isFinite(gain)?Math.max(.25f,Math.min(1.5f,gain)):1;smoothingMs=Math.max(0,Math.min(150,smoothing));invertPitch=inverted;}
    float sensitivity(){return sensitivity;}
    int smoothingMs(){return smoothingMs;}
    boolean inverted(){return invertPitch;}
    void reset(){pose.reset();ready=false;totalYaw=yaw=pitch=0;timestamp=0;}
    void update(float rawYaw,float rawPitch,long nanos){
        if(!Float.isFinite(rawYaw)||!Float.isFinite(rawPitch))return;
        if(!ready){ready=true;lastYaw=rawYaw;originPitch=rawPitch;timestamp=nanos;return;}
        if(nanos<=timestamp)return;
        totalYaw+=VrProjection.wrap(rawYaw-lastYaw);lastYaw=rawYaw;
        float targetYaw=VrProjection.wrap(totalYaw*sensitivity),targetPitch=VrProjection.clampPitch((rawPitch-originPitch)*sensitivity*(invertPitch?-1:1));
        float seconds=Math.min(.1f,(nanos-timestamp)/1_000_000_000f);timestamp=nanos;
        float alpha=smoothingMs==0?1:(float)(1-Math.exp(-seconds/(smoothingMs/1000.0)));
        float delta=VrProjection.wrap(targetYaw-yaw);
        if(Math.abs(delta)>.08f)yaw=VrProjection.wrap(yaw+alpha*delta);
        if(Math.abs(targetPitch-pitch)>.08f)pitch=VrProjection.clampPitch(pitch+alpha*(targetPitch-pitch));
    }
    float yaw(){return yaw;}
    float pitch(){return pitch;}
}
