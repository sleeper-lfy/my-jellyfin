package net.lumen.media;

import org.json.JSONObject;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;
import java.util.function.Consumer;

/** One bounded UDP discovery round. Never transmits or receives access tokens. */
final class ServerDiscovery {
    static final int PORT=8098;
    static final class Server {
        final String address,name;
        Server(String address,String name){this.address=address;this.name=name;}
        @Override public String toString(){return address+"  ·  "+name;}
    }
    static byte[] probe(String nonce){return ("LUMEN_DISCOVER_V1 "+nonce).getBytes(StandardCharsets.US_ASCII);}
    static Server parse(byte[] data,int length,InetAddress sender,String nonce)throws Exception{
        if(!(sender instanceof Inet4Address)||length>1024)return null;
        if(!sender.isSiteLocalAddress()&&!sender.isLoopbackAddress()&&!sender.isLinkLocalAddress())return null;
        JSONObject json=new JSONObject(new String(data,0,length,StandardCharsets.UTF_8));
        int port=json.optInt("port",0);
        if(!"lumen".equals(json.optString("service"))||json.optInt("api_version")!=1||!nonce.equals(json.optString("nonce"))||port<1||port>65535)return null;
        String name=json.optString("name","Lumen").replaceAll("[\\p{Cntrl}]","");
        if(name.length()>64)name=name.substring(0,64);
        return new Server("http://"+sender.getHostAddress()+":"+port,name);
    }
    static void scan(Consumer<Server> found)throws Exception{
        String nonce=UUID.randomUUID().toString().replace("-","");
        Set<InetAddress> targets=new LinkedHashSet<>();
        targets.add(InetAddress.getByName("255.255.255.255"));
        for(NetworkInterface nic:Collections.list(NetworkInterface.getNetworkInterfaces())){
            if(!nic.isUp()||nic.isLoopback())continue;
            for(java.net.InterfaceAddress address:nic.getInterfaceAddresses())if(address.getBroadcast()!=null)targets.add(address.getBroadcast());
        }
        Set<String> seen=new LinkedHashSet<>();
        try(DatagramSocket socket=new DatagramSocket()){
            socket.setBroadcast(true);socket.setSoTimeout(250);
            byte[] request=probe(nonce);
            for(InetAddress target:targets)try{socket.send(new DatagramPacket(request,request.length,target,PORT));}catch(java.io.IOException ignored){/* Other active interfaces may still work. */}
            long deadline=System.nanoTime()+3_000_000_000L;
            while(System.nanoTime()<deadline&&!Thread.currentThread().isInterrupted()){
                byte[] data=new byte[1025];DatagramPacket packet=new DatagramPacket(data,data.length);
                try{
                    socket.receive(packet);Server server=parse(data,packet.getLength(),packet.getAddress(),nonce);
                    if(server!=null&&seen.add(server.address))found.accept(server);
                }catch(SocketTimeoutException ignored){/* Bounded scan; manual entry always remains available. */}
                catch(org.json.JSONException ignored){/* Ignore unrelated LAN traffic. */}
            }
        }
    }
}
