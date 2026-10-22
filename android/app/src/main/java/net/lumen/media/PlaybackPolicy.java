package net.lumen.media;

/** Display geometry and seek arithmetic, independent of Android and the decoder. */
public final class PlaybackPolicy {
    public static final int UNKNOWN=0, LANDSCAPE=1, PORTRAIT=2;
    private PlaybackPolicy() {}
    public static int orientation(int width,int height,int sarNum,int sarDen,boolean rotated) {
        if(width<=0||height<=0)return UNKNOWN;
        double displayWidth=width*(sarNum>0&&sarDen>0?(double)sarNum/sarDen:1);
        double displayHeight=height;
        if(rotated){double previous=displayWidth;displayWidth=displayHeight;displayHeight=previous;}
        return displayWidth>displayHeight?LANDSCAPE:PORTRAIT;
    }
    public static long seek(long position,long duration,long delta) {
        long target=Math.max(0,position+delta);
        return duration>0?Math.min(duration,target):target;
    }
    public static float fov(float value) { return Math.max(50,Math.min(110,value)); }
}
