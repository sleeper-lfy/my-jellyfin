package net.lumen.media;

/** Relative quaternion tracking: a vertical viewing ray must not define horizontal heading. */
final class VrPoseTracker {
    private final double[] origin=new double[4],current=new double[4];
    private boolean ready;
    private double rightX,rightY;
    private float yaw,pitch;
    void reset(){ready=false;yaw=pitch=0;}
    float yaw(){return yaw;}
    float pitch(){return pitch;}
    boolean update(float[] matrix){
        if(matrix==null||matrix.length<9)return false;
        for(float value:matrix)if(!Float.isFinite(value))return false;
        quaternion(matrix,current);
        if(!ready){
            System.arraycopy(current,0,origin,0,4);
            // Use the initial horizontal viewing direction only to sign the pitch axis.
            double x=-matrix[2],y=-matrix[5],length=Math.hypot(x,y);
            if(length>.01){rightX=y/length;rightY=-x/length;}
            else{length=Math.hypot(matrix[0],matrix[3]);rightX=length>.01?matrix[0]/length:1;rightY=length>.01?matrix[3]/length:0;}
            ready=true;return true;
        }
        // q = current * inverse(origin), expressed in world axes. Android world Z is up.
        double ax=current[0],ay=current[1],az=current[2],aw=current[3];
        double bx=-origin[0],by=-origin[1],bz=-origin[2],bw=origin[3];
        double x=aw*bx+ax*bw+ay*bz-az*by,y=aw*by-ax*bz+ay*bw+az*bx;
        double z=aw*bz+ax*by-ay*bx+az*bw,w=aw*bw-ax*bx-ay*by-az*bz;
        double length=Math.hypot(z,w);
        // A twist is undefined only at an upside-down 180-degree tilt. Keep heading there.
        if(length<.01)return true;
        double tz=z/length,tw=w/length;
        yaw=VrProjection.wrap((float)-Math.toDegrees(2*Math.atan2(tz,tw)));
        // Remove world-up twist; the remaining swing yields pitch without asin's 90° fold.
        double sx=tw*x+tz*y,sy=tw*y-tz*x,sw=tw*w+tz*z;
        pitch=VrProjection.wrap((float)Math.toDegrees(2*Math.atan2(sx*rightX+sy*rightY,sw)));
        return true;
    }
    private static void quaternion(float[] m,double[] q){
        double trace=m[0]+m[4]+m[8],s;
        if(trace>0){s=Math.sqrt(trace+1)*2;q[3]=s/4;q[0]=(m[7]-m[5])/s;q[1]=(m[2]-m[6])/s;q[2]=(m[3]-m[1])/s;}
        else if(m[0]>m[4]&&m[0]>m[8]){s=Math.sqrt(1+m[0]-m[4]-m[8])*2;q[3]=(m[7]-m[5])/s;q[0]=s/4;q[1]=(m[1]+m[3])/s;q[2]=(m[2]+m[6])/s;}
        else if(m[4]>m[8]){s=Math.sqrt(1+m[4]-m[0]-m[8])*2;q[3]=(m[2]-m[6])/s;q[0]=(m[1]+m[3])/s;q[1]=s/4;q[2]=(m[5]+m[7])/s;}
        else{s=Math.sqrt(1+m[8]-m[0]-m[4])*2;q[3]=(m[3]-m[1])/s;q[0]=(m[2]+m[6])/s;q[1]=(m[5]+m[7])/s;q[2]=s/4;}
    }
}
