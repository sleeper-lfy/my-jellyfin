package net.lumen.media;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Set;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import okhttp3.Call;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

/** Loopback-only streaming bridge: native decoders never receive the server credential. */
final class PlaybackBridge implements AutoCloseable {
    /** Payload received from the LAN, independent of LibVLC's loopback statistics. */
    static final class Stats {
        final long videoBytesRead,rangeRequests,lastResponseMillis,upstreamVideoRequests,cacheHits,cachedVideoBytes;
        final int activeVideoRequests,lastResponseCode;
        Stats(long bytes,long ranges,int active,int code,long millis,long upstream,long hits,long cached) {
            videoBytesRead=bytes;rangeRequests=ranges;activeVideoRequests=active;
            lastResponseCode=code;lastResponseMillis=millis;
            upstreamVideoRequests=upstream;cacheHits=hits;cachedVideoBytes=cached;
        }
    }
    private final String base, token, prefix, filePath;
    private final ServerSocket listener;
    private final Set<Socket> sockets=ConcurrentHashMap.newKeySet();
    private final Set<Call> upstreams=ConcurrentHashMap.newKeySet();
    private final AtomicLong videoBytesRead=new AtomicLong(),rangeRequests=new AtomicLong();
    private final AtomicLong upstreamVideoRequests=new AtomicLong(),cacheHits=new AtomicLong(),cachedVideoBytes=new AtomicLong();
    private final VideoReadCache cache=new VideoReadCache();
    private volatile Source source;
    private final AtomicInteger activeVideoRequests=new AtomicInteger();
    private volatile int lastResponseCode;
    private volatile long lastResponseMillis=-1;
    private final OkHttpClient client=new OkHttpClient.Builder().proxy(Proxy.NO_PROXY)
        .connectTimeout(8,TimeUnit.SECONDS).readTimeout(15,TimeUnit.SECONDS)
        .followRedirects(false).followSslRedirects(false).build();
    private final ExecutorService disconnects=new ThreadPoolExecutor(4,4,0,TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(8),r->{Thread t=new Thread(r,"media-disconnect");t.setDaemon(true);return t;});
    private final ThreadPoolExecutor workers=new ThreadPoolExecutor(4,4,0,TimeUnit.SECONDS,new ArrayBlockingQueue<>(8));
    private volatile boolean closed;
    private static final Pattern CONTENT_RANGE=Pattern.compile("bytes ([0-9]+)-([0-9]+)/([0-9]+)");
    private static final Pattern REQUEST_RANGE=Pattern.compile("bytes=([0-9]+)-([0-9]*)");
    private static final class Source {
        final long length;final String type;
        Source(long size,String mime){length=size;type=mime;}
    }
    private static long number(String value){try{return Long.parseLong(value);}catch(NumberFormatException ignored){return -1;}}

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
    Stats snapshot() {
        return new Stats(videoBytesRead.get(),rangeRequests.get(),activeVideoRequests.get(),lastResponseCode,lastResponseMillis,
            upstreamVideoRequests.get(),cacheHits.get(),cachedVideoBytes.get());
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
        AtomicReference<Call> current=new AtomicReference<>();
        boolean videoRequest=false;
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
            videoRequest=request[0].equals("GET")&&path.equals(filePath+"stream");
            if(videoRequest){activeVideoRequests.incrementAndGet();if(range!=null)rangeRequests.incrementAndGet();}
            peer.setSoTimeout(0);
            Source known=source;long start=0,end=known==null?-1:known.length-1;
            boolean simple=range==null;
            if(range!=null){Matcher match=REQUEST_RANGE.matcher(range);if(match.matches()){
                start=number(match.group(1));long requestedEnd=match.group(2).isEmpty()?Long.MAX_VALUE:number(match.group(2));
                simple=start>=0&&requestedEnd>=start;if(known!=null)end=Math.min(requestedEnd,known.length-1);
            }}
            byte[] buffer=new byte[VideoReadCache.BLOCK_SIZE];
            int cached=videoRequest&&known!=null&&simple&&start<=end?cache.read(start,buffer,(int)Math.min(buffer.length,end-start+1)):0;
            if(cached>0){
                cacheHits.incrementAndGet();StringBuilder headers=new StringBuilder("HTTP/1.1 "+(range==null?200:206)+" Media\r\nConnection: close\r\nAccept-Ranges: bytes\r\nContent-Length: "+(end-start+1)+"\r\n");
                if(known.type!=null)headers.append("Content-Type: ").append(known.type).append("\r\n");
                if(range!=null)headers.append("Content-Range: bytes ").append(start).append('-').append(end).append('/').append(known.length).append("\r\n");
                output.write(headers.append("\r\n").toString().getBytes(StandardCharsets.US_ASCII));output.flush();
                long position=start;
                while(cached>0&&!closed&&!peer.isClosed()){
                    output.write(buffer,0,cached);cachedVideoBytes.addAndGet(cached);position+=cached;
                    if(position>end)return;
                    cached=cache.read(position,buffer,(int)Math.min(buffer.length,end-position+1));
                }
                // An open-ended response keeps its real remaining length. A cache
                // gap resumes from that exact byte instead of returning a short body.
                if(!closed&&!peer.isClosed())forward(peer,input,output,current,path,"GET","bytes="+position+"-"+end,true,false,position,end,known.length);
            }else forward(peer,input,output,current,path,request[0],range,videoRequest,true,-1,-1,-1);
        }catch(IOException|RejectedExecutionException ignored){/* Seeking and leaving playback cancel in-flight requests. */}
        finally {if(videoRequest)activeVideoRequests.decrementAndGet();sockets.remove(socket);Call call=current.get();if(call!=null){upstreams.remove(call);call.cancel();}}
    }
    private void forward(Socket peer,InputStream input,OutputStream output,AtomicReference<Call> current,String path,String method,String range,
                         boolean videoRequest,boolean headersNeeded,long expectedStart,long expectedEnd,long expectedLength)throws IOException {
        Request.Builder builder=new Request.Builder().url(base+path).method(method,null)
            .header("Authorization","Bearer "+token).header("Accept-Encoding","identity");
        if(range!=null)builder.header("Range",range);
        Call call=client.newCall(builder.build());current.set(call);upstreams.add(call);
        try {
            if(closed||peer.isClosed()){call.cancel();return;}
            // Only an upstream read needs a disconnect watcher. Fast cache-only
            // responses must not queue hundreds of otherwise idle monitor jobs.
            disconnects.execute(()->{
                try {input.read();}catch(IOException ignored){}
                finally {call.cancel();try{peer.close();}catch(IOException ignored){}}
            });
            if(videoRequest)upstreamVideoRequests.incrementAndGet();
            long requestedAt=System.nanoTime();
            try(Response response=call.execute()){
                int status=response.code();
                if(videoRequest){lastResponseCode=status;lastResponseMillis=TimeUnit.NANOSECONDS.toMillis(System.nanoTime()-requestedAt);}
                long offset=0,total=-1,end=-1;
                if(status==206){Matcher match=CONTENT_RANGE.matcher(response.header("Content-Range",""));if(match.matches()){
                    offset=number(match.group(1));end=number(match.group(2));total=number(match.group(3));
                    if(offset<0||end<offset||total<=end)total=-1;
                    long length=number(response.header("Content-Length","-1"));if(length>=0&&length!=end-offset+1)total=-1;
                }}else if(status==200){total=number(response.header("Content-Length","-1"));end=total-1;}
                if(!headersNeeded&&(status!=206||offset!=expectedStart||end!=expectedEnd||total!=expectedLength)){cache.clear();source=null;throw new IOException("Changed video response");}
                if(headersNeeded){
                    if(status!=200&&status!=206&&status!=416){reject(output,status>=400?status:502);return;}
                    StringBuilder headers=new StringBuilder("HTTP/1.1 "+status+" Media\r\nConnection: close\r\n");
                    for(String name:new String[]{"Content-Type","Content-Length","Content-Range","Accept-Ranges"}){
                        String value=response.header(name);if(value!=null&&!value.contains("\r")&&!value.contains("\n"))headers.append(name).append(": ").append(value).append("\r\n");
                    }
                    output.write(headers.append("\r\n").toString().getBytes(StandardCharsets.US_ASCII));output.flush();
                }
                boolean cacheable=videoRequest&&total>0&&(status==200||status==206);
                if(cacheable){
                    Source previous=source;if(previous!=null&&previous.length!=total){cache.clear();if(!headersNeeded)throw new IOException("Changed video size");}
                    String type=response.header("Content-Type");if(type!=null&&(type.contains("\r")||type.contains("\n")))type=null;
                    source=new Source(total,type);
                }
                if(!method.equals("HEAD")&&status!=416&&response.body()!=null)try(InputStream media=response.body().byteStream()){
                    byte[] buffer=new byte[VideoReadCache.BLOCK_SIZE];int count;
                    while(!closed&&!peer.isClosed()&&(count=media.read(buffer))!=-1){
                        if(videoRequest)videoBytesRead.addAndGet(count);
                        if(cacheable&&offset<=end){int received=(int)Math.min(count,end-offset+1);cache.put(offset,buffer,received);}
                        output.write(buffer,0,count);offset+=count;
                    }
                }
            }
        }finally {upstreams.remove(call);current.compareAndSet(call,null);call.cancel();}
    }
    @Override public void close() {
        closed=true;try{listener.close();}catch(IOException ignored){}
        for(Socket socket:sockets)try{socket.close();}catch(IOException ignored){}
        for(Call connection:upstreams)connection.cancel();
        cache.close();source=null;
        workers.shutdownNow();disconnects.shutdownNow();client.connectionPool().evictAll();client.dispatcher().executorService().shutdown();
    }
}
