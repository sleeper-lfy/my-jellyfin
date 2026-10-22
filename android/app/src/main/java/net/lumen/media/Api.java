package net.lumen.media;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

final class Api {
    final Connection connection;
    Api(Connection connection) { this.connection=connection; }
    byte[] fetch(String path, JSONObject body, int maximum) throws Exception {
        if(!path.startsWith("/api/") || path.contains(".."))throw new Exception("无效服务端路径");
        HttpURLConnection request=(HttpURLConnection)new URL(connection.base+path).openConnection();
        request.setConnectTimeout(6000);request.setReadTimeout(12000);request.setInstanceFollowRedirects(false);
        request.setRequestProperty("Authorization","Bearer "+connection.token);
        try {
            if(body!=null) {
                byte[] bytes=body.toString().getBytes(StandardCharsets.UTF_8);
                request.setRequestMethod("POST");request.setDoOutput(true);request.setFixedLengthStreamingMode(bytes.length);
                request.setRequestProperty("Content-Type","application/json");
                try(java.io.OutputStream output=request.getOutputStream()){output.write(bytes);}
            }
            int status=request.getResponseCode();
            if(status==401)throw new Exception("访问密钥不正确，请重新连接电脑");
            if(status<200 || status>=300)throw new Exception("服务端返回 "+status+"，请检查电脑端服务与媒体文件");
            try(InputStream input=request.getInputStream();ByteArrayOutputStream output=new ByteArrayOutputStream()) {
                byte[] buffer=new byte[8192];int count;
                while((count=input.read(buffer))!=-1) {
                    if(output.size()+count>maximum)throw new Exception("响应超过大小限制");
                    output.write(buffer,0,count);
                }
                return output.toByteArray();
            }
        } finally {request.disconnect();}
    }
    JSONObject get(String path) throws Exception {return new JSONObject(new String(fetch(path,null,4_000_000),StandardCharsets.UTF_8));}
    JSONObject post(String path,JSONObject body) throws Exception {return new JSONObject(new String(fetch(path,body,4_000_000),StandardCharsets.UTF_8));}
    Bitmap image(String path) throws Exception {
        byte[] bytes=fetch(path,null,10_000_000);
        BitmapFactory.Options options=new BitmapFactory.Options();options.inJustDecodeBounds=true;BitmapFactory.decodeByteArray(bytes,0,bytes.length,options);
        if(options.outWidth<=0 || (long)options.outWidth*options.outHeight>40_000_000)throw new Exception("无效图片");
        options.inJustDecodeBounds=false;options.inSampleSize=1;
        while(options.outWidth/options.inSampleSize>800)options.inSampleSize*=2;
        return BitmapFactory.decodeByteArray(bytes,0,bytes.length,options);
    }
}
