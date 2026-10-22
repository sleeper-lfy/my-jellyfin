package net.lumen.media;

/** Horizontal swipe math: one screen width moves at most 120 seconds, with millisecond precision. */
public final class SeekGesture {
    private SeekGesture(){}
    public static long target(long start,long duration,float displacement,int width){
        long span=duration>0?Math.min(120000,duration):120000;
        return PlaybackPolicy.seek(start,duration,Math.round(displacement/Math.max(1,width)*span));
    }
    public static boolean horizontal(float dx,float dy,float slop){return Math.abs(dx)>slop&&Math.abs(dx)>Math.abs(dy)*1.3f;}
}
