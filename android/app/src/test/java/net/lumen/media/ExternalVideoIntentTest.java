package net.lumen.media;

import android.app.Application;
import android.app.Dialog;
import android.content.ClipData;
import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Intent;
import android.content.ContentResolver;
import android.content.IntentFilter;
import android.content.pm.ActivityInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.ProviderInfo;
import android.content.pm.ResolveInfo;
import android.content.res.AssetFileDescriptor;
import android.content.res.XmlResourceParser;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.CancellationSignal;
import android.os.ParcelFileDescriptor;
import android.os.PatternMatcher;
import android.provider.OpenableColumns;
import androidx.appcompat.app.AlertDialog;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.Implements;
import org.robolectric.annotation.Implementation;
import org.robolectric.shadows.ShadowContentResolver;
import org.robolectric.shadows.ShadowDialog;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.xmlpull.v1.XmlPullParser;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

/** Manifest resolution and real provider-backed descriptors; no JNI decoder is started. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk=33)
public class ExternalVideoIntentTest {
    private static final Uri CONTENT=Uri.parse("content://external.video.test/items/42");
    private Application app;
    private VideoProvider provider;

    public static final class VideoProvider extends ContentProvider {
        File file;boolean readable=true,empty,hasName=true;volatile boolean blockQuery,blockOpen;
        final AtomicInteger queries=new AtomicInteger(),types=new AtomicInteger(),opens=new AtomicInteger();
        final List<AssetFileDescriptor> descriptors=new CopyOnWriteArrayList<>();
        final CountDownLatch opening=new CountDownLatch(1),continueOpen=new CountDownLatch(1),continueQuery=new CountDownLatch(1);
        volatile String mode;volatile CancellationSignal openedSignal;
        @Override public boolean onCreate(){return true;}
        @Override public String getType(Uri uri){types.incrementAndGet();return "video/x-matroska";}
        @Override public Cursor query(Uri uri,String[] projection,String selection,String[] args,String order){queries.incrementAndGet();if(blockQuery)try{continueQuery.await(3,TimeUnit.SECONDS);}catch(InterruptedException error){Thread.currentThread().interrupt();}MatrixCursor result=new MatrixCursor(new String[]{OpenableColumns.DISPLAY_NAME});if(hasName)result.addRow(new Object[]{"海岸纪行.mkv"});return result;}
        @Override public AssetFileDescriptor openAssetFile(Uri uri,String value,CancellationSignal signal)throws FileNotFoundException{
            opens.incrementAndGet();mode=value;openedSignal=signal;if(!readable)throw new SecurityException("secret provider address and access token must not reach the UI");
            if(blockOpen){opening.countDown();if(signal!=null)signal.setOnCancelListener(continueOpen::countDown);try{continueOpen.await(3,TimeUnit.SECONDS);}catch(InterruptedException error){Thread.currentThread().interrupt();}if(signal!=null)signal.throwIfCanceled();}
            if(!"r".equals(value))throw new SecurityException("Only read grants are allowed");
            ParcelFileDescriptor descriptor=ParcelFileDescriptor.open(file,ParcelFileDescriptor.MODE_READ_ONLY);AssetFileDescriptor asset=new AssetFileDescriptor(descriptor,6,empty?0:5);descriptors.add(asset);return asset;
        }
        @Override public AssetFileDescriptor openAssetFile(Uri uri,String value)throws FileNotFoundException{return openAssetFile(uri,value,null);}
        @Override public Uri insert(Uri uri,ContentValues values){throw new UnsupportedOperationException();}
        @Override public int delete(Uri uri,String selection,String[] args){throw new UnsupportedOperationException();}
        @Override public int update(Uri uri,ContentValues values,String selection,String[] args){throw new UnsupportedOperationException();}
    }
    /** Robolectric 4.14's provider-client shadow drops the third argument; keep Android's contract. */
    @Implements(ContentResolver.class)
    public static class CancellationAwareResolver extends ShadowContentResolver {
        @Implementation protected AssetFileDescriptor openAssetFileDescriptor(Uri uri,String mode,CancellationSignal signal)throws FileNotFoundException{
            if(signal!=null)signal.throwIfCanceled();ContentProvider provider=getProvider(uri);if(provider==null)throw new FileNotFoundException("Missing test provider");return provider.openAssetFile(uri,mode,signal);
        }
    }
    @Before public void fixture()throws Exception{
        app=RuntimeEnvironment.getApplication();provider=new VideoProvider();provider.file=new File(app.getCacheDir(),"external-video-provider.bin");Files.write(provider.file.toPath(),"HEADERVIDEOFOOTER".getBytes(StandardCharsets.UTF_8));ProviderInfo info=new ProviderInfo();info.authority="external.video.test";info.exported=true;info.grantUriPermissions=true;provider.attachInfo(app,info);ShadowContentResolver.registerProviderInternal(info.authority,provider);
    }
    private Intent view(String address,String mime){Intent intent=new Intent(Intent.ACTION_VIEW).addCategory(Intent.CATEGORY_DEFAULT);Uri uri=Uri.parse(address);return mime==null?intent.setData(uri):intent.setDataAndType(uri,mime);}
    private boolean offered(Intent intent){List<ResolveInfo> matches=app.getPackageManager().queryIntentActivities(intent,PackageManager.MATCH_DEFAULT_ONLY);return matches.stream().anyMatch(match->VideoOpenActivity.class.getName().equals(match.activityInfo.name)&&match.activityInfo.exported);}

    @Test public void genericMimeResolvesTheProviderVideoTypeWithoutAVisibleFilename()throws Exception{
        provider.hasName=false;
        try(ExternalVideoSource source=ExternalVideoSource.from(app,view(CONTENT.toString(),"application/octet-stream"))){
            assertEquals("video/x-matroska",source.mimeType());assertEquals(1,provider.types.get());
            try(ExternalVideoSource.AssetLease lease=source.openAsset()){assertEquals(6,lease.asset().getStartOffset());assertEquals(5,lease.asset().getLength());}
        }
    }

    @Test @Config(sdk={26,35}) public void actualPackageManagerOffersLumenForTypedVideosAndUntypedVideoUrls()throws Exception{
        for(String scheme:new String[]{"content://external.video.test/items/42","file:///storage/emulated/0/Movies/sample.mkv","https://example.test/media/42","http://example.test/video"}){
            for(String mime:new String[]{"video/mp4","video/x-matroska","video/hevc","video/h265","application/x-matroska"})assertTrue("System chooser is missing "+scheme+" as "+mime,offered(view(scheme,mime)));
        }
        for(String address:new String[]{"https://example.test/clip.mp4","http://example.test/clip.2160p.mkv?access=sample","https://example.test/path/clip.hevc","https://example.test/CLIP.MP4"}){
            Intent intent=view(address,null).addCategory(Intent.CATEGORY_BROWSABLE);assertTrue("Untyped video link must match its real manifest path filter: "+address,offered(intent));ResolveInfo resolved=app.getPackageManager().resolveActivity(intent,PackageManager.MATCH_DEFAULT_ONLY);assertNotNull(resolved);assertEquals(VideoOpenActivity.class.getName(),resolved.activityInfo.name);
        }
        assertTrue(offered(view(CONTENT.toString(),"application/octet-stream")));assertTrue(offered(view("https://example.test/clip.mkv","application/octet-stream")));
        ActivityInfo player=app.getPackageManager().getActivityInfo(new android.content.ComponentName(app,PlayerActivity.class),0);assertFalse("Private library player must not be externally exported",player.exported);
    }

    @Test @Config(sdk={26,35}) public void manifestDoesNotClaimOrdinaryWebPagesOrAddStoragePermissions()throws Exception{
        for(Intent intent:new Intent[]{view("https://example.test/",null),view("http://example.test/watch?id=42",null),view("https://example.test/page.html","text/html"),view("https://example.test/image.jpg","image/jpeg"),view("https://example.test/readme.txt",null)})assertFalse("Lumen must not be offered for a normal page",offered(intent));
        PackageInfo info=app.getPackageManager().getPackageInfo(app.getPackageName(),PackageManager.GET_PERMISSIONS);List<String> permissions=info.requestedPermissions==null?java.util.Collections.emptyList():Arrays.asList(info.requestedPermissions);for(String permission:new String[]{"android.permission.READ_EXTERNAL_STORAGE","android.permission.WRITE_EXTERNAL_STORAGE","android.permission.MANAGE_EXTERNAL_STORAGE","android.permission.READ_MEDIA_VIDEO"})assertFalse(permissions.contains(permission));
    }

    private void restoreModernSuffixesOmittedByLegacyParser()throws Exception{
        // Robolectric 4.14 uses deprecated PackageParser, which reads path kinds 0..3 only.
        // Supplement ONLY suffix attributes from the actual compiled manifest, retaining its
        // original schemes, MIME types, categories and all legacy path constraints.
        List<IntentFilter> filters=shadowOf(app.getPackageManager()).getIntentFiltersForActivity(new android.content.ComponentName(app,VideoOpenActivity.class));
        String ns="http://schemas.android.com/apk/res/android";boolean videoActivity=false;int filterIndex=0,suffixes=0;IntentFilter filter=null;
        try(XmlResourceParser xml=app.getAssets().openXmlResourceParser("AndroidManifest.xml")){
            for(int event=xml.next();event!=XmlPullParser.END_DOCUMENT;event=xml.next()){
                if(event==XmlPullParser.START_TAG&&"activity".equals(xml.getName())){String name=xml.getAttributeValue(ns,"name");videoActivity=".VideoOpenActivity".equals(name)||VideoOpenActivity.class.getName().equals(name);}
                else if(event==XmlPullParser.START_TAG&&videoActivity&&"intent-filter".equals(xml.getName()))filter=filters.get(filterIndex++);
                else if(event==XmlPullParser.START_TAG&&videoActivity&&filter!=null&&"data".equals(xml.getName())){String suffix=xml.getAttributeValue(ns,"pathSuffix");if(suffix!=null){suffixes++;boolean found=false;for(int index=0;index<filter.countDataPaths();index++)if(filter.getDataPath(index).getType()==PatternMatcher.PATTERN_SUFFIX&&suffix.equals(filter.getDataPath(index).getPath()))found=true;if(!found)filter.addDataPath(suffix,PatternMatcher.PATTERN_SUFFIX);assertTrue(new PatternMatcher(suffix,PatternMatcher.PATTERN_SUFFIX).match("/Title.2025.2160p.HEVC.10bit"+suffix));}}
                else if(event==XmlPullParser.END_TAG&&"intent-filter".equals(xml.getName()))filter=null;
                else if(event==XmlPullParser.END_TAG&&"activity".equals(xml.getName()))videoActivity=false;
            }
        }
        assertTrue("The real compiled manifest must retain its modern video suffixes",suffixes>=18);
    }
    @Test @Config(sdk=35) public void modernPackageManagerMatchesMultiDotVideoSuffixesWithOrWithoutOctetMime()throws Exception{
        restoreModernSuffixesOmittedByLegacyParser();
        for(String address:new String[]{"https://example.test/movies/Title.2025.2160p.HEVC.10bit.mkv?signature=sample","http://example.test/series/Coast.Journal.2025.S01E02.1080p.mp4","https://example.test/VR.Sample.2025.180.3D.hevc"}){
            assertTrue("Modern chooser must match a complete video suffix",offered(view(address,null)));assertTrue("Octet-stream file links must retain the video path constraint",offered(view(address,"application/octet-stream")));
        }
        assertFalse(offered(view("https://example.test/Title.2025.movie.html",null)));assertFalse(offered(view("https://example.test/Title.2025.movie.html","application/octet-stream")));
    }

    @Test public void routerForwardsOnlyTheValidatedUriAndReadGrantWithoutConsultingAProvider()throws Exception{
        provider.blockQuery=true;Intent incoming=view(CONTENT.toString(),null).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION|Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION|Intent.FLAG_GRANT_PREFIX_URI_PERMISSION).putExtra("work_id",999).putExtra("queue",true).putExtra("token","private-library-secret").putExtra("server","https://untrusted.test");ClipData clip=ClipData.newRawUri("Untrusted title",CONTENT);clip.addItem(new ClipData.Item(Uri.parse("content://untrusted.test/another-file")));incoming.setClipData(clip);
        try(ActivityController<VideoOpenActivity> lifecycle=Robolectric.buildActivity(VideoOpenActivity.class,incoming).create()){
            Intent forwarded=shadowOf(lifecycle.get()).getNextStartedActivity();assertNotNull(forwarded);assertEquals(PlayerActivity.class.getName(),forwarded.getComponent().getClassName());assertEquals(Intent.ACTION_VIEW,forwarded.getAction());assertEquals(CONTENT,forwarded.getData());assertNull("Provider type stays unresolved for the worker",forwarded.getType());assertEquals(Intent.FLAG_GRANT_READ_URI_PERMISSION,forwarded.getFlags());assertNull("Library and arbitrary caller options must never cross the exported router",forwarded.getExtras());assertEquals(1,forwarded.getClipData().getItemCount());assertEquals(CONTENT,forwarded.getClipData().getItemAt(0).getUri());assertTrue(lifecycle.get().isFinishing());assertEquals(0,provider.queries.get());assertEquals(0,provider.types.get());assertEquals(0,provider.opens.get());
        }finally{provider.continueQuery.countDown();}
    }

    @Test public void unsupportedUrisAndExecutableOptionsFailWithoutLeakingTheirAddress()throws Exception{
        for(String address:new String[]{"javascript:alert(1)","intent://play/#Intent;scheme=http;end","rtsp://example.test/video","file://untrusted.test/clip.mp4","http://user:password@example.test/clip.mp4","https://example.test/clip.mp4%0a:sout=evil","http:///clip.mp4"}){
            Intent intent=view(address,"video/mp4");assertFalse(ExternalVideoSource.supports(intent));IOException error=assertThrows(IOException.class,()->ExternalVideoSource.from(app,intent));assertFalse(error.getMessage().contains(address));
        }
        Intent options=view("https://example.test/clip.mp4","video/mp4").putExtra("item_options",new String[]{":sout=arbitrary"});assertThrows(IOException.class,()->ExternalVideoSource.from(app,options));assertThrows(IOException.class,()->ExternalVideoSource.from(app,new Intent(Intent.ACTION_SEND).setDataAndType(CONTENT,"video/mp4")));
        try(ActivityController<VideoOpenActivity> lifecycle=Robolectric.buildActivity(VideoOpenActivity.class,options).create()){
            assertNull(shadowOf(lifecycle.get()).getNextStartedActivity());Dialog dialog=ShadowDialog.getLatestDialog();assertTrue(dialog instanceof AlertDialog);assertTrue(dialog.isShowing());((AlertDialog)dialog).getButton(AlertDialog.BUTTON_POSITIVE).performClick();shadowOf(android.os.Looper.getMainLooper()).idle();assertTrue(lifecycle.get().isFinishing());
        }
    }

    @Test public void providerDescriptorsPreserveOffsetLengthAndCloseOnLeaseOrSourceClose()throws Exception{
        Intent intent=view(CONTENT.toString(),"video/x-matroska").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try(ExternalVideoSource source=ExternalVideoSource.from(app,intent)){
            assertEquals("海岸纪行.mkv",source.title());assertFalse(source.isNetwork());ExternalVideoSource.AssetLease first=source.openAsset(),second=source.openAsset();AssetFileDescriptor a=first.asset(),b=second.asset();assertNotSame(a,b);assertEquals("r",provider.mode);assertEquals(6,a.getStartOffset());assertEquals(5,a.getLength());assertEquals(6,b.getStartOffset());assertEquals(5,b.getLength());
            FileInputStream bytes=new FileInputStream(a.getFileDescriptor());bytes.getChannel().position(a.getStartOffset());byte[] video=new byte[(int)a.getLength()];assertEquals(5,bytes.read(video));assertArrayEquals("VIDEO".getBytes(StandardCharsets.UTF_8),video);first.close();first.close();assertThrows(IOException.class,first::asset);assertThrows(IllegalStateException.class,()->a.getParcelFileDescriptor().getFd());assertTrue(b.getParcelFileDescriptor().getFd()>=0);source.close();assertThrows(IOException.class,second::asset);assertThrows(IllegalStateException.class,()->b.getParcelFileDescriptor().getFd());assertThrows(IOException.class,source::openAsset);
        }
    }

    @Test public void missingReadPermissionAndEmptyProviderCloseDescriptorsAndReturnClearErrors()throws Exception{
        try(ExternalVideoSource source=ExternalVideoSource.from(app,view(CONTENT.toString(),"video/mp4"))){
            provider.readable=false;IOException denied=assertThrows(IOException.class,source::openAsset);assertTrue(denied.getMessage().contains("权限"));assertFalse(denied.getMessage().contains("secret"));assertEquals("r",provider.mode);assertTrue(provider.descriptors.isEmpty());provider.readable=true;provider.empty=true;IOException empty=assertThrows(IOException.class,source::openAsset);assertTrue(empty.getMessage().contains("读取"));assertEquals(1,provider.descriptors.size());assertThrows(IllegalStateException.class,()->provider.descriptors.get(0).getParcelFileDescriptor().getFd());
        }
    }

    @Test @Config(shadows=CancellationAwareResolver.class) public void sourceCloseCancelsAProviderOpenInFlightWithoutWaitingForTheSourceLock()throws Exception{
        ExternalVideoSource source=ExternalVideoSource.from(app,view(CONTENT.toString(),"video/mp4"));provider.blockOpen=true;ExecutorService worker=Executors.newSingleThreadExecutor();try{
            Future<IOException> result=worker.submit(()->{try{source.openAsset();return null;}catch(IOException error){return error;}});assertTrue(provider.opening.await(2,TimeUnit.SECONDS));assertNotNull(provider.openedSignal);source.close();assertTrue(provider.openedSignal.isCanceled());assertNotNull("Cancellation must interrupt the real provider request",result.get(2,TimeUnit.SECONDS));assertTrue(provider.descriptors.isEmpty());assertThrows(IOException.class,source::openAsset);
        }finally{source.close();provider.continueOpen.countDown();worker.shutdownNow();}
    }

    @Test public void fileAndNetworkSourcesDoNotUseLibraryApiOrAuthorizationExtras()throws Exception{
        File file=new File(app.getCacheDir(),"external-sample.mp4");Files.write(file.toPath(),"video-sample".getBytes(StandardCharsets.UTF_8));try(ExternalVideoSource source=ExternalVideoSource.from(app,new Intent(Intent.ACTION_VIEW).setData(Uri.fromFile(file)))){assertEquals("external-sample.mp4",source.title());try(ExternalVideoSource.AssetLease lease=source.openAsset()){assertEquals(file.length(),lease.asset().getLength());}}
        Intent incoming=view("https://example.test/clip.mp4?signature=opaque-value","video/mp4").putExtra("token","library-bearer").putExtra("http_headers",new String[]{"Authorization: Bearer attacker"});try(ExternalVideoSource source=ExternalVideoSource.from(app,incoming)){assertTrue(source.isNetwork());assertEquals("clip.mp4",source.title());assertEquals(incoming.getData(),source.uri());assertThrows(IOException.class,source::openAsset);assertEquals(0,provider.opens.get());}
    }
}
