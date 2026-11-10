package net.lumen.media;

/** Monotonic playback measurements. Counters describe one decoder/bridge instance. */
final class PlaybackMeasurements {
    private long bufferingSince=-1,bufferedMs=0,seekSince=-1,seekTarget=0,seekOrigin=0,candidatePosition=-1,candidateTime=-1;
    int bufferingCount;
    long lastSeekMs=-1;
    void buffering(boolean active,long now) {
        if(active&&bufferingSince<0){bufferingSince=now;bufferingCount++;}
        else if(!active&&bufferingSince>=0){bufferedMs+=Math.max(0,now-bufferingSince);bufferingSince=-1;}
    }
    long bufferingMs(long now){return bufferedMs+(bufferingSince<0?0:Math.max(0,now-bufferingSince));}
    void seek(long target,long origin,long now){seekTarget=target;seekOrigin=origin;seekSince=now;lastSeekMs=-1;candidatePosition=-1;candidateTime=-1;}
    void progress(long position,boolean playing,long now){
        // Native TimeChanged is a clock response, not a frame-presentation callback.
        // Ignore queued positions at the old location and require two advancing samples.
        if(seekSince<0||!playing||bufferingSince>=0||position==seekOrigin||position<seekTarget||position-seekTarget>1500)return;
        if(candidatePosition>=0&&position>candidatePosition&&now>candidateTime){lastSeekMs=Math.max(0,now-seekSince);seekSince=-1;}
        else {candidatePosition=position;candidateTime=now;}
    }
    boolean seeking(){return seekSince>=0;}

    static final class Sample {
        private long previousTime=-1,previousBytes;
        private int previousDisplayed,previousLost;
        boolean ready;
        double mebibytesPerSecond,displayedPerSecond;
        long newlyLost;
        void update(long now,long bytes,int displayed,int lost){
            ready=previousTime>=0&&now>previousTime&&bytes>=previousBytes&&displayed>=previousDisplayed&&lost>=previousLost;
            if(ready){double seconds=(now-previousTime)/1000.0;mebibytesPerSecond=(bytes-previousBytes)/1048576.0/seconds;displayedPerSecond=(displayed-previousDisplayed)/seconds;newlyLost=(long)lost-previousLost;}
            previousTime=now;previousBytes=bytes;previousDisplayed=displayed;previousLost=lost;
        }
    }
}
