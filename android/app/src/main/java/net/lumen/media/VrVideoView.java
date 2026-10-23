package net.lumen.media;

import android.content.Context;
import android.graphics.SurfaceTexture;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.opengl.GLES11Ext;
import android.opengl.GLES20;
import android.opengl.GLSurfaceView;
import android.opengl.Matrix;
import android.view.MotionEvent;
import android.view.ScaleGestureDetector;
import android.view.ViewConfiguration;
import android.view.Surface;
import android.view.SurfaceHolder;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.FloatBuffer;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.microedition.khronos.egl.EGLConfig;
import javax.microedition.khronos.opengles.GL10;

/** VLC decodes into an OES texture; this view projects each eye on a VR180 hemisphere. */
public final class VrVideoView extends GLSurfaceView implements GLSurfaceView.Renderer, SensorEventListener {
    public interface Listener { void ready(); void lost(); void failed(String reason); void tap(); void zoom(float fov); boolean gesture(android.view.View view,MotionEvent event); default void viewChanged(){} }
    private final Listener listener;
    private final SensorManager sensors;
    private final Sensor rotation;
    private final ScaleGestureDetector scaleGesture;
    private final int touchSlop;
    private boolean moved=false;
    private boolean swipeSeeking=true;
    public void setSwipeSeeking(boolean enabled){swipeSeeking=enabled;}
    private float downX,downY;
    private volatile SurfaceTexture texture;
    private volatile boolean surfaceReady=false;
    private final AtomicBoolean frame = new AtomicBoolean();
    private final float[] textureMatrix = new float[16];
    private final FloatBuffer vertices = ByteBuffer.allocateDirect(8*4).order(ByteOrder.nativeOrder()).asFloatBuffer();
    private int program, textureId, width, height;
    private volatile int maxTextureSize=4096;
    private volatile int videoWidth=1920, videoHeight=1080;
    private volatile boolean fish=false, headset=false, swap=false, tracking=true;
    private volatile float yaw=0, pitch=0, sensorYaw=0, sensorPitch=0, fov=90;
    private boolean resumed=false;
    private final VrMotionFilter motion=new VrMotionFilter();
    private float touchX, touchY;
    private final float[] rotationMatrix=new float[9];

