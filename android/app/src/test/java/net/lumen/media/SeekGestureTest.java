package net.lumen.media;
import org.junit.Test;
import static org.junit.Assert.*;
public class SeekGestureTest {
    @Test public void horizontalSwipesSeekRelativeToTouchDownAndClampAtEnds(){
        assertEquals(80000,SeekGesture.target(50000,600000,250,1000));
        assertEquals(20000,SeekGesture.target(50000,600000,-250,1000));
        assertEquals(0,SeekGesture.target(10000,600000,-1000,1000));
        assertEquals(600000,SeekGesture.target(590000,600000,1000,1000));
    }
    @Test public void shortVideosHaveProportionalControlAndVerticalMotionDoesNotSeek(){
        assertEquals(15000,SeekGesture.target(0,60000,250,1000));
        assertFalse(SeekGesture.horizontal(4,1,8));
        assertFalse(SeekGesture.horizontal(15,30,8));
        assertTrue(SeekGesture.horizontal(-60,5,8));
    }
}
