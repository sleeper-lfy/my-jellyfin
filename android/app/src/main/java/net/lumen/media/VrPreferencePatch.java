package net.lumen.media;

import org.json.JSONObject;
import org.json.JSONException;
import java.util.Iterator;

/** Effective directory defaults must not become file overrides when another setting changes. */
final class VrPreferencePatch {
    private VrPreferencePatch() {}
    static void record(JSONObject preferences, JSONObject previous, JSONObject current) throws JSONException {
        if (preferences.has("_vr_inherited")) {
            JSONObject patch=preferences.optJSONObject("_vr_patch");
            if(patch==null)patch=new JSONObject();
            for(Iterator<String> keys=current.keys();keys.hasNext();) {
                String key=keys.next();Object old=previous.opt(key),value=current.get(key);
                boolean same=old instanceof Number&&value instanceof Number
                    ? Math.abs(((Number)old).doubleValue()-((Number)value).doubleValue())<.00001
                    : value.equals(old);
                if(!same)patch.put(key,value);
            }
            preferences.put("_vr_patch",patch);
        }
        preferences.put("vr",current);
    }
    static JSONObject upload(JSONObject preferences) throws JSONException {
        JSONObject result=new JSONObject();
        for(String key:new String[]{"subtitle_delay","subtitle_size","subtitle_position","beauty"})
            if(preferences.has(key))result.put(key,preferences.get(key));
        JSONObject vr=preferences.optJSONObject(preferences.has("_vr_inherited")?"_vr_patch":"vr");
        if(vr!=null&&vr.length()>0)result.put("vr",vr);
        return result;
    }
}
