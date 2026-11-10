package net.lumen.media;
import org.junit.Test;
import static org.junit.Assert.*;
public class HoldSpeedTest {
    static final class Fake implements HoldSpeed.Decoder {float value;boolean reject;int writes;Fake(float value){this.value=value;}public float rate(){return value;}public boolean rate(float next){writes++;if(reject)return false;value=next;return true;}}
    @Test public void restoresTheActualSelectedRateAndCancelIsIdempotent(){
        for(float selected:new float[]{.75f,1,1.25f,1.5f,2,3}){HoldSpeed hold=new HoldSpeed();Fake decoder=new Fake(selected);assertTrue(hold.begin(decoder));assertEquals(Math.max(2,selected),decoder.value,0);assertTrue(hold.active());assertTrue(hold.end());assertEquals(selected,decoder.value,0);assertTrue(hold.end());assertEquals(2,decoder.writes);}
    }
    @Test public void replacementRestoresTheOldDecoderBeforeStartingAnother(){HoldSpeed hold=new HoldSpeed();Fake first=new Fake(1.5f),second=new Fake(1);hold.begin(first);hold.begin(second);assertEquals(1.5f,first.value,0);assertEquals(2,second.value,0);hold.end();assertEquals(1,second.value,0);}
    @Test public void rejectedAndInvalidRatesNeverEnterHold(){HoldSpeed hold=new HoldSpeed();Fake decoder=new Fake(1);decoder.reject=true;assertFalse(hold.begin(decoder));assertFalse(hold.active());for(float invalid:new float[]{0,-1,Float.NaN,Float.POSITIVE_INFINITY}){Fake broken=new Fake(invalid);assertFalse(hold.begin(broken));assertEquals(0,broken.writes);}}
    @Test public void restorationFailureIsReportedAndDoesNotKeepAReleasedDecoder(){HoldSpeed hold=new HoldSpeed();Fake decoder=new Fake(1.5f);hold.begin(decoder);decoder.reject=true;assertFalse(hold.end());assertFalse(hold.active());}
}
