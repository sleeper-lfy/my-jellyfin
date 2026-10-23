package net.lumen.media;

import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.function.BooleanSupplier;

/** Public GitHub requests use no media-server credentials; APKs stream to bounded disk files. */
final class GitHubUpdates {
    static final String REPO="sleeper-lfy/my-jellyfin";
    static final String RELEASE="https://api.github.com/repos/"+REPO+"/releases/latest";
    static final String TARGET="https://raw.githubusercontent.com/"+REPO+"/main/target/";
    static final long MAX_APK=256L*1024*1024;
    interface Fetcher {byte[] get(String url,int limit)throws Exception;}
    interface Progress {void update(long done,long total);}
    static final class Candidate {
        final String version,url,sha256,notes,source;final long code,size;
        Candidate(String version,long code,String url,long size,String hash,String notes,String source)throws Exception{
            if(!version.matches("[0-9]{1,6}\\.[0-9]{1,6}\\.[0-9]{1,6}")||size<=0||size>MAX_APK||!hash.matches("[0-9a-fA-F]{64}"))throw new IOException("更新信息格式无效或缺少 SHA-256 校验值");
            validateUrl(url);this.version=version;this.code=code;this.url=url;this.size=size;sha256=hash.toLowerCase(Locale.ROOT);this.notes=notes.length()>2500?notes.substring(0,2500):notes;this.source=source;
        }
    }
    static int compare(String left,String right){
        String[] a=left.replaceFirst("^v","").split("\\."),b=right.replaceFirst("^v","").split("\\.");
        try{for(int i=0;i<Math.max(a.length,b.length);i++){int value=Long.compare(i<a.length?Long.parseLong(a[i]):0,i<b.length?Long.parseLong(b[i]):0);if(value!=0)return value;}}catch(NumberFormatException ignored){return -1;}return 0;
    }
    static Candidate check(String installed,long installedCode,Fetcher fetch)throws Exception{
        Candidate best=null;int successful=0;String error="";
        try{
            JSONObject release=new JSONObject(new String(fetch.get(RELEASE,1024*1024),StandardCharsets.UTF_8));
            String version=release.getString("tag_name").replaceFirst("^v","");successful++;
            if(!release.optBoolean("draft")&&!release.optBoolean("prerelease")&&compare(version,installed)>0){
                JSONArray assets=release.optJSONArray("assets");JSONObject apk=null,checksum=null;
                if(assets!=null)for(int i=0;i<assets.length();i++){JSONObject asset=assets.getJSONObject(i);if(asset.optString("name").equals("Lumen-android-debug.apk"))apk=asset;if(asset.optString("name").equals("Lumen-android-debug.apk.sha256"))checksum=asset;}
                if(apk!=null){String hash=apk.optString("digest").replaceFirst("^sha256:","");if(!hash.matches("[0-9a-fA-F]{64}")&&checksum!=null)hash=new String(fetch.get(checksum.getString("browser_download_url"),4096),StandardCharsets.UTF_8).trim().split("\\s+")[0];best=new Candidate(version,-1,apk.getString("browser_download_url"),apk.getLong("size"),hash,release.optString("body"),"GitHub Releases");}
            }
        }catch(Exception failure){error=failure.getMessage();}
        try{
            JSONObject target=new JSONObject(new String(fetch.get(TARGET+"android-build.json",64*1024),StandardCharsets.UTF_8));
            String version=target.getString("version");long code=target.getLong("version_code");
            Candidate candidate=new Candidate(version,code,TARGET+"Lumen-android-debug.apk",target.getLong("bytes"),target.getString("sha256"),"仓库 target 中经过打包验证的 Android 安装包。","GitHub target");successful++;
            if(code>installedCode&&compare(version,installed)>=0&&(best==null||compare(version,best.version)>=0))best=candidate;
        }catch(Exception failure){error=failure.getMessage();}
        if(successful==0)throw new IOException("无法读取 GitHub 更新信息："+error);
        return best;
    }
    static void validateUrl(String value)throws Exception{
        URI uri=new URI(value);String host=uri.getHost();
        if(!"https".equalsIgnoreCase(uri.getScheme())||uri.getRawUserInfo()!=null||uri.getFragment()!=null||uri.getPort()!=-1&&uri.getPort()!=443||host==null||!(host.equals("github.com")||host.equals("api.github.com")||host.equals("raw.githubusercontent.com")||host.endsWith(".githubusercontent.com")))throw new IOException("更新地址必须来自 GitHub HTTPS");
    }
    static HttpURLConnection open(String value)throws Exception{
        for(int redirects=0;redirects<6;redirects++){
            validateUrl(value);HttpURLConnection connection=(HttpURLConnection)new URL(value).openConnection();connection.setInstanceFollowRedirects(false);connection.setConnectTimeout(15000);connection.setReadTimeout(20000);connection.setRequestProperty("User-Agent","Lumen-Android-Updater");connection.setRequestProperty("Accept-Encoding","identity");
            int status;
            try{status=connection.getResponseCode();}catch(Exception error){connection.disconnect();throw error;}
            if(status>=300&&status<400){String next=connection.getHeaderField("Location");connection.disconnect();if(next==null)throw new IOException("GitHub 重定向无效");value=new URI(value).resolve(next).toString();continue;}
            if(status!=200){connection.disconnect();throw new IOException("GitHub HTTP "+status);}
            return connection;
        }throw new IOException("GitHub 重定向次数过多");
    }
    static byte[] fetch(String url,int limit)throws Exception{
        HttpURLConnection connection=open(url);
        try(InputStream input=connection.getInputStream();ByteArrayOutputStream output=new ByteArrayOutputStream()){
            byte[] buffer=new byte[8192];int count;while((count=input.read(buffer))!=-1){if(output.size()+count>limit)throw new IOException("更新信息过大");output.write(buffer,0,count);}return output.toByteArray();
        }finally{connection.disconnect();}
    }
    static File download(Candidate candidate,File directory,Progress progress,BooleanSupplier cancelled)throws Exception{
        HttpURLConnection connection=open(candidate.url);
        try(InputStream input=connection.getInputStream()){long size=connection.getContentLengthLong();if(size>=0&&size!=candidate.size)throw new IOException("安装包大小与更新信息不符，请重新检查更新");return save(candidate,directory,input,progress,cancelled);}finally{connection.disconnect();}
    }
    static File save(Candidate candidate,File directory,InputStream input,Progress progress,BooleanSupplier cancelled)throws Exception{
        if(!directory.isDirectory()&&!directory.mkdirs())throw new IOException("无法创建更新缓存目录");
        File temporary=File.createTempFile("update-",".part",directory),target=new File(directory,"Lumen-update.apk");long total=0,last=0;MessageDigest digest=MessageDigest.getInstance("SHA-256");
        try{
            try(FileOutputStream output=new FileOutputStream(temporary)){
                byte[] buffer=new byte[64*1024];int count;
                while((count=input.read(buffer))!=-1){if(cancelled.getAsBoolean()||Thread.currentThread().isInterrupted())throw new InterruptedIOException("下载已取消");total+=count;if(total>candidate.size||total>MAX_APK)throw new IOException("安装包大小异常");output.write(buffer,0,count);digest.update(buffer,0,count);long now=System.nanoTime();if(now-last>200_000_000L){progress.update(total,candidate.size);last=now;}}
                output.getFD().sync();
            }
            if(cancelled.getAsBoolean())throw new InterruptedIOException("下载已取消");
            if(total!=candidate.size||!hex(digest.digest()).equals(candidate.sha256))throw new IOException("安装包校验失败，请重新检查更新");
            Files.move(temporary.toPath(),target.toPath(),StandardCopyOption.REPLACE_EXISTING);progress.update(total,candidate.size);return target;
        }finally{Files.deleteIfExists(temporary.toPath());}
    }
    static String hex(byte[] bytes){StringBuilder result=new StringBuilder();for(byte value:bytes)result.append(String.format(Locale.ROOT,"%02x",value&255));return result.toString();}
}
