package net.lumen.media;

import android.app.Activity;
import android.content.ClipData;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.widget.*;
import java.io.File;
import java.security.MessageDigest;
import java.util.HashSet;
import java.util.Set;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Explicit user-driven GitHub update check, bounded streaming download and system installation. */
public final class UpdateActivity extends Activity {
    private final ExecutorService network=Executors.newSingleThreadExecutor();
    GitHubUpdates.Fetcher fetcher=GitHubUpdates::fetch;
    private volatile boolean cancelled=false;private boolean busy=false,pendingInstall=false;
    private TextView status,notes;private ProgressBar progress;private Button check,download,install,cancel;
    private GitHubUpdates.Candidate candidate;private File downloaded;private PackageInfo installed;
    private int dp(int value){return Math.round(value*getResources().getDisplayMetrics().density);}
    private TextView label(String value,int size){TextView view=new TextView(this);view.setText(value);view.setTextSize(size);view.setTextColor(Color.WHITE);view.setPadding(0,dp(10),0,dp(10));return view;}
    private Button button(String value,Runnable action){Button button=new Button(this);button.setText(value);MediaStyle.button(button,false,false,false);button.setOnClickListener(view->action.run());return button;}
    @SuppressWarnings("deprecation") static int signatureFlags(){return Build.VERSION.SDK_INT>=28?PackageManager.GET_SIGNING_CERTIFICATES:PackageManager.GET_SIGNATURES;}
    @SuppressWarnings("deprecation") static long versionCode(PackageInfo info){return Build.VERSION.SDK_INT>=28?info.getLongVersionCode():info.versionCode;}
    @SuppressWarnings("deprecation") static Set<String> certificates(PackageInfo info)throws Exception{
        Signature[] signatures=Build.VERSION.SDK_INT>=28&&info.signingInfo!=null?info.signingInfo.getApkContentsSigners():info.signatures;
        if(signatures==null||signatures.length==0)throw new Exception("无法验证安装包签名");Set<String> values=new HashSet<>();for(Signature signature:signatures)values.add(GitHubUpdates.hex(MessageDigest.getInstance("SHA-256").digest(signature.toByteArray())));return values;
    }
    static void validateArchive(PackageInfo archive,PackageInfo installed,GitHubUpdates.Candidate expected)throws Exception{
        if(archive==null||!installed.packageName.equals(archive.packageName))throw new Exception("安装包不属于 Lumen");
        if(versionCode(archive)<=versionCode(installed))throw new Exception("下载的安装包不是更高版本");
        if(!expected.version.equals(archive.versionName)||expected.code>0&&expected.code!=versionCode(archive))throw new Exception("安装包版本与更新信息不符");
        if(!certificates(installed).equals(certificates(archive)))throw new Exception("安装包签名与当前应用不同，不能覆盖安装");
    }
    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        try{installed=getPackageManager().getPackageInfo(getPackageName(),signatureFlags());}catch(Exception error){finish();return;}
        LinearLayout page=new LinearLayout(this);page.setOrientation(LinearLayout.VERTICAL);page.setPadding(dp(24),dp(20),dp(24),dp(20));page.setBackgroundColor(Color.rgb(16,16,16));page.setFitsSystemWindows(true);
        page.addView(button("返回",this::finish));page.addView(label("检查更新",26));page.addView(label("当前版本 "+installed.versionName+" · "+versionCode(installed),15));
        status=label("从 GitHub Releases 和仓库 target 检查新版，不需要连接媒体服务器。",15);status.setMinHeight(dp(76));page.addView(status);
        progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);progress.setMax(1000);page.addView(progress,new LinearLayout.LayoutParams(-1,dp(8)));
        notes=label("",14);page.addView(notes);
        check=button("检查更新",this::check);download=button("下载新版 APK",this::download);install=button("安装已校验的更新",this::install);cancel=button("取消下载",()->{cancelled=true;cancel.setEnabled(false);status.setText("正在取消下载…");});
        for(Button button:new Button[]{check,download,install,cancel})page.addView(button);
        download.setEnabled(false);install.setEnabled(false);cancel.setEnabled(false);
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.addView(page);setContentView(scroll);check();
    }
    private void state(boolean working){busy=working;check.setEnabled(!working);download.setEnabled(!working&&candidate!=null);install.setEnabled(!working&&downloaded!=null);cancel.setEnabled(working&&candidate!=null);}
    private void ui(Runnable action){runOnUiThread(()->{if(!isDestroyed()&&!isFinishing())action.run();});}
    private void check(){
        if(busy)return;cancelled=false;candidate=null;downloaded=null;state(true);progress.setIndeterminate(true);status.setText("正在检查 GitHub 更新…");
        network.execute(()->{try{
            GitHubUpdates.Candidate found=GitHubUpdates.check(installed.versionName,versionCode(installed),fetcher);
            ui(()->{candidate=found;progress.setIndeterminate(false);state(false);status.setText(found==null?"未发现可用的更高版本安装包。":"发现新版 "+found.version+" · "+String.format(Locale.ROOT,"%.1f MiB",found.size/1048576.0)+"\n来源："+found.source);notes.setText(found==null?"":found.notes);});
        }catch(Exception error){ui(()->{progress.setIndeterminate(false);state(false);status.setText("检查失败，可稍后重试："+error.getMessage());});}});
    }
    private void download(){
        if(busy||candidate==null)return;GitHubUpdates.Candidate selected=candidate;cancelled=false;downloaded=null;state(true);progress.setIndeterminate(false);progress.setProgress(0);status.setText("正在下载 "+selected.version+"…");
        network.execute(()->{try{
            File file=GitHubUpdates.download(selected,new File(getCacheDir(),"updates"),(done,total)->ui(()->{progress.setProgress((int)(done*1000/total));status.setText(String.format(Locale.ROOT,"下载 %.1f / %.1f MiB · %d%%",done/1048576.0,total/1048576.0,done*100/total));}),()->cancelled);
            try{PackageInfo archive=getPackageManager().getPackageArchiveInfo(file.getAbsolutePath(),signatureFlags());validateArchive(archive,installed,selected);}catch(Exception error){java.nio.file.Files.deleteIfExists(file.toPath());throw error;}
            ui(()->{downloaded=file;state(false);status.setText("下载完成，大小、SHA-256、包名、版本和签名已校验。点击安装后由系统确认。");});
        }catch(Exception error){ui(()->{state(false);status.setText(cancelled?"下载已取消，临时文件已清理。":"下载失败："+error.getMessage());});}});
    }
    private void install(){
        if(downloaded==null||busy)return;
        try{
            if(!getPackageManager().canRequestPackageInstalls()){
                pendingInstall=true;status.setText("请在系统页面允许 Lumen 安装应用，返回后继续安装。");startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:"+getPackageName())));return;
            }
            Uri uri=new Uri.Builder().scheme("content").authority(getPackageName()+".updates").appendPath("Lumen-update.apk").build();
            Intent intent=new Intent(Intent.ACTION_VIEW).setDataAndType(uri,"application/vnd.android.package-archive").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);intent.setClipData(ClipData.newRawUri("Lumen update",uri));startActivity(intent);
        }catch(Exception error){status.setText("无法打开系统安装界面："+error.getMessage());}
    }
    @Override protected void onResume(){super.onResume();if(pendingInstall){pendingInstall=false;if(getPackageManager().canRequestPackageInstalls())install();else status.setText("尚未获得安装授权，可以授权后再次点击安装。");}}
    @Override protected void onDestroy(){cancelled=true;network.shutdownNow();super.onDestroy();}
}
