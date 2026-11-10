package net.lumen.media;

import android.content.SharedPreferences;

/** Requested decoder policy, independent of the decoder actually selected by VLC. */
final class PlaybackDecoderPolicy {
    static final int AUTOMATIC=0, MEDIACODEC_JNI=1, SOFTWARE=2;
    private PlaybackDecoderPolicy() {}
    static int load(SharedPreferences preferences) {
        int mode=preferences.getInt("decoder_mode",preferences.getBoolean("software",false)?SOFTWARE:AUTOMATIC);
        return mode>=AUTOMATIC&&mode<=SOFTWARE?mode:AUTOMATIC;
    }
    static void save(SharedPreferences preferences,int mode) {
        preferences.edit().putInt("decoder_mode",mode).putBoolean("software",mode==SOFTWARE).apply();
    }
    static String description(int mode) {
        if(mode==SOFTWARE)return "软件解码";
        return mode==MEDIACODEC_JNI?"MediaCodec JNI 硬件优先，软件兜底":"自动（MediaCodec NDK 硬件优先，软件兜底）";
    }
}
