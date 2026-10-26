package net.lumen.media;

import java.util.ArrayList;
import org.junit.Test;
import static org.junit.Assert.*;

public class SubtitleAppearanceTest {
    @Test public void textHasNoBackgroundAndRemainsReadableWithDarkEdges() {
        ArrayList<String> options=SubtitleAppearance.options(28,80);
        assertTrue(options.contains("--freetype-background-opacity=0"));
        assertTrue(options.contains("--freetype-color=16777215"));
        assertTrue(options.contains("--freetype-opacity=255"));
        assertTrue(options.contains("--freetype-outline-color=0"));
        assertTrue(options.contains("--freetype-outline-opacity=255"));
        assertTrue(options.contains("--freetype-outline-thickness=2"));
        assertTrue(options.contains("--no-subsdec-formatted"));
        assertFalse(options.stream().anyMatch(value->value.startsWith("--codec=")||value.startsWith("--ssa-style")));
    }
    @Test public void rememberedSizeAndPositionDoNotRestoreAnOpaqueRectangle() {
        ArrayList<String> first=SubtitleAppearance.options(22,30);
        ArrayList<String> restored=SubtitleAppearance.options(56,150);
        assertTrue(first.contains("--freetype-fontsize=22"));
        assertTrue(restored.contains("--freetype-fontsize=56"));
        assertTrue(restored.contains("--sub-margin=150"));
        assertTrue(first.contains("--freetype-background-opacity=0"));
        assertTrue(restored.contains("--freetype-background-opacity=0"));
        assertTrue(SubtitleAppearance.options(22,-20).contains("--sub-margin=0"));
    }
}
