package net.lumen.media;

import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.RecordedRequest;
import okhttp3.mockwebserver.Dispatcher;
import org.junit.*;
import static org.junit.Assert.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class PlaybackBridgeTest {
    private MockWebServer upstream;
    private PlaybackBridge bridge;
    private final AtomicReference<String> authorization=new AtomicReference<>();
    private final AtomicReference<String> range=new AtomicReference<>();
    private final AtomicInteger calls=new AtomicInteger();
    private volatile boolean redirect;
    private final byte[] movie=new byte[512*1024+37];
    @Before public void setup() throws Exception {
        for(int i=0;i<movie.length;i++)movie[i]=(byte)(i%251);
        upstream=new MockWebServer();
        upstream.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){
            calls.incrementAndGet();authorization.set(request.getHeader("Authorization"));
            range.set(request.getHeader("Range"));
            if(redirect)return new MockResponse().setResponseCode(302).setHeader("Location","/unexpected");
            byte[] bytes=request.getPath().contains("subtitles")?"subtitle".getBytes(StandardCharsets.UTF_8):movie;
            MockResponse response=new MockResponse().setHeader("Content-Type","video/mp4").setHeader("Accept-Ranges","bytes");
            if(range.get()!=null){bytes=java.util.Arrays.copyOfRange(movie,2,6);response.setResponseCode(206).setHeader("Content-Range","bytes 2-5/"+movie.length);}
            if(request.getMethod().equals("HEAD"))response.setHeader("Content-Length",bytes.length);
            else response.setBody(new okio.Buffer().write(bytes));
            return response;
        }});upstream.start(java.net.InetAddress.getByName("127.0.0.1"),0);
        bridge=new PlaybackBridge(upstream.url("/").toString().replaceAll("/+$",""),"test-server-secret",7);
    }
    @After public void cleanup() throws Exception {bridge.close();upstream.shutdown();}

    private HttpURLConnection open(String url) throws Exception {HttpURLConnection connection=(HttpURLConnection)new URL(url).openConnection(Proxy.NO_PROXY);connection.setReadTimeout(3000);return connection;}
    @Test public void streamsAllBytesAndKeepsCredentialOutOfUrl() throws Exception {
        String url=bridge.url("/api/files/7/stream");assertFalse(url.contains("test-server-secret"));
        HttpURLConnection connection=open(url);assertEquals(200,connection.getResponseCode());
        assertArrayEquals(movie,connection.getInputStream().readAllBytes());connection.disconnect();
        assertEquals("Bearer test-server-secret",authorization.get());
    }
    @Test public void measuresActualVideoPayloadWithoutHeadSubtitlesOrErrors() throws Exception {
        PlaybackBridge.Stats initial=bridge.snapshot();
        assertEquals(0,initial.videoBytesRead);assertEquals(0,initial.rangeRequests);
        assertEquals(0,initial.activeVideoRequests);assertEquals(0,initial.lastResponseCode);
        assertEquals(-1,initial.lastResponseMillis);
        HttpURLConnection video=open(bridge.url("/api/files/7/stream"));
        try{assertArrayEquals(movie,video.getInputStream().readAllBytes());}finally{video.disconnect();}
        PlaybackBridge.Stats read=bridge.snapshot();
        assertEquals(movie.length,read.videoBytesRead);assertEquals(200,read.lastResponseCode);
        assertTrue(read.lastResponseMillis>=0);

        HttpURLConnection head=open(bridge.url("/api/files/7/stream"));head.setRequestMethod("HEAD");
        try{assertEquals(200,head.getResponseCode());assertEquals(0,head.getInputStream().readAllBytes().length);}finally{head.disconnect();}
        HttpURLConnection subtitle=open(bridge.url("/api/files/7/subtitles/0"));
        try{assertEquals("subtitle",new String(subtitle.getInputStream().readAllBytes(),StandardCharsets.UTF_8));}finally{subtitle.disconnect();}
        assertEquals(movie.length,bridge.snapshot().videoBytesRead);

        HttpURLConnection rangeVideo=open(bridge.url("/api/files/7/stream"));rangeVideo.setRequestProperty("Range","bytes=2-5");
        try{assertEquals(206,rangeVideo.getResponseCode());assertEquals(4,rangeVideo.getInputStream().readAllBytes().length);}finally{rangeVideo.disconnect();}
        assertEquals(movie.length,bridge.snapshot().videoBytesRead);
        assertEquals(4,bridge.snapshot().cachedVideoBytes);assertEquals(1,bridge.snapshot().cacheHits);
        assertEquals(1,bridge.snapshot().upstreamVideoRequests);
        assertEquals(1,bridge.snapshot().rangeRequests);assertEquals(200,bridge.snapshot().lastResponseCode); // Last computer response; cached 206 is local.
        redirect=true;
        HttpURLConnection refused=open(bridge.url("/api/files/7/stream"));
        refused.setRequestProperty("Range","bytes="+(movie.length+1)+"-");
        try{assertEquals(502,refused.getResponseCode());}finally{refused.disconnect();}
        assertEquals(movie.length,bridge.snapshot().videoBytesRead);
        assertEquals(302,bridge.snapshot().lastResponseCode);
        assertEquals(0,initial.videoBytesRead); // Snapshots do not change under the caller.
    }
    @Test public void forwardsRangeAndHead() throws Exception {
        HttpURLConnection connection=open(bridge.url("/api/files/7/stream"));connection.setRequestProperty("Range","bytes=2-5");
        assertEquals(206,connection.getResponseCode());assertEquals("bytes 2-5/"+movie.length,connection.getHeaderField("Content-Range"));
        assertArrayEquals(java.util.Arrays.copyOfRange(movie,2,6),connection.getInputStream().readAllBytes());connection.disconnect();
        connection=open(bridge.url("/api/files/7/stream"));connection.setRequestMethod("HEAD");
        assertEquals(movie.length,connection.getContentLength());assertEquals(0,connection.getInputStream().readAllBytes().length);connection.disconnect();
    }
    @Test public void rejectsGuessedPathOtherFilesAndPost() throws Exception {
        String url=bridge.url("/api/files/7/stream");
        assertEquals(404,open(url.replace("/api/files/7/","/api/files/8/")).getResponseCode());
        assertEquals(404,open(new URL(url).getProtocol()+"://"+new URL(url).getAuthority()+"/api/files/7/stream").getResponseCode());
        HttpURLConnection post=open(url);post.setRequestMethod("POST");assertEquals(405,post.getResponseCode());
        assertEquals(0,calls.get());
    }
    @Test public void streamsSubtitlesAndRefusesRedirects() throws Exception {
        assertEquals("subtitle",new String(open(bridge.url("/api/files/7/subtitles/0")).getInputStream().readAllBytes(),StandardCharsets.UTF_8));
        redirect=true;assertEquals(502,open(bridge.url("/api/files/7/stream")).getResponseCode());assertEquals(2,calls.get());
    }
    @Test public void abandonedStreamsDoNotDelayTheNextSeek() throws Exception {
        AtomicInteger requests=new AtomicInteger();
        upstream.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){
            MockResponse response=new MockResponse().setBody("seek-result");
            if(requests.incrementAndGet()<=4)response.setBodyDelay(4,java.util.concurrent.TimeUnit.SECONDS);
            return response;
        }});
        URL url=new URL(bridge.url("/api/files/7/stream"));
        for(int i=0;i<4;i++) {
            try(Socket abandoned=new Socket(url.getHost(),url.getPort())) {
                abandoned.setSoTimeout(2000);
                abandoned.getOutputStream().write(("GET "+url.getPath()+" HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
                // Wait for the response headers, then leave while the upstream body is stalled.
                int matched=0;byte[] boundary={13,10,13,10};
                while(matched<4){int b=abandoned.getInputStream().read();assertTrue("response headers for request "+i,b>=0);matched=b==boundary[matched]?matched+1:b==13?1:0;}
            }
        }
        HttpURLConnection next=open(url.toString());next.setReadTimeout(1500);
        try {assertEquals("seek-result",new String(next.getInputStream().readAllBytes(),StandardCharsets.UTF_8));}
        finally {next.disconnect();}
    }
    private void realRangeResponses(){
        upstream.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){
            calls.incrementAndGet();authorization.set(request.getHeader("Authorization"));range.set(request.getHeader("Range"));
            String header=request.getHeader("Range");long from=0,to=movie.length-1;
            if(header!=null){java.util.regex.Matcher match=java.util.regex.Pattern.compile("bytes=([0-9]+)-([0-9]*)").matcher(header);
                if(!match.matches())return new MockResponse().setResponseCode(416).setHeader("Content-Range","bytes */"+movie.length);
                from=Long.parseLong(match.group(1));if(!match.group(2).isEmpty())to=Math.min(to,Long.parseLong(match.group(2)));
            }
            if(from>to||from>=movie.length)return new MockResponse().setResponseCode(416).setHeader("Content-Range","bytes */"+movie.length);
            MockResponse response=new MockResponse().setHeader("Content-Type","video/mp4").setHeader("Accept-Ranges","bytes");
            if(header!=null)response.setResponseCode(206).setHeader("Content-Range","bytes "+from+"-"+to+"/"+movie.length);
            if(request.getMethod().equals("HEAD"))return response.setHeader("Content-Length",to-from+1);
            return response.setBody(new okio.Buffer().write(movie,(int)from,(int)(to-from+1)));
        }});
    }
    private byte[] readRange(int from,String end)throws Exception {
        HttpURLConnection connection=open(bridge.url("/api/files/7/stream"));connection.setRequestProperty("Range","bytes="+from+"-"+end);
        try{return connection.getInputStream().readAllBytes();}finally{connection.disconnect();}
    }
    @Test public void repeating277NearbyRangesReusesReceivedBytesWithout277ComputerTrips()throws Exception {
        realRangeResponses();HttpURLConnection first=open(bridge.url("/api/files/7/stream"));
        try{assertArrayEquals(movie,first.getInputStream().readAllBytes());}finally{first.disconnect();}
        for(int i=0;i<277;i++){
            int start=(i*1579)%(movie.length-513),end=start+1+i%511;
            assertArrayEquals(java.util.Arrays.copyOfRange(movie,start,end+1),readRange(start,String.valueOf(end)));
        }
        assertEquals(1,calls.get());assertEquals("Bearer test-server-secret",authorization.get());
        PlaybackBridge.Stats stats=bridge.snapshot();assertEquals(277,stats.rangeRequests);assertEquals(1,stats.upstreamVideoRequests);assertEquals(277,stats.cacheHits);
        assertEquals(movie.length,stats.videoBytesRead);
    }
    @Test public void openEndedCachedPrefixContinuesAtTheGapWithTheExactLengthAndBytes()throws Exception {
        realRangeResponses();assertArrayEquals(java.util.Arrays.copyOfRange(movie,0,32768),readRange(0,"32767"));
        HttpURLConnection next=open(bridge.url("/api/files/7/stream"));next.setRequestProperty("Range","bytes=16000-");
        try{
            assertEquals(206,next.getResponseCode());assertEquals(movie.length-16000,next.getContentLength());
            assertEquals("bytes 16000-"+(movie.length-1)+"/"+movie.length,next.getHeaderField("Content-Range"));
            assertArrayEquals(java.util.Arrays.copyOfRange(movie,16000,movie.length),next.getInputStream().readAllBytes());
        }finally{next.disconnect();}
        assertEquals(2,calls.get());assertEquals("bytes=32768-"+(movie.length-1),range.get());assertEquals(movie.length,bridge.snapshot().videoBytesRead);
        assertArrayEquals(java.util.Arrays.copyOfRange(movie,movie.length-73,movie.length),readRange(movie.length-73,""));assertEquals(2,calls.get());
        HttpURLConnection outside=open(bridge.url("/api/files/7/stream"));outside.setRequestProperty("Range","bytes="+movie.length+"-");
        try{assertEquals(416,outside.getResponseCode());assertEquals("bytes */"+movie.length,outside.getHeaderField("Content-Range"));}finally{outside.disconnect();}
        HttpURLConnection head=open(bridge.url("/api/files/7/stream"));head.setRequestMethod("HEAD");
        try{assertEquals(movie.length,head.getContentLength());assertEquals(0,head.getInputStream().readAllBytes().length);}finally{head.disconnect();}
    }
    @Test public void concurrentReadersShareOnlyThisPlaybackAndUnknownLengthRemainsStreaming()throws Exception {
        realRangeResponses();assertArrayEquals(java.util.Arrays.copyOfRange(movie,0,16384),readRange(0,"16383"));
        java.util.concurrent.ExecutorService readers=java.util.concurrent.Executors.newFixedThreadPool(4);
        try{
            java.util.List<java.util.concurrent.Future<byte[]>> results=new java.util.ArrayList<>();
            for(int i=0;i<20;i++){final int start=i*431;results.add(readers.submit(()->readRange(start,String.valueOf(start+499))));}
            for(int i=0;i<results.size();i++)assertArrayEquals(java.util.Arrays.copyOfRange(movie,i*431,i*431+500),results.get(i).get(3,java.util.concurrent.TimeUnit.SECONDS));
            assertEquals(1,calls.get());
        }finally{readers.shutdownNow();}
        bridge.close();bridge=new PlaybackBridge(upstream.url("/").toString().replaceAll("/+$",""),"test-server-secret",7);
        upstream.setDispatcher(new Dispatcher(){@Override public MockResponse dispatch(RecordedRequest request){calls.incrementAndGet();return new MockResponse().setChunkedBody(new okio.Buffer().write(movie),8192);}});
        for(int i=0;i<2;i++){HttpURLConnection unknown=open(bridge.url("/api/files/7/stream"));try{assertArrayEquals(movie,unknown.getInputStream().readAllBytes());}finally{unknown.disconnect();}}
        assertEquals(3,calls.get());assertEquals(0,bridge.snapshot().cacheHits);
    }
    @Test public void cachedResponsesDoNotDependOnTheDisconnectMonitorQueue()throws Exception {
        realRangeResponses();HttpURLConnection warm=open(bridge.url("/api/files/7/stream"));
        try{assertArrayEquals(movie,warm.getInputStream().readAllBytes());}finally{warm.disconnect();}
        java.lang.reflect.Field field=PlaybackBridge.class.getDeclaredField("disconnects");field.setAccessible(true);
        java.util.concurrent.ThreadPoolExecutor monitors=(java.util.concurrent.ThreadPoolExecutor)field.get(bridge);
        java.util.concurrent.CountDownLatch occupied=new java.util.concurrent.CountDownLatch(4),release=new java.util.concurrent.CountDownLatch(1);
        Runnable blocked=()->{occupied.countDown();try{release.await();}catch(InterruptedException ignored){Thread.currentThread().interrupt();}};
        try{
            for(int i=0;i<4;i++)monitors.execute(blocked);
            assertTrue(occupied.await(2,java.util.concurrent.TimeUnit.SECONDS));
            for(int i=0;i<8;i++)monitors.execute(blocked);
            assertArrayEquals(java.util.Arrays.copyOfRange(movie,100,200),readRange(100,"199"));
            assertEquals(1,calls.get());assertEquals(1,bridge.snapshot().rangeRequests);
        }finally{release.countDown();}
    }
    @Test public void closeRevokesListener() throws Exception {
        String url=bridge.url("/api/files/7/stream");bridge.close();
        try{open(url).getResponseCode();fail("listener must be closed");}catch(java.io.IOException expected){}
    }
}
