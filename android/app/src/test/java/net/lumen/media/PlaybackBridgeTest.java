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
    @Test public void closeRevokesListener() throws Exception {
        String url=bridge.url("/api/files/7/stream");bridge.close();
        try{open(url).getResponseCode();fail("listener must be closed");}catch(java.io.IOException expected){}
    }
}
