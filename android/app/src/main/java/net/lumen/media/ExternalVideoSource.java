package net.lumen.media;

import android.content.ContentResolver;
import android.content.Context;
import android.content.Intent;
import android.content.res.AssetFileDescriptor;
import android.database.Cursor;
import android.net.Uri;
import android.os.CancellationSignal;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.File;
import java.io.IOException;
import java.net.URI;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import org.videolan.libvlc.LibVLC;
import org.videolan.libvlc.Media;

/** A single external video, with no library identity, authorization header or VLC options. */
final class ExternalVideoSource implements AutoCloseable {
    private static final Set<String> SCHEMES=new HashSet<>(Arrays.asList("content","file","http","https"));
    private static final Set<String> CONTAINERS=new HashSet<>(Arrays.asList("application/x-matroska","application/mp4"));
    private static final String[] UNSAFE_EXTRAS={"vlc_options","libvlc_options","media_options","item_options","sout","input-slave"};
    private static final String VIDEO_SUFFIX="(?i).+\\.(mp4|m4v|mkv|webm|mov|avi|mpg|mpeg|m2ts|mts|ts|hevc|h265|h264|3gp|3g2|flv|wmv|m3u8)$";
    private final ContentResolver resolver;
    private final Uri uri;
    private final String title,mime;
    private final CancellationSignal cancellation;
    private final Set<AssetLease> assets=new HashSet<>();
    private final Set<OpenedMedia> opened=new HashSet<>();
    private volatile boolean closed;

