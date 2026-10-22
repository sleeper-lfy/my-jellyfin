package net.lumen.media;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.net.URI;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

final class Connection {
    final String base, token;
    Connection(String address, String key) throws Exception {
        URI uri = new URI(address.trim());
        if (!("http".equals(uri.getScheme()) || "https".equals(uri.getScheme())) || uri.getHost()==null || uri.getUserInfo()!=null
                || uri.getQuery()!=null || uri.getFragment()!=null || !(uri.getPath().isEmpty() || uri.getPath().equals("/")))
            throw new Exception("请输入完整电脑地址，例如 http://192.168.1.10:8097");
        if (key.trim().length()<20) throw new Exception("请复制电脑端的完整访问密钥");
        base=address.trim().replaceAll("/+$", ""); token=key.trim();
    }
    private static SecretKey encryptionKey() throws Exception {
        KeyStore store=KeyStore.getInstance("AndroidKeyStore"); store.load(null);
        if(!store.containsAlias("lumen_connection")) {
            KeyGenerator generator=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder("lumen_connection",KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
            generator.generateKey();
        }
        return ((KeyStore.SecretKeyEntry)store.getEntry("lumen_connection",null)).getSecretKey();
    }
    void save(Context context) throws Exception {
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,encryptionKey());
        byte[] encrypted=cipher.doFinal(token.getBytes(java.nio.charset.StandardCharsets.UTF_8));
        context.getSharedPreferences("connection",0).edit().putString("base",base)
            .putString("key",Base64.encodeToString(encrypted,Base64.NO_WRAP)).putString("iv",Base64.encodeToString(cipher.getIV(),Base64.NO_WRAP)).apply();
    }
    static Connection load(Context context) {
        try {
            SharedPreferences prefs=context.getSharedPreferences("connection",0);
            String base=prefs.getString("base","");if(base.isEmpty())return null;
            Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE,encryptionKey(),new GCMParameterSpec(128,Base64.decode(prefs.getString("iv",""),Base64.NO_WRAP)));
            return new Connection(base,new String(cipher.doFinal(Base64.decode(prefs.getString("key",""),Base64.NO_WRAP)),java.nio.charset.StandardCharsets.UTF_8));
        } catch(Exception ignored) { return null; }
    }
}
