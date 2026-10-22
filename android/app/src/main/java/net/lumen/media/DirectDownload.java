package net.lumen.media;

import android.app.Activity;
import android.app.DownloadManager;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.widget.Toast;

/** HTTP download clicks go to the system downloader, keeping normal browser history untouched. */
final class DirectDownload {
    private DirectDownload(){}
    static void start(Activity activity,String url){
        Uri uri=Uri.parse(url);
        if(!PrivateBrowserActivity.website(uri)){Toast.makeText(activity,"下载地址无效",Toast.LENGTH_SHORT).show();return;}
        String name=uri.getLastPathSegment();
        if(name==null||name.isEmpty())name="Lumen-download";
        name=name.replaceAll("[^\\p{L}\\p{N}._-]","_");if(name.length()>120)name=name.substring(name.length()-120);
        name=System.currentTimeMillis()+"-"+name;
        try{
            DownloadManager.Request request=new DownloadManager.Request(uri).setTitle(name)
                .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            if(Build.VERSION.SDK_INT>=29)request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS,name);
            else request.setDestinationInExternalFilesDir(activity,Environment.DIRECTORY_DOWNLOADS,name);
            ((DownloadManager)activity.getSystemService(Activity.DOWNLOAD_SERVICE)).enqueue(request);
            Toast.makeText(activity,"已交给系统下载器，可在通知中查看进度",Toast.LENGTH_LONG).show();
        }catch(RuntimeException error){Toast.makeText(activity,"无法启动下载："+error.getMessage(),Toast.LENGTH_LONG).show();}
    }
}
