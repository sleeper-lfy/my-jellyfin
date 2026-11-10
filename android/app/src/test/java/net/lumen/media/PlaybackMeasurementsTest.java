package net.lumen.media;

import org.junit.Test;
import static org.junit.Assert.*;

public class PlaybackMeasurementsTest {
    @Test public void firstSampleAndNewDecoderNeverReportAnInventedZeroOrHugeRate(){
        PlaybackMeasurements.Sample sample=new PlaybackMeasurements.Sample();
        sample.update(1000,5*1048576L,100,10);assertFalse(sample.ready);
        sample.update(2000,7*1048576L,130,12);assertTrue(sample.ready);
        assertEquals(2,sample.mebibytesPerSecond,0);assertEquals(30,sample.displayedPerSecond,0);assertEquals(2,sample.newlyLost);
        sample.update(3000,0,0,0);assertFalse(sample.ready);
        sample.update(4000,1048576,30,0);assertTrue(sample.ready);assertEquals(1,sample.mebibytesPerSecond,0);
    }
    @Test public void cachedVideoCanGenuinelyHaveZeroNetworkReadWhileDisplayingFrames(){
        PlaybackMeasurements.Sample sample=new PlaybackMeasurements.Sample();
        sample.update(1000,1048576,30,0);sample.update(2000,1048576,60,0);
        assertTrue(sample.ready);assertEquals(0,sample.mebibytesPerSecond,0);assertEquals(30,sample.displayedPerSecond,0);
    }
    @Test public void bufferingCountsTransitionsRatherThanEveryPercentageEvent(){
        PlaybackMeasurements measurements=new PlaybackMeasurements();
        measurements.buffering(true,100);measurements.buffering(true,200);assertEquals(1,measurements.bufferingCount);
        assertEquals(400,measurements.bufferingMs(500));measurements.buffering(false,600);measurements.buffering(false,800);
        measurements.buffering(true,1000);assertEquals(2,measurements.bufferingCount);assertEquals(700,measurements.bufferingMs(1200));
    }
    @Test public void seekIgnoresOldPositionPauseBufferingAndRequiresAdvancingTargetSamples(){
        PlaybackMeasurements measurements=new PlaybackMeasurements();
        measurements.seek(35000,30000,1000);
        measurements.progress(30000,true,1001);assertTrue(measurements.seeking());
        measurements.progress(35000,false,1100);assertTrue(measurements.seeking());
        measurements.buffering(true,1100);measurements.progress(35000,true,1200);assertTrue(measurements.seeking());
        measurements.buffering(false,1300);measurements.progress(35000,true,1400);assertTrue(measurements.seeking());
        measurements.progress(35250,true,1650);assertFalse(measurements.seeking());assertEquals(650,measurements.lastSeekMs);
        measurements.seek(10000,35250,2000);assertEquals(-1,measurements.lastSeekMs);
        measurements.progress(35250,true,2100);assertTrue(measurements.seeking());
        measurements.progress(10010,true,2200);measurements.progress(10260,true,2450);assertEquals(450,measurements.lastSeekMs);
    }
}
