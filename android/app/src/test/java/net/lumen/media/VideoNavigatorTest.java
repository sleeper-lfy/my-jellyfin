package net.lumen.media;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.RecordedRequest;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class) @Config(sdk=33)
public class VideoNavigatorTest {
    @Test public void pagingStaleHintsAndFiltersFindNeighboursWithoutWrapping()throws Exception{
        try(MockWebServer server=new MockWebServer()){
            server.setDispatcher(new Dispatcher(){public MockResponse dispatch(RecordedRequest request){
                assertEquals("vr",request.getRequestUrl().queryParameter("kind"));assertEquals("test tag",request.getRequestUrl().queryParameter("tag"));
                int offset=Integer.parseInt(request.getRequestUrl().queryParameter("offset")),limit=Integer.parseInt(request.getRequestUrl().queryParameter("limit"));JSONArray rows=new JSONArray();
                try{for(int i=offset;i<Math.min(205,offset+limit);i++)rows.put(new JSONObject().put("id",i+1).put("file_count",i==100?0:1));}catch(Exception error){throw new AssertionError(error);}
                return new MockResponse().setBody("{\"total\":205,\"items\":"+rows+"}");}});server.start();
            Api api=new Api(new Connection(server.url("/").toString(),"abcdefghijklmnopqrstuvwxyz123456"));String path="/api/works?kind=vr&tag=test%20tag";
            VideoNavigator.Target target=VideoNavigator.adjacent(api,100,1,path,-1,()->false);assertEquals(102,target.id);assertEquals(101,target.position);
            assertEquals(100,VideoNavigator.adjacent(api,102,-1,path,40,()->false).id);
            assertEquals(151,VideoNavigator.adjacent(api,150,1,path,149,()->false).id);
            assertNull(VideoNavigator.adjacent(api,1,-1,path,-1,()->false));assertNull(VideoNavigator.adjacent(api,205,1,path,-1,()->false));
            assertNull(VideoNavigator.adjacent(api,999,1,path,-1,()->false));assertNull(VideoNavigator.adjacent(api,150,1,path,-1,()->true));
        }
    }
}
