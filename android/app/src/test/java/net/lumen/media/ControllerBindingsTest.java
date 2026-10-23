package net.lumen.media;
import org.junit.Test;
import static org.junit.Assert.*;
import static net.lumen.media.ControllerBindings.Action.*;
public class ControllerBindingsTest {
    @Test public void defaultRemoteAndGamepadActionsCoverPlaybackAndVr(){
        ControllerBindings bindings=new ControllerBindings();
        assertEquals(TOGGLE,bindings.resolve("remote",85));
        assertEquals(BACKWARD,bindings.resolve("remote",21));
        assertEquals(FORWARD,bindings.resolve("remote",22));
        assertEquals(NEXT_EPISODE,bindings.resolve("remote",87));
        assertEquals(PREVIOUS_EPISODE,bindings.resolve("remote",88));
        assertFalse(NEXT_EPISODE.repeatable);assertFalse(PREVIOUS_EPISODE.repeatable);
        assertEquals(ZOOM_IN,bindings.resolve("pad",19));
        assertEquals(ZOOM_OUT,bindings.resolve("pad",20));
        assertEquals(PROJECTION,bindings.resolve("pad",99));
        assertEquals(RECENTER,bindings.resolve("pad",100));
        assertEquals(RESET_VIEW,bindings.resolve("pad",108));
        assertNull(bindings.resolve("remote",24)); // Volume remains available to Android unless explicitly bound.
    }
    @Test public void overridesArePersistentIdsAndDeviceSpecificWithGlobalFallback(){
        ControllerBindings bindings=new ControllerBindings();
        bindings.put("",85,RECENTER);bindings.put("pad-a",85,PROJECTION);bindings.put("pad-a",22,NONE);
        assertEquals(PROJECTION,bindings.resolve("pad-a",85));
        assertEquals(RECENTER,bindings.resolve("pad-b",85));
        assertEquals(NONE,bindings.resolve("pad-a",22));
        assertEquals(FORWARD,bindings.resolve("pad-b",22));
        assertNull(ControllerBindings.parse("future action"));
        bindings.clear();assertEquals(TOGGLE,bindings.resolve("pad-a",85));
    }
    @Test public void joystickHysteresisReleasesBeforeSwitchingAndIgnoresDrift(){
        assertEquals(0,ControllerBindings.direction(.2f,0));
        assertEquals(1,ControllerBindings.direction(.8f,0));
        assertEquals(1,ControllerBindings.direction(.5f,1));
        assertEquals(0,ControllerBindings.direction(.3f,1));
        assertEquals(-1,ControllerBindings.direction(-.9f,1));
        assertEquals(0,ControllerBindings.direction(-.1f,-1));
    }
}
