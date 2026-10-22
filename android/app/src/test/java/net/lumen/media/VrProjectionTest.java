package net.lumen.media;
import org.junit.Test;
import static org.junit.Assert.*;
public class VrProjectionTest {
    @Test public void onlyVrCategoryAutomaticallyEnablesVr() {
        assertTrue(VrProjection.autoEnable("vr"));
        for(String kind:new String[]{"movie","series","other","",null})assertFalse(VrProjection.autoEnable(kind));
    }
    @Test public void centerSelectsSeparateEyesAndCanSwap() {
        for(boolean fish:new boolean[]{false,true}) {
            assertArrayEquals(new double[]{.25,.5},VrProjection.uv(0,0,1,fish,0,false),1e-7);
            assertArrayEquals(new double[]{.75,.5},VrProjection.uv(0,0,1,fish,1,false),1e-7);
            assertArrayEquals(new double[]{.75,.5},VrProjection.uv(0,0,1,fish,0,true),1e-7);
        }
    }
    @Test public void hemisphereEdgesAndBackAreHandled() {
        for(boolean fish:new boolean[]{false,true}) {
            assertNull(VrProjection.uv(0,0,-1,fish,0,false));
            assertArrayEquals(new double[]{.5,.5},VrProjection.uv(1,0,0,fish,0,false),1e-7);
            assertArrayEquals(new double[]{.25,0},VrProjection.uv(0,1,0,fish,0,false),1e-7);
        }
        assertNull(VrProjection.uv(0,0,0,false,0,false));
    }
    @Test public void fishAndStandardHaveDifferentDiagonalMapping() {
        double[] standard=VrProjection.uv(1,1,1,false,0,false),fish=VrProjection.uv(1,1,1,true,0,false);
        assertTrue(Math.abs(standard[0]-fish[0])>.01);
        assertTrue(fish[0]>=0&&fish[0]<=.5&&fish[1]>=0&&fish[1]<=1);
    }
    @Test public void orientationWrapAvoidsFullTurnJumps() {
        assertEquals(2,VrProjection.wrap(-358),.0001);
        assertEquals(-2,VrProjection.wrap(358),.0001);
        assertEquals(85,VrProjection.clampPitch(100),.0001);
    }
}
