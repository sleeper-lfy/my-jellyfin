package net.lumen.media;

import java.util.ArrayList;

/** Text subtitles share a transparent surface in both normal and VR playback. */
public final class SubtitleAppearance {
    private SubtitleAppearance() {}
    public static ArrayList<String> options(int fontSizePx,int bottomMarginPx) {
        ArrayList<String> options=new ArrayList<>();
        options.add("--freetype-fontsize="+fontSizePx);
        options.add("--sub-margin="+Math.max(0,bottomMarginPx));
        options.add("--freetype-color=16777215");
        options.add("--freetype-opacity=255");
        options.add("--freetype-background-opacity=0");
        options.add("--freetype-outline-color=0");
        options.add("--freetype-outline-opacity=255");
        options.add("--freetype-outline-thickness=2");
        options.add("--freetype-shadow-color=0");
        options.add("--freetype-shadow-opacity=128");
        options.add("--freetype-shadow-distance=0.03");
        // SRT/HTML style tags must not bring an opaque background back. Native
        // libass and bitmap subtitle tracks remain available and unmodified.
        options.add("--no-subsdec-formatted");
        return options;
    }
}