    private ExternalVideoSource(ContentResolver resolver,Uri uri,String title,String mime,CancellationSignal cancellation){this.resolver=resolver;this.uri=uri;this.title=title;this.mime=mime;this.cancellation=cancellation;}
    static boolean supports(Intent intent){try{validate(intent,null,null);return true;}catch(Exception ignored){return false;}}
    /** URI-only routing: opaque provider IDs are checked on the player's cancellable worker. */
    static Uri routingUri(Intent intent)throws IOException{
        Uri uri=validateUri(intent);String type=normalizedMime(intent.getType());
        boolean providerMustResolve="content".equals(uri.getScheme())&&(type==null||"application/octet-stream".equals(type));
        if(!providerMustResolve)validate(intent,type,null);return uri;
    }
    static ExternalVideoSource from(Context context,Intent intent)throws IOException{return from(context,intent,new CancellationSignal());}
    static ExternalVideoSource from(Context context,Intent intent,CancellationSignal signal)throws IOException{
        if(signal==null)throw new IOException("视频读取已取消。");
        try{
            Uri uri=validateUri(intent);ContentResolver resolver=context.getContentResolver();String name=null,type=intent.getType();
            if("content".equals(uri.getScheme())){
                if(normalizedMime(type)==null||"application/octet-stream".equals(normalizedMime(type)))try{
                    String providerType=resolver.getType(uri);if(normalizedMime(providerType)!=null)type=providerType;
                }catch(SecurityException ignored){}
                try(Cursor cursor=resolver.query(uri,new String[]{OpenableColumns.DISPLAY_NAME},null,null,null,signal)){
                    if(cursor!=null&&cursor.moveToFirst()){int column=cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);if(column>=0)name=cursor.getString(column);}
                }catch(android.os.OperationCanceledException error){throw error;}catch(RuntimeException ignored){}
            }
            validate(intent,type,name);String title=safeTitle(name==null?uri.getLastPathSegment():name);
            return new ExternalVideoSource(resolver,uri,title,normalizedMime(type)==null?"video/*":normalizedMime(type),signal);
        }catch(IOException error){signal.cancel();throw error;}catch(RuntimeException error){signal.cancel();throw new IOException("无法读取视频信息，请从来源应用重新选择视频。",error);}
    }
    private static Uri validateUri(Intent intent)throws IOException{
        if(intent==null||!Intent.ACTION_VIEW.equals(intent.getAction())||intent.getData()==null)throw new IOException("请选择一个视频文件或视频链接。");
        try{
            for(String extra:UNSAFE_EXTRAS)if(intent.hasExtra(extra))throw new IOException("此打开请求包含不支持的播放器选项。");
            Uri uri=intent.getData().normalizeScheme();String raw=uri.toString();
            if(raw.length()>16384||raw.matches("(?s).*[\\x00-\\x20\\x7f].*")||raw.matches("(?is).*%(00|0a|0d).*"))throw new IOException("视频地址格式不正确。");
            URI parsed=new URI(raw);String scheme=uri.getScheme();if(!SCHEMES.contains(scheme)||uri.isOpaque()||parsed.getRawUserInfo()!=null)throw new IOException("仅支持本机视频和 HTTP / HTTPS 视频链接。");
            if("http".equals(scheme)||"https".equals(scheme)){
                if(parsed.getHost()==null||parsed.getHost().isEmpty()||parsed.getPort()==0||parsed.getPort()>65535)throw new IOException("视频链接缺少有效的服务器地址。");
            }else if("content".equals(scheme)){
                if(uri.getAuthority()==null||uri.getAuthority().isEmpty())throw new IOException("内容提供方地址不正确。");
            }else if(uri.getPath()==null||!uri.getPath().startsWith("/")||uri.getAuthority()!=null&&!uri.getAuthority().isEmpty())throw new IOException("本机视频地址不正确。");
            return uri;
        }catch(IOException error){throw error;}catch(Exception error){throw new IOException("视频地址格式不正确。",error);}
    }
    private static void validate(Intent intent,String resolvedType,String displayName)throws IOException{
        Uri uri=validateUri(intent);String type=normalizedMime(resolvedType==null?intent.getType():resolvedType);
        boolean filename=(displayName!=null&&displayName.matches(VIDEO_SUFFIX))||(uri.getLastPathSegment()!=null&&uri.getLastPathSegment().matches(VIDEO_SUFFIX));
        boolean video=type!=null&&(type.matches("video/[a-z0-9.+*-]+")||CONTAINERS.contains(type));
        if(!video&&!(filename&&(type==null||"application/octet-stream".equals(type))))throw new IOException("此内容不是受支持的视频，请选择 MP4、MKV 等视频文件。");
    }
    private static String normalizedMime(String type){if(type==null||type.trim().isEmpty())return null;return type.split(";",2)[0].trim().toLowerCase(Locale.ROOT);}
    private static String safeTitle(String value){if(value==null||value.trim().isEmpty())return "外部视频";String clean=value.replaceAll("[\\p{Cntrl}]"," ").trim();return clean.isEmpty()?"外部视频":clean.length()>160?clean.substring(0,160):clean;}
    String title(){return title;}
    Uri uri(){return uri;}
    String mimeType(){return mime;}
    boolean isNetwork(){return "http".equals(uri.getScheme())||"https".equals(uri.getScheme());}

    /** Each decoder instance receives its own descriptor; the provider's offset/length are kept. */
    AssetLease openAsset()throws IOException{
        if(isNetwork())throw new IOException("网络视频不使用本机文件句柄。");
        if(closed||cancellation.isCanceled())throw new IOException("视频读取已取消。");AssetFileDescriptor descriptor=null;
        try{
            if("content".equals(uri.getScheme()))descriptor=resolver.openAssetFileDescriptor(uri,"r",cancellation);
            else{File file=new File(uri.getPath());if(!file.isFile()||!file.canRead())throw new IOException("本机视频不存在或没有读取权限。");descriptor=new AssetFileDescriptor(ParcelFileDescriptor.open(file,ParcelFileDescriptor.MODE_READ_ONLY),0,AssetFileDescriptor.UNKNOWN_LENGTH);}
            if(descriptor==null||descriptor.getStartOffset()<0||descriptor.getLength()==0)throw new IOException("来源应用未提供可读取的视频内容。");
            AssetLease lease=new AssetLease(descriptor);synchronized(this){if(closed||cancellation.isCanceled())throw new IOException("视频读取已取消。");assets.add(lease);}return lease;
        }catch(SecurityException error){closeDescriptor(descriptor);throw new IOException("没有读取这个视频的权限，请从来源应用重新打开并允许读取。",error);}catch(IOException error){closeDescriptor(descriptor);throw error;}catch(RuntimeException error){closeDescriptor(descriptor);throw new IOException("无法读取视频，请检查来源应用是否仍可访问该文件。",error);}
    }
    OpenedMedia openMedia(LibVLC vlc)throws IOException{
        if(closed||cancellation.isCanceled())throw new IOException("视频读取已取消。");AssetLease lease=null;Media media=null;
        try{
            if(isNetwork())media=new Media(vlc,uri);else{lease=openAsset();media=new Media(vlc,lease.asset());}
            OpenedMedia handle=new OpenedMedia(media,lease);synchronized(this){if(closed||cancellation.isCanceled())throw new IOException("视频读取已取消。");opened.add(handle);}return handle;
        }catch(IOException|RuntimeException|LinkageError error){try{if(media!=null)media.release();}finally{if(lease!=null)lease.close();}if(error instanceof IOException)throw (IOException)error;throw new IOException("无法打开此视频。请重新选择文件或视频链接。",error);}
    }
    private static void closeDescriptor(AssetFileDescriptor descriptor){if(descriptor!=null)try{descriptor.close();}catch(IOException ignored){}}
    final class AssetLease implements AutoCloseable {
        private AssetFileDescriptor descriptor;
        private AssetLease(AssetFileDescriptor descriptor){this.descriptor=descriptor;}
        synchronized AssetFileDescriptor asset()throws IOException{if(descriptor==null)throw new IOException("视频文件句柄已关闭。");return descriptor;}
        @Override public void close(){AssetFileDescriptor value;synchronized(this){value=descriptor;descriptor=null;}closeDescriptor(value);synchronized(ExternalVideoSource.this){assets.remove(this);}}
    }
    final class OpenedMedia implements AutoCloseable {
        final Media media;private AssetLease lease;private boolean released;
        private OpenedMedia(Media media,AssetLease lease){this.media=media;this.lease=lease;}
        /** Call only after MediaPlayer.stop/detach/release; this owns the initial Media reference. */
        @Override public void close(){synchronized(this){if(released)return;released=true;}try{media.release();}catch(RuntimeException|LinkageError ignored){}finally{if(lease!=null){lease.close();lease=null;}synchronized(ExternalVideoSource.this){opened.remove(this);}}}
    }
    @Override public void close(){
        cancellation.cancel();ArrayList<OpenedMedia> media;ArrayList<AssetLease> descriptors;synchronized(this){if(closed)return;closed=true;media=new ArrayList<>(opened);descriptors=new ArrayList<>(assets);}for(OpenedMedia handle:media)handle.close();for(AssetLease lease:descriptors)lease.close();
    }
}
