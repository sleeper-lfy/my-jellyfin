package net.lumen.media;
import org.junit.Test;
import static org.junit.Assert.*;

public class VrMotionFilterTest {
    private float[] pose(double heading,double elevation,double roll){
        double p=Math.toRadians(90+elevation),r=Math.toRadians(-roll),h=Math.toRadians(-heading),c=Math.cos(r),s=Math.sin(r);
        double[] matrix={c,-s,0,Math.cos(p)*s,Math.cos(p)*c,-Math.sin(p),Math.sin(p)*s,Math.sin(p)*c,Math.cos(p)};float[] result=new float[9];
        for(int column=0;column<3;column++){result[column]=(float)(Math.cos(h)*matrix[column]-Math.sin(h)*matrix[3+column]);result[3+column]=(float)(Math.sin(h)*matrix[column]+Math.cos(h)*matrix[3+column]);result[6+column]=(float)matrix[6+column];}return result;
    }
    @Test public void lookingUpAndDownWorksInBothLandscapesAndPortraits(){
        for(double roll:new double[]{0,90,180,270}){
            float[] neutral=pose(0,0,roll),up=pose(10,30,roll),down=pose(-10,-30,roll);
            assertEquals(0,VrMotionFilter.elevation(neutral),.001);assertEquals(30,VrMotionFilter.elevation(up),.001);assertEquals(-30,VrMotionFilter.elevation(down),.001);
            assertEquals(10,VrMotionFilter.heading(up),.001);assertEquals(-10,VrMotionFilter.heading(down),.001);
            VrMotionFilter filter=new VrMotionFilter();filter.configure(1,0,false);filter.update(0,0,1);filter.update(VrMotionFilter.heading(up),VrMotionFilter.elevation(up),20_000_001);
            double pitch=Math.toRadians(filter.pitch());
            for(boolean fish:new boolean[]{false,true})assertTrue(VrProjection.uv(0,Math.sin(pitch),Math.cos(pitch),fish,0,false)[1]<.5);
            filter.configure(1,0,true);filter.update(10,30,40_000_001);assertEquals(-30,filter.pitch(),.001);
        }
    }
    @Test public void sensitivityJitterWrapAndRecenterAreStable(){
        VrMotionFilter filter=new VrMotionFilter();filter.configure(.5f,0,false);filter.update(179,0,1);filter.update(-179,10,20_000_001);assertEquals(1,filter.yaw(),.001);assertEquals(5,filter.pitch(),.001);
        filter.reset();filter.update(80,20,40_000_001);assertEquals(0,filter.yaw(),0);assertEquals(0,filter.pitch(),0);
        filter.update(80.04f,20.04f,60_000_001);assertEquals(0,filter.yaw(),0);assertEquals(0,filter.pitch(),0);
        filter.update(Float.NaN,100,80_000_001);assertEquals(0,filter.yaw(),0);
    }
    @Test public void tiltingHeadUpNeverTurnsLeftOrRightInEitherLandscape(){
        for(double roll:new double[]{90,270}){
            VrMotionFilter filter=new VrMotionFilter();filter.configure(1,0,false);float[] neutral=pose(35,0,roll);filter.update(VrMotionFilter.heading(neutral),VrMotionFilter.elevation(neutral),1);
            long timestamp=1;
            for(int elevation=-45;elevation<=45;elevation+=5){float[] tilted=pose(35,elevation,roll);filter.update(VrMotionFilter.heading(tilted),VrMotionFilter.elevation(tilted),timestamp+=20_000_000);assertEquals("Pitch leaked into yaw at display roll "+roll,0,filter.yaw(),.001);assertEquals(elevation,filter.pitch(),.001);}
            filter.reset();filter.update(0,0,1);
            for(int heading=-45;heading<=45;heading+=5){float[] turned=pose(heading,0,roll);filter.update(VrMotionFilter.heading(turned),VrMotionFilter.elevation(turned),timestamp+=20_000_000);assertEquals("Yaw leaked into pitch",0,filter.pitch(),.001);}
        }
    }
    @Test public void smoothingDependsOnElapsedTimeRatherThanSensorFrequency(){
        VrMotionFilter slow=new VrMotionFilter(),fast=new VrMotionFilter();slow.configure(1,100,false);fast.configure(1,100,false);slow.update(0,0,1);fast.update(0,0,1);
        for(int i=1;i<=10;i++)slow.update(30,20,1+i*20_000_000L);
        for(int i=1;i<=20;i++)fast.update(30,20,1+i*10_000_000L);
        assertEquals(slow.yaw(),fast.yaw(),.01);assertEquals(slow.pitch(),fast.pitch(),.01);assertTrue(slow.yaw()>20&&slow.yaw()<30);
    }
}
