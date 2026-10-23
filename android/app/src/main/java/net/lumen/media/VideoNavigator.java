package net.lumen.media;

import org.json.JSONArray;
import org.json.JSONObject;
import java.util.function.BooleanSupplier;

/** Locate a neighbour in the current server list without retaining a whole media library. */
final class VideoNavigator {
    static final class Target {final long id;final int position;Target(long id,int position){this.id=id;this.position=position;}}
    static Target adjacent(Api api,long current,int direction,String path,int hint,BooleanSupplier cancelled)throws Exception{
        if(direction!=1&&direction!=-1)throw new IllegalArgumentException("Invalid navigation direction");
        if(!(path.startsWith("/api/works?")||path.startsWith("/api/recommendations?")))throw new IllegalArgumentException("Invalid media list");
        if(hint>=0){
            int offset=Math.max(0,hint-1);JSONArray rows=api.get(path+"&offset="+offset+"&limit=3").getJSONArray("items");
            if(cancelled.getAsBoolean())return null;
            for(int i=0;i<rows.length();i++)if(rows.getJSONObject(i).optLong("id")==current){
                int next=i+direction;if(next>=0&&next<rows.length()&&playable(rows.getJSONObject(next)))return new Target(rows.getJSONObject(next).getLong("id"),offset+next);
            }
        }
        Target previous=null;boolean found=false;int offset=0;
        while(!cancelled.getAsBoolean()){
            JSONObject page=api.get(path+"&offset="+offset+"&limit=100");JSONArray rows=page.getJSONArray("items");
            if(cancelled.getAsBoolean())return null;
            for(int i=0;i<rows.length();i++){
                JSONObject row=rows.getJSONObject(i);long id=row.optLong("id");
                if(id==current){if(direction<0)return previous;found=true;}
                else if(playable(row)){Target candidate=new Target(id,offset+i);if(found)return candidate;previous=candidate;}
            }
            offset+=rows.length();if(rows.length()==0||offset>=page.optInt("total",offset))return null;
        }
        return null;
    }
    private static boolean playable(JSONObject row){return row.optLong("id")>0&&row.optInt("file_count",1)>0;}
}
