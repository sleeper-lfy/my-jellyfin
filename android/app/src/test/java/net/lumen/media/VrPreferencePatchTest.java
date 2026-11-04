package net.lumen.media;

import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class) @Config(sdk=33)
public class VrPreferencePatchTest {
    @Test public void changingSubtitleDoesNotPinDirectoryVrDefaults()throws Exception{
        JSONObject value=new JSONObject("{\"vr\":{\"fov\":70,\"fish\":true},\"_vr_inherited\":{\"fov\":70,\"fish\":true},\"subtitle_size\":28}");
        JSONObject upload=VrPreferencePatch.upload(value);
        assertEquals(28,upload.getInt("subtitle_size"));assertFalse(upload.has("vr"));assertFalse(upload.has("_vr_inherited"));
    }
    @Test public void changingOneVrFieldUploadsOnlyThatOverride()throws Exception{
        JSONObject previous=new JSONObject("{\"fov\":70,\"fish\":true,\"yaw\":0}");
        JSONObject value=new JSONObject().put("vr",previous).put("_vr_inherited",new JSONObject(previous.toString()));
        JSONObject current=new JSONObject(previous.toString()).put("fov",80);
        VrPreferencePatch.record(value,previous,current);
        JSONObject upload=VrPreferencePatch.upload(value);
        assertEquals(1,upload.getJSONObject("vr").length());assertEquals(80,upload.getJSONObject("vr").getInt("fov"));
        JSONObject next=new JSONObject(current.toString()).put("yaw",15);
        VrPreferencePatch.record(value,current,next);
        assertEquals(2,VrPreferencePatch.upload(value).getJSONObject("vr").length());
        assertFalse(VrPreferencePatch.upload(value).getJSONObject("vr").has("fish"));
    }
    @Test public void oldServerKeepsExistingPerFileSerialization()throws Exception{
        JSONObject value=new JSONObject().put("vr",new JSONObject().put("fish",true));
        VrPreferencePatch.record(value,new JSONObject(),new JSONObject().put("fish",true).put("fov",80));
        assertEquals(2,VrPreferencePatch.upload(value).getJSONObject("vr").length());
    }
}
