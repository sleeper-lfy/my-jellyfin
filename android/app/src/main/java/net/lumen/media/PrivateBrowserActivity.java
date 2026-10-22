package net.lumen.media;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebStorage;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

/** App-local private website viewer: no cookies, DOM storage, cache or retained history. */
public final class PrivateBrowserActivity extends Activity {
    private WebView web;
    static boolean website(Uri uri){return uri!=null&&("https".equals(uri.getScheme())||"http".equals(uri.getScheme()))
        &&uri.getHost()!=null&&uri.getUserInfo()==null;}
    static void open(Activity activity,String url){
        Uri uri=Uri.parse(url);
        if(!website(uri)){Toast.makeText(activity,"网页地址无效",Toast.LENGTH_SHORT).show();return;}
        activity.startActivity(new Intent(activity,PrivateBrowserActivity.class).setData(uri));
    }
    @Override protected void onCreate(Bundle state){
        super.onCreate(state);
        Uri uri=getIntent().getData();if(!website(uri)){finish();return;}
        LinearLayout layout=new LinearLayout(this);layout.setOrientation(LinearLayout.VERTICAL);layout.setBackgroundColor(Color.BLACK);layout.setFitsSystemWindows(true);
        LinearLayout bar=new LinearLayout(this);
        Button close=new Button(this);close.setText("关闭");close.setOnClickListener(v->finish());bar.addView(close);
        TextView location=new TextView(this);location.setTextColor(Color.WHITE);location.setText("无痕浏览 · "+uri.getHost());location.setMaxLines(2);
        bar.addView(location,new LinearLayout.LayoutParams(0,-2,1));layout.addView(bar);
        web=new WebView(this);layout.addView(web,new LinearLayout.LayoutParams(-1,0,1));
        WebSettings settings=web.getSettings();settings.setJavaScriptEnabled(true);settings.setDomStorageEnabled(false);
        settings.setDatabaseEnabled(false);settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        settings.setAllowFileAccess(false);settings.setAllowContentAccess(false);settings.setSaveFormData(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        CookieManager cookies=CookieManager.getInstance();cookies.setAcceptCookie(false);cookies.setAcceptThirdPartyCookies(web,false);
        cookies.removeAllCookies(null);web.clearCache(true);WebStorage.getInstance().deleteAllData();
        web.setDownloadListener((url,userAgent,contentDisposition,mimeType,contentLength)->DirectDownload.start(this,url));
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){return !website(request.getUrl());}
            @Override public void onPageFinished(WebView view,String url){Uri current=Uri.parse(url);location.setText("无痕浏览 · "+current.getHost());}
        });
        setContentView(layout);web.loadUrl(uri.toString());
    }
    @Override public void onBackPressed(){if(web!=null&&web.canGoBack())web.goBack();else super.onBackPressed();}
    @Override protected void onPause(){if(web!=null){web.onPause();web.clearCache(true);CookieManager.getInstance().removeAllCookies(null);}super.onPause();}
    @Override protected void onResume(){super.onResume();if(web!=null)web.onResume();}
    @Override protected void onDestroy(){
        if(web!=null){web.stopLoading();web.loadUrl("about:blank");web.clearHistory();web.clearCache(true);
            CookieManager.getInstance().removeAllCookies(null);WebStorage.getInstance().deleteAllData();
            ((android.view.ViewGroup)web.getParent()).removeView(web);web.destroy();web=null;}
        super.onDestroy();
    }
}
