package net.lumen.media;
import org.junit.Test;
import static org.junit.Assert.*;
public class PlaybackPolicyTest {
    @Test public void displayShapeIncludesPixelAspectAndRotation(){
        assertEquals(PlaybackPolicy.LANDSCAPE,PlaybackPolicy.orientation(1920,1080,1,1,false));
        assertEquals(PlaybackPolicy.PORTRAIT,PlaybackPolicy.orientation(1080,1920,1,1,false));
        assertEquals(PlaybackPolicy.PORTRAIT,PlaybackPolicy.orientation(1920,1080,1,1,true));
        assertEquals(PlaybackPolicy.LANDSCAPE,PlaybackPolicy.orientation(1080,1920,1,1,true));
        assertEquals(PlaybackPolicy.LANDSCAPE,PlaybackPolicy.orientation(720,900,2,1,false));
        assertEquals(PlaybackPolicy.PORTRAIT,PlaybackPolicy.orientation(720,900,2,1,true));
        assertEquals(PlaybackPolicy.UNKNOWN,PlaybackPolicy.orientation(0,1080,1,1,false));
        assertEquals(PlaybackPolicy.PORTRAIT,PlaybackPolicy.orientation(720,720,0,0,false));
    }
    @Test public void seekingClampsToBothEndsAndUnknownDurationIsAllowed(){
        assertEquals(0,PlaybackPolicy.seek(5000,60000,-10000));
        assertEquals(60000,PlaybackPolicy.seek(55000,60000,10000));
        assertEquals(25000,PlaybackPolicy.seek(15000,0,10000));
    }
    @Test public void zoomNeverLeavesSupportedProjectionRange(){
        assertEquals(50,PlaybackPolicy.fov(1),.001);
        assertEquals(110,PlaybackPolicy.fov(500),.001);
        assertEquals(90,PlaybackPolicy.fov(90),.001);
    }
}
