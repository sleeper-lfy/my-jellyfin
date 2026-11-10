package net.lumen.media;

import org.junit.Test;
import static org.junit.Assert.*;

public class VideoReadCacheTest {
    @Test public void sparseReadsNeverInventBytesBetweenReceivedIntervals(){
        VideoReadCache cache=new VideoReadCache();byte[] received={1,2,3,4},out=new byte[8];
        cache.put(100,received,4);assertEquals(0,cache.read(99,out,8));assertEquals(4,cache.read(100,out,8));
        assertArrayEquals(new byte[]{1,2,3,4,0,0,0,0},out);assertEquals(0,cache.read(104,out,8));
        cache.put(120,received,4);assertEquals(0,cache.read(110,out,8));assertEquals(4,cache.read(120,out,8));
        cache.put(124,received,4);assertEquals(8,cache.read(120,out,8));
    }
    @Test public void sparseOneByteRequestsStayBoundedAndCloseRevokesTheCache(){
        VideoReadCache cache=new VideoReadCache();byte[] one={7},out={0};
        for(int i=0;i<1000;i++)cache.put((long)i*VideoReadCache.BLOCK_SIZE,one,1);
        assertEquals(VideoReadCache.MAX_BYTES,cache.allocatedBytes());assertEquals(0,cache.read(0,out,1));
        assertEquals(1,cache.read(999L*VideoReadCache.BLOCK_SIZE,out,1));assertEquals(7,out[0]);
        cache.close();assertEquals(0,cache.allocatedBytes());cache.put(0,one,1);assertEquals(0,cache.allocatedBytes());
    }
}
