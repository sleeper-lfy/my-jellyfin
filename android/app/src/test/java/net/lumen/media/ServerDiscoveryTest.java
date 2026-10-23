package net.lumen.media;

import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=33)
public class ServerDiscoveryTest {
    @Test public void discoveryMatchesNonceAndUsesPacketSourceInsteadOfAdvertisedHost()throws Exception{
        String nonce="a".repeat(32);
        assertEquals("LUMEN_DISCOVER_V1 "+nonce,new String(ServerDiscovery.probe(nonce),StandardCharsets.US_ASCII));
        JSONObject response=new JSONObject().put("service","lumen").put("api_version",1).put("port",18097).put("nonce",nonce).put("name","Media PC").put("host","attacker.example");
        byte[] data=response.toString().getBytes(StandardCharsets.UTF_8);
        ServerDiscovery.Server server=ServerDiscovery.parse(data,data.length,InetAddress.getByName("192.168.1.30"),nonce);
        assertNotNull(server);assertEquals("http://192.168.1.30:18097",server.address);assertEquals("Media PC",server.name);
        assertNull(ServerDiscovery.parse(data,data.length,InetAddress.getByName("192.168.1.30"),"b".repeat(32)));
        assertNull(ServerDiscovery.parse(data,data.length,InetAddress.getByName("8.8.8.8"),nonce));
        response.put("port",70000);data=response.toString().getBytes(StandardCharsets.UTF_8);
        assertNull(ServerDiscovery.parse(data,data.length,InetAddress.getByName("192.168.1.30"),nonce));
    }
}
