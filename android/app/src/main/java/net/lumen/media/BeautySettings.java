package net.lumen.media;

import android.content.Context;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

/** Local GPU filtering only; no face recognition or source-file processing. */
public final class BeautySettings {
    public final boolean enabled;
    public final float smoothing,brighten;
    public BeautySettings(JSONObject value){
        if(value==null)value=new JSONObject();
        enabled=value.optBoolean("enabled",false);
        smoothing=amount(value,"smoothing",35);brighten=amount(value,"brighten",15);
    }
    private static float amount(JSONObject value,String key,int fallback){
        double number=value.optDouble(key,fallback);
        return (float)(Double.isFinite(number)?Math.max(0,Math.min(100,number)):fallback)/100f;
    }
    public static String shader(Context context){
        try(java.io.InputStream input=context.getAssets().open("shaders/beauty-core.glsl")){
            java.io.ByteArrayOutputStream output=new java.io.ByteArrayOutputStream();
            byte[] buffer=new byte[4096];int count;while((count=input.read(buffer))!=-1)output.write(buffer,0,count);
            return output.toString(StandardCharsets.UTF_8.name());
        }catch(IOException error){throw new IllegalStateException("美颜着色器未安装",error);}
    }
}
