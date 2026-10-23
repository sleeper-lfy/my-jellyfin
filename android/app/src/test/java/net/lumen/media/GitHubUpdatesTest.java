package net.lumen.media;

import android.app.Application;
import android.content.pm.PackageInfo;
import android.content.pm.Signature;
import android.net.Uri;
import android.os.Looper;
import android.provider.OpenableColumns;
import android.widget.TextView;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;
import org.robolectric.android.controller.ActivityController;
import java.io.*;
import java.lang.reflect.Field;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

@RunWith(RobolectricTestRunner.class) @Config(sdk=33)
public class GitHubUpdatesTest {
    private final String hash="a".repeat(64);
    private byte[] bytes(String value){return value.getBytes(StandardCharsets.UTF_8);}
    private byte[] manifest(String version,long code)throws Exception{return bytes(new JSONObject().put("version",version).put("version_code",code).put("bytes",5).put("sha256",hash).toString());}
    private String release(String version){return "{\"tag_name\":\"v"+version+"\",\"assets\":[{\"name\":\"Lumen-android-debug.apk\",\"browser_download_url\":\"https://github.com/sleeper-lfy/my-jellyfin/releases/download/v"+version+"/Lumen-android-debug.apk\",\"size\":5,\"digest\":\"sha256:"+hash+"\"}]}";}
    @Test public void targetFallbackWorksWhenReleaseApiIsUnavailable()throws Exception{
        ArrayList<String> urls=new ArrayList<>();GitHubUpdates.Candidate update=GitHubUpdates.check("0.4.3",6,(url,limit)->{urls.add(url);if(url.equals(GitHubUpdates.RELEASE))throw new IOException("HTTP 403");return manifest("0.4.4",7);});
        assertEquals("0.4.4",update.version);assertEquals(7,update.code);assertEquals(GitHubUpdates.TARGET+"Lumen-android-debug.apk",update.url);assertEquals(2,urls.size());
    }
    @Test public void newestStableReleaseWinsAndInstalledVersionDoesNotDowngrade()throws Exception{
        GitHubUpdates.Candidate update=GitHubUpdates.check("0.4.3",6,(url,limit)->url.equals(GitHubUpdates.RELEASE)?bytes(release("0.4.5")):manifest("0.4.4",7));
        assertEquals("0.4.5",update.version);assertEquals("GitHub Releases",update.source);
        assertNull(GitHubUpdates.check("0.4.3",6,(url,limit)->url.equals(GitHubUpdates.RELEASE)?bytes(release("0.4.2")):manifest("0.4.3",6)));
        assertEquals(1,GitHubUpdates.compare("0.4.10","0.4.9"));
    }
    @Test public void missingChecksumsAndUntrustedUrlsCannotBecomeUpdatePackages()throws Exception{
        for(String url:new String[]{"http://github.com/file.apk","https://github.com.evil.test/file.apk","https://github.com@evil.test/file.apk","https://github.com:444/file.apk","file:///tmp/a.apk"})assertThrows(Exception.class,()->GitHubUpdates.validateUrl(url));
        assertThrows(Exception.class,()->new GitHubUpdates.Candidate("0.4.4",7,GitHubUpdates.TARGET+"a.apk",4,"","","test"));
        assertThrows(Exception.class,()->GitHubUpdates.check("0.4.3",6,(url,limit)->{throw new IOException("Network unavailable");}));
    }
    private GitHubUpdates.Candidate candidate(byte[] data)throws Exception{return new GitHubUpdates.Candidate("0.4.4",7,GitHubUpdates.TARGET+"a.apk",data.length,GitHubUpdates.hex(MessageDigest.getInstance("SHA-256").digest(data)),"","test");}
    @Test public void streamingDownloadChecksBytesHashAndCleansPartialFiles()throws Exception{
        File directory=Files.createTempDirectory("lumen-update-test").toFile();byte[] data=bytes("Verified APK test bytes");GitHubUpdates.Candidate expected=candidate(data);ArrayList<Long> progress=new ArrayList<>();
        File result=GitHubUpdates.save(expected,directory,new ByteArrayInputStream(data),(done,total)->progress.add(done),()->false);assertArrayEquals(data,Files.readAllBytes(result.toPath()));assertEquals(Long.valueOf(data.length),progress.get(progress.size()-1));
        for(byte[] wrong:new byte[][]{bytes("short"),new byte[data.length],new byte[data.length+1]})assertThrows(IOException.class,()->GitHubUpdates.save(expected,directory,new ByteArrayInputStream(wrong),(a,b)->{},()->false));
        assertThrows(InterruptedIOException.class,()->GitHubUpdates.save(expected,directory,new ByteArrayInputStream(data),(a,b)->{},()->true));
        assertArrayEquals(data,Files.readAllBytes(result.toPath()));assertEquals(1,directory.listFiles().length);
    }
    @SuppressWarnings("deprecation") private PackageInfo info(String name,long version,String versionName,int signature){PackageInfo info=new PackageInfo();info.packageName=name;info.setLongVersionCode(version);info.versionName=versionName;info.signatures=new Signature[]{new Signature(new byte[]{(byte)signature})};return info;}
    @Test public void installationRejectsWrongPackageOldVersionAndDifferentCertificate()throws Exception{
        GitHubUpdates.Candidate expected=candidate(bytes("apk"));PackageInfo installed=info("net.lumen.media",6,"0.4.3",1);UpdateActivity.validateArchive(info("net.lumen.media",7,"0.4.4",1),installed,expected);
        assertThrows(Exception.class,()->UpdateActivity.validateArchive(info("evil.package",7,"0.4.4",1),installed,expected));
        assertThrows(Exception.class,()->UpdateActivity.validateArchive(info("net.lumen.media",6,"0.4.4",1),installed,expected));
        assertThrows(Exception.class,()->UpdateActivity.validateArchive(info("net.lumen.media",7,"0.4.4",2),installed,expected));
        assertThrows(Exception.class,()->UpdateActivity.validateArchive(info("net.lumen.media",8,"0.4.5",1),installed,expected));
    }
    @Test public void providerOnlyExposesOneReadOnlyCachedApk()throws Exception{
        UpdatePackageProvider provider=Robolectric.buildContentProvider(UpdatePackageProvider.class).create().get();Application app=RuntimeEnvironment.getApplication();File directory=new File(app.getCacheDir(),"updates");directory.mkdirs();Files.write(new File(directory,"Lumen-update.apk").toPath(),bytes("apk"));
        Uri uri=Uri.parse("content://net.lumen.media.updates/Lumen-update.apk");
        try(android.os.ParcelFileDescriptor descriptor=provider.openFile(uri,"r")){assertNotNull(descriptor);}
        try(android.database.Cursor cursor=provider.query(uri,new String[]{OpenableColumns.SIZE},null,null,null)){assertTrue(cursor.moveToFirst());assertEquals(3,cursor.getLong(0));}
        assertThrows(FileNotFoundException.class,()->provider.openFile(uri,"w"));assertThrows(FileNotFoundException.class,()->provider.openFile(Uri.parse("content://net.lumen.media.updates/../library.sqlite"),"r"));
    }
    private Object field(Object object,String name)throws Exception{Field field=object.getClass().getDeclaredField(name);field.setAccessible(true);return field.get(object);}
    @Test public void updateScreenChecksWithoutServerAndKeepsMainThreadResponsive()throws Exception{
        android.content.pm.PackageInfo current=RuntimeEnvironment.getApplication().getPackageManager().getPackageInfo("net.lumen.media",0);
        String[] version=current.versionName.split("\\.");
        String nextVersion=version[0]+"."+version[1]+"."+(Integer.parseInt(version[2])+1);long nextCode=current.getLongVersionCode()+1;
        CountDownLatch release=new CountDownLatch(1);
        try(ActivityController<UpdateActivity> lifecycle=Robolectric.buildActivity(UpdateActivity.class)){
            UpdateActivity activity=lifecycle.get();activity.fetcher=(url,limit)->{release.await(3,TimeUnit.SECONDS);if(url.equals(GitHubUpdates.RELEASE))throw new IOException("API unavailable");return manifest(nextVersion,nextCode);};
            lifecycle.create().start().resume().visible();TextView status=(TextView)field(activity,"status");assertTrue(status.getText().toString().contains("正在检查"));release.countDown();
            long deadline=System.currentTimeMillis()+5000;while(!status.getText().toString().contains("发现新版")&&System.currentTimeMillis()<deadline){Thread.sleep(15);shadowOf(Looper.getMainLooper()).idle();}
            assertTrue(status.getText().toString().contains(nextVersion));assertTrue(((android.widget.Button)field(activity,"download")).isEnabled());
        }finally{release.countDown();}
    }
}
