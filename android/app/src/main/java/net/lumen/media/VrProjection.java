package net.lumen.media;

/** VR180 mappings. UV coordinates address one eye before SBS packing. */
public final class VrProjection {
    public static final float DEFAULT_FOV = 90f;
    private VrProjection() {}
    public static boolean autoEnable(String kind) { return "vr".equals(kind); }
    public static float clampPitch(float value) { return Math.max(-85f, Math.min(85f, value)); }
    public static float wrap(float degrees) { return (degrees % 360 + 540) % 360 - 180; }
    public static double[] uv(double x, double y, double z, boolean fisheye, int eye, boolean swap) {
        double length = Math.sqrt(x*x + y*y + z*z);
        if (length == 0 || z < 0) return null;
        x /= length; y /= length; z /= length;
        double u, v;
        if (fisheye) {
            double radius = Math.acos(Math.min(1, z)) / Math.PI;
            double xy = Math.hypot(x, y);
            u = .5 + (xy > 0 ? radius*x/xy : 0);
            v = .5 - (xy > 0 ? radius*y/xy : 0);
        } else {
            u = .5 + Math.atan2(x, z)/Math.PI;
            v = .5 - Math.asin(Math.max(-1, Math.min(1, y)))/Math.PI;
        }
        return new double[]{(u + (swap ? 1-eye : eye))*.5, v};
    }
    public static final String FRAGMENT =
        "#extension GL_OES_EGL_image_external : require\n" +
        "precision highp float; varying vec2 uv; uniform samplerExternalOES video;" +
        "uniform mat4 texMatrix; uniform vec2 angles; uniform float aspect; uniform float tanHalfFov;" +
        "uniform float eye; uniform int fish; uniform vec2 texel; uniform bool flatVideo; uniform float videoAspect;" +
        "uniform vec2 pixelStep; uniform vec4 sampleBounds; uniform vec2 beautyAmount;" +
        "vec4 samplePixel(vec2 t){return texture2D(video,(texMatrix*vec4(clamp(t,sampleBounds.xy,sampleBounds.zw),0,1)).xy);}" +
        "BEAUTY_CORE\n" +
        "void main(){" +
        "if(flatVideo){vec2 p=uv*2.0-1.0;if(aspect>videoAspect)p.x*=aspect/videoAspect;else p.y*=videoAspect/aspect;" +
        "if(abs(p.x)>1.0||abs(p.y)>1.0){gl_FragColor=vec4(0,0,0,1);return;}" +
        "gl_FragColor=vec4(beauty(p*.5+.5,beautyAmount.x,beautyAmount.y),1);return;}" +
        "vec2 p=uv*2.0-1.0; vec3 d=normalize(vec3(p.x*aspect*tanHalfFov,p.y*tanHalfFov,1.0));" +
        "float cp=cos(angles.y),sp=sin(angles.y),cy=cos(angles.x),sy=sin(angles.x);" +
        "d=vec3(d.x,cp*d.y+sp*d.z,-sp*d.y+cp*d.z);" +
        "d=vec3(cy*d.x+sy*d.z,d.y,-sy*d.x+cy*d.z);" +
        "if(d.z<0.0){gl_FragColor=vec4(0,0,0,1);return;}" +
        "vec2 t; if(fish==1){float r=acos(clamp(d.z,0.0,1.0))/3.14159265;" +
        "float l=length(d.xy); t=vec2(.5)+vec2(d.x,-d.y)*(l>0.00001?r/l:0.0);}" +
        "else{t=vec2(.5+atan(d.x,d.z)/3.14159265,.5-asin(clamp(d.y,-1.0,1.0))/3.14159265);}" +
        "t=clamp(t,texel,vec2(1.0)-texel);t.x=(t.x+eye)*.5;" +
        // Android SurfaceTexture transform accounts for decoder crop and Y orientation.
        "t.y=1.0-t.y; gl_FragColor=vec4(beauty(t,beautyAmount.x,beautyAmount.y),1);}";
}
