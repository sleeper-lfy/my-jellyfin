package net.lumen.media;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Set;
import java.util.concurrent.*;

/** Loopback-only streaming bridge: native decoders never receive the server credential. */
final class PlaybackBridge implements AutoCloseable {
    private final String base, token, prefix, filePath;
    private final ServerSocket listener;
    private final Set<Socket> sockets=ConcurrentHashMap.newKeySet();
    private final Set<HttpURLConnection> upstreams=ConcurrentHashMap.newKeySet();
    private final ThreadPoolExecutor workers=new ThreadPoolExecutor(4,4,0,TimeUnit.SECONDS,new ArrayBlockingQueue<>(8));
    private volatile boolean closed;

    PlaybackBridge(String base,String token,long fileId) throws IOException {
        this.base=base;this.token=token;filePath="/api/files/"+fileId+"/";
        byte[] secret=new byte[24];new SecureRandom().nextBytes(secret);
        StringBuilder key=new StringBuilder();for(byte b:secret)key.append(String.format(java.util.Locale.ROOT,"%02x",b&255));
        prefix="/"+key;
        listener=new ServerSocket();listener.bind(new InetSocketAddress("127.0.0.1",0),8);
        Thread accept=new Thread(()->{
            while(!closed) {
                try {
                    Socket socket=listener.accept();socket.setSoTimeout(15000);sockets.add(socket);
                    try {workers.execute(()->serve(socket));}
                    catch(RejectedExecutionException e){sockets.remove(socket);socket.close();}
                }catch(IOException ignored){if(!closed)close();}
            }
        },"local-media-stream");accept.setDaemon(true);accept.start();
    }
    String url(String path) {
        if(!allowed(path))throw new IllegalArgumentException("Invalid playback path");
        return "http://127.0.0.1:"+listener.getLocalPort()+prefix+path;
    }
    private boolean allowed(String path) {
        return path.equals(filePath+"stream") || path.matches(java.util.regex.Pattern.quote(filePath)+"subtitles/[0-9]+");
    }
    private static String line(InputStream input) throws IOException {
        ByteArrayOutputStream out=new ByteArrayOutputStream();int b;
        while((b=input.read())!=-1 && b!='\n') {if(out.size()>=8192)throw new IOException("Header too long");if(b!='\r')out.write(b);}
        return out.toString(StandardCharsets.US_ASCII.name());
    }
    private static void reject(OutputStream out,int status) throws IOException {
        out.write(("HTTP/1.1 "+status+" Rejected\r\nContent-Length: 0\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.US_ASCII));out.flush();
    }
    private void serve(Socket socket) {
        HttpURLConnection upstream=null;
        try(Socket peer=socket) {
            InputStream input=new BufferedInputStream(peer.getInputStream());OutputStream output=peer.getOutputStream();
            String[] request=line(input).split(" ");
            if(request.length!=3 || !(request[0].equals("GET")||request[0].equals("HEAD"))) {reject(output,405);return;}
            String path=request[1].startsWith(prefix)?request[1].substring(prefix.length()):"";
            if(!allowed(path)){reject(output,404);return;}
            String range=null;int size=0;
            for(String header=line(input);!header.isEmpty();header=line(input)) {
                size+=header.length();if(size>32768){reject(output,431);return;}
                if(header.regionMatches(true,0,"Range:",0,6))range=header.substring(6).trim();
            }
            upstream=(HttpURLConnection)new URL(base+path).openConnection(Proxy.NO_PROXY);
            upstream.setInstanceFollowRedirects(false);upstream.setConnectTimeout(8000);upstream.setReadTimeout(15000);
            upstream.setRequestMethod(request[0]);upstream.setRequestProperty("Authorization","Bearer "+token);
            upstream.setRequestProperty("Accept-Encoding","identity");if(range!=null)upstream.setRequestProperty("Range",range);
            upstreams.add(upstream);if(closed)return;
            int status=upstream.getResponseCode();
            // Do not forward redirects or server-generated error bodies to the native player.
            if(status!=200 && status!=206 && status!=416){reject(output,status>=400?status:502);return;}
            StringBuilder headers=new StringBuilder("HTTP/1.1 "+status+" Media\r\nConnection: close\r\n");
            for(String name:new String[]{"Content-Type","Content-Length","Content-Range","Accept-Ranges"}) {
                String value=upstream.getHeaderField(name);if(value!=null&&!value.contains("\r")&&!value.contains("\n"))headers.append(name).append(": ").append(value).append("\r\n");
            }
            output.write(headers.append("\r\n").toString().getBytes(StandardCharsets.US_ASCII));output.flush();
            if(!request[0].equals("HEAD") && status!=416)try(InputStream media=upstream.getInputStream()) {
                byte[] buffer=new byte[64*1024];int count;
                while(!closed && (count=media.read(buffer))!=-1)output.write(buffer,0,count);
            }
        }catch(IOException ignored){/* Seeking and leaving playback cancel in-flight requests. */}
        finally {sockets.remove(socket);if(upstream!=null){upstreams.remove(upstream);upstream.disconnect();}}
    }
    @Override public void close() {
        closed=true;try{listener.close();}catch(IOException ignored){}
        for(Socket socket:sockets)try{socket.close();}catch(IOException ignored){}
        for(HttpURLConnection connection:upstreams)connection.disconnect();
        workers.shutdownNow();
    }
}
