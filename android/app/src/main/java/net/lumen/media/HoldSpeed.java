package net.lumen.media;

/** A temporary rate belongs to one decoder instance and never changes saved preferences. */
final class HoldSpeed {
    interface Decoder {float rate();boolean rate(float value);}
    private Decoder decoder;
    private float original=1,temporary=1;
    boolean begin(Decoder target){
        end();float value=target.rate();if(!Float.isFinite(value)||value<=0)return false;
        float next=Math.max(2,value);if(!target.rate(next))return false;
        decoder=target;original=value;temporary=next;return true;
    }
    boolean active(){return decoder!=null;}
    float original(){return original;}
    float temporary(){return temporary;}
    boolean end(){
        Decoder target=decoder;decoder=null;
        if(target==null)return true;
        try{return target.rate(original);}catch(IllegalStateException ignored){return false;}
    }
}
