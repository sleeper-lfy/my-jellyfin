// Lumen lightweight beauty: skin-weighted bilateral smoothing, no face geometry.
// samplePixel and pixelStep are supplied by each playback renderer.
vec3 beauty(vec2 point, float smoothing, float brighten) {
    vec3 center = samplePixel(point).rgb;
    if (smoothing <= 0.0 && brighten <= 0.0) return center;
    float cb = dot(center, vec3(-0.168736, -0.331264, 0.5)) + 0.5;
    float cr = dot(center, vec3(0.5, -0.418688, -0.081312)) + 0.5;
    float skin = smoothstep(0.28, 0.34, cb) * (1.0 - smoothstep(0.48, 0.54, cb))
               * smoothstep(0.52, 0.57, cr) * (1.0 - smoothstep(0.70, 0.77, cr));
    skin *= smoothstep(0.04, 0.15, dot(center, vec3(0.299, 0.587, 0.114)));
    vec3 total = center * 2.0;
    float weights = 2.0;
    if (smoothing > 0.0 && skin > 0.001) {
        for (int y = -1; y <= 1; y++) {
            for (int x = -1; x <= 1; x++) {
                if (x == 0 && y == 0) continue;
                vec3 neighbor = samplePixel(point + vec2(float(x), float(y)) * pixelStep * 2.0).rgb;
                vec3 delta = neighbor - center;
                float weight = exp(-dot(delta, delta) * 70.0) / (1.0 + float(x*x + y*y));
                total += neighbor * weight;
                weights += weight;
            }
        }
    }
    vec3 result = mix(center, total / weights, smoothing * skin * 0.85);
    result += brighten * skin * 0.18 * (vec3(1.0) - result);
    return clamp(result, 0.0, 1.0);
}
