//!HOOK MAIN
//!BIND HOOKED
//!DESC Lumen gentle bounded sharpen
vec4 hook() {
    vec4 center = HOOKED_tex(HOOKED_pos);
    vec3 a = HOOKED_texOff(vec2(1, 0)).rgb;
    vec3 b = HOOKED_texOff(vec2(-1, 0)).rgb;
    vec3 c = HOOKED_texOff(vec2(0, 1)).rgb;
    vec3 d = HOOKED_texOff(vec2(0, -1)).rgb;
    vec3 low = min(center.rgb, min(min(a,b),min(c,d)));
    vec3 high = max(center.rgb, max(max(a,b),max(c,d)));
    return vec4(clamp(center.rgb + 0.2 * (center.rgb - (a+b+c+d)*0.25), low, high), center.a);
}
