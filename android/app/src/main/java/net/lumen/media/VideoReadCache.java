package net.lumen.media;

import java.util.LinkedHashMap;

/** A single playback's received bytes, bounded even for sparse one-byte reads. */
final class VideoReadCache {
    static final int BLOCK_SIZE=64*1024, MAX_BYTES=16*1024*1024;
    private static final int MAX_BLOCKS=MAX_BYTES/BLOCK_SIZE;
    private static final class Block {
        final byte[] bytes=new byte[BLOCK_SIZE];
        int from=BLOCK_SIZE,to;
    }
    private final LinkedHashMap<Long,Block> blocks=new LinkedHashMap<>(16,.75f,true);
    private boolean closed;
    synchronized void put(long offset,byte[] input,int count) {
        if(closed)return;
        int consumed=0;
        while(consumed<count) {
            long key=offset/BLOCK_SIZE;int within=(int)(offset%BLOCK_SIZE),length=Math.min(count-consumed,BLOCK_SIZE-within);
            Block block=blocks.get(key);
            if(block==null){block=new Block();blocks.put(key,block);}
            // One contiguous interval per block: never mark an unread gap as data.
            if(within>block.to||within+length<block.from){block.from=within;block.to=within+length;}
            else {block.from=Math.min(block.from,within);block.to=Math.max(block.to,within+length);}
            System.arraycopy(input,consumed,block.bytes,within,length);
            if(blocks.size()>MAX_BLOCKS){Long oldest=blocks.keySet().iterator().next();blocks.remove(oldest);}
            consumed+=length;offset+=length;
        }
    }
    synchronized int read(long offset,byte[] output,int maximum) {
        Block block=blocks.get(offset/BLOCK_SIZE);if(block==null)return 0;
        int within=(int)(offset%BLOCK_SIZE);if(within<block.from||within>=block.to)return 0;
        int length=Math.min(maximum,block.to-within);System.arraycopy(block.bytes,within,output,0,length);return length;
    }
    synchronized int allocatedBytes(){return blocks.size()*BLOCK_SIZE;}
    synchronized void clear(){blocks.clear();}
    synchronized void close(){closed=true;blocks.clear();}
}