    public VrVideoView(Context context, Listener listener) {
        super(context); this.listener=listener;
        touchSlop=ViewConfiguration.get(context).getScaledTouchSlop();
        scaleGesture=new ScaleGestureDetector(context,new ScaleGestureDetector.SimpleOnScaleGestureListener(){
            @Override public boolean onScale(ScaleGestureDetector detector){
                moved=true;setFov(fov/detector.getScaleFactor());listener.zoom(fov);return true;
            }
        });
        sensors=(SensorManager)context.getSystemService(Context.SENSOR_SERVICE);
        rotation=sensors.getDefaultSensor(Sensor.TYPE_GAME_ROTATION_VECTOR);
        setEGLContextClientVersion(2);
        setPreserveEGLContextOnPause(true);
        vertices.put(new float[]{-1,-1,1,-1,-1,1,1,1}).position(0);
        Matrix.setIdentityM(textureMatrix,0);
        setRenderer(this); setRenderMode(RENDERMODE_WHEN_DIRTY);
    }
    public SurfaceTexture videoTexture() { return surfaceReady?texture:null; }
    public boolean hasTracking() { return rotation != null; }
    public void configure(boolean fisheye, boolean stereoDisplay, boolean swapEyes, boolean headTracking) {
        if(tracking!=headTracking){motion.reset();sensorYaw=sensorPitch=0;}
        fish=fisheye; headset=stereoDisplay; swap=swapEyes; tracking=headTracking;
        updateSensor(); requestRender();
    }
    public void setFov(float degrees) { fov=PlaybackPolicy.fov(degrees);requestRender(); }
    public float getFov(){return fov;}
    public float getViewYaw(){return yaw;}
    public float getViewPitch(){return pitch;}
    public void setViewAngles(float horizontal,float vertical){yaw=VrProjection.wrap(horizontal);pitch=VrProjection.clampPitch(vertical);requestRender();}
    public void setTrackingParameters(float sensitivity,int smoothingMs,boolean invertPitch){motion.configure(sensitivity,smoothingMs,invertPitch);}
    public float getTrackingSensitivity(){return motion.sensitivity();}
    public int getTrackingSmoothing(){return motion.smoothingMs();}
    public boolean getTrackingInvertPitch(){return motion.inverted();}
    public void recenter() { yaw=pitch=sensorYaw=sensorPitch=0;motion.reset();requestRender(); }
    public int[] setVideoSize(int w,int h) {
        if(w<=0||h<=0)return new int[]{videoWidth,videoHeight};
        double scale=Math.min(1.0,(double)maxTextureSize/Math.max(w,h));
        int targetWidth=Math.max(2,((int)(w*scale)/2)*2),targetHeight=Math.max(2,((int)(h*scale)/2)*2);
        videoWidth=targetWidth;videoHeight=targetHeight;
        queueEvent(()->{if(texture!=null)texture.setDefaultBufferSize(targetWidth,targetHeight);});
        return new int[]{targetWidth,targetHeight};
    }
    @Override public void onResume() { super.onResume();resumed=true;sensorYaw=sensorPitch=0;motion.reset();updateSensor(); }
    @Override public void onPause() { resumed=false;sensors.unregisterListener(this);super.onPause(); }
    private void updateSensor() {
        sensors.unregisterListener(this);
        if(resumed && tracking && rotation!=null)sensors.registerListener(this,rotation,SensorManager.SENSOR_DELAY_GAME);
        if(!tracking)sensorYaw=sensorPitch=0;
    }
    @Override public void surfaceDestroyed(SurfaceHolder holder) {
        surfaceReady=false;
        listener.lost(); // Detach VLC before destroying its consumer surface.
        super.surfaceDestroyed(holder);
    }
    private static int compile(int kind,String source) {
        int shader=GLES20.glCreateShader(kind);GLES20.glShaderSource(shader,source);GLES20.glCompileShader(shader);
        int[] ok=new int[1];GLES20.glGetShaderiv(shader,GLES20.GL_COMPILE_STATUS,ok,0);
        if(ok[0]==0)throw new IllegalStateException(GLES20.glGetShaderInfoLog(shader));return shader;
    }
    @Override public void onSurfaceCreated(GL10 gl,EGLConfig config) {
        try {
            if(texture!=null){texture.release();texture=null;}
            int[] maximum=new int[1];GLES20.glGetIntegerv(GLES20.GL_MAX_TEXTURE_SIZE,maximum,0);maxTextureSize=maximum[0];
            int[] ids=new int[1];GLES20.glGenTextures(1,ids,0);textureId=ids[0];
            GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,textureId);
            GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,GLES20.GL_TEXTURE_MIN_FILTER,GLES20.GL_LINEAR);
            GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,GLES20.GL_TEXTURE_MAG_FILTER,GLES20.GL_LINEAR);
            GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,GLES20.GL_TEXTURE_WRAP_S,GLES20.GL_CLAMP_TO_EDGE);
            GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,GLES20.GL_TEXTURE_WRAP_T,GLES20.GL_CLAMP_TO_EDGE);
            int vs=compile(GLES20.GL_VERTEX_SHADER,"attribute vec2 position; varying vec2 uv; void main(){uv=position*.5+.5;gl_Position=vec4(position,0,1);}");
            int fs=compile(GLES20.GL_FRAGMENT_SHADER,VrProjection.FRAGMENT);
            program=GLES20.glCreateProgram();GLES20.glAttachShader(program,vs);GLES20.glAttachShader(program,fs);GLES20.glLinkProgram(program);
            GLES20.glDeleteShader(vs);GLES20.glDeleteShader(fs);
            int[] ok=new int[1];GLES20.glGetProgramiv(program,GLES20.GL_LINK_STATUS,ok,0);
            if(ok[0]==0)throw new IllegalStateException(GLES20.glGetProgramInfoLog(program));
            texture=new SurfaceTexture(textureId);texture.setDefaultBufferSize(videoWidth,videoHeight);
            texture.setOnFrameAvailableListener(t->{frame.set(true);requestRender();});

        }catch(RuntimeException error){post(()->listener.failed(error.getMessage()));}
    }
    @Override public void onSurfaceChanged(GL10 gl,int w,int h) { width=w;height=h;surfaceReady=true;post(listener::ready); }
    private int uniform(String name) { return GLES20.glGetUniformLocation(program,name); }
    @Override public void onDrawFrame(GL10 gl) {
        GLES20.glClearColor(0,0,0,1);GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT);
        if(texture==null||program==0||height==0)return;
        if(frame.getAndSet(false)){texture.updateTexImage();texture.getTransformMatrix(textureMatrix);}
        GLES20.glUseProgram(program);GLES20.glActiveTexture(GLES20.GL_TEXTURE0);GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,textureId);
        GLES20.glUniform1i(uniform("video"),0);GLES20.glUniformMatrix4fv(uniform("texMatrix"),1,false,textureMatrix,0);
        GLES20.glUniform2f(uniform("angles"),(float)Math.toRadians(yaw+sensorYaw),(float)Math.toRadians(VrProjection.clampPitch(pitch+sensorPitch)));
        GLES20.glUniform1f(uniform("tanHalfFov"),(float)Math.tan(Math.toRadians(fov/2)));
        GLES20.glUniform1i(uniform("fish"),fish?1:0);
        GLES20.glUniform2f(uniform("texel"),1f/Math.max(1,videoWidth/2),.5f/Math.max(1,videoHeight));
        int attr=GLES20.glGetAttribLocation(program,"position");GLES20.glEnableVertexAttribArray(attr);vertices.position(0);
        GLES20.glVertexAttribPointer(attr,2,GLES20.GL_FLOAT,false,0,vertices);
        int eyes=headset?2:1;
        for(int eye=0;eye<eyes;eye++) {
            int left=eye*width/eyes,right=(eye+1)*width/eyes;
            GLES20.glViewport(left,0,right-left,height);
            GLES20.glUniform1f(uniform("aspect"),(float)(right-left)/height);
            GLES20.glUniform1f(uniform("eye"),swap?1-eye:eye);
            GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP,0,4);
        }
        GLES20.glDisableVertexAttribArray(attr);
    }
    @Override public boolean onTouchEvent(MotionEvent event) {
        scaleGesture.onTouchEvent(event);
        if(swipeSeeking)return listener.gesture(this,event);
        if(event.getActionMasked()==MotionEvent.ACTION_DOWN){
            downX=touchX=event.getX();downY=touchY=event.getY();moved=false;return true;
        }
        if(event.getPointerCount()>1||event.getActionMasked()==MotionEvent.ACTION_POINTER_UP){
            moved=true;touchX=event.getX();touchY=event.getY();return true;
        }
        if(event.getActionMasked()==MotionEvent.ACTION_MOVE){
            if(Math.hypot(event.getX()-downX,event.getY()-downY)>touchSlop)moved=true;
            if(moved&&!scaleGesture.isInProgress()){
                yaw=VrProjection.wrap(yaw-(event.getX()-touchX)*.15f);
                pitch=VrProjection.clampPitch(pitch+(event.getY()-touchY)*.15f);
                requestRender();
            }
            touchX=event.getX();touchY=event.getY();return true;
        }
        if(event.getActionMasked()==MotionEvent.ACTION_UP){if(!moved)performClick();else listener.viewChanged();return true;}
        return true;
    }
    @Override public boolean performClick(){super.performClick();listener.tap();return true;}
    @Override public void onSensorChanged(SensorEvent event) {
        if(!tracking||!resumed)return;
        SensorManager.getRotationMatrixFromVector(rotationMatrix,event.values);
        float azimuth=VrMotionFilter.heading(rotationMatrix),elevation=VrMotionFilter.elevation(rotationMatrix);
        motion.update(azimuth,elevation,event.timestamp);sensorYaw=motion.yaw();sensorPitch=motion.pitch();requestRender();
    }
    @Override public void onAccuracyChanged(Sensor sensor,int accuracy) {}
    public void release() {
        sensors.unregisterListener(this);
        // Call after the decoder and GL thread have stopped.
        if(texture!=null){texture.release();texture=null;}
    }
}
