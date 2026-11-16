package net.lumen.media;

import android.content.Context;
import org.json.JSONObject;

/** Identical season/episode labels in details and the in-player picker. */
final class EpisodeLabels {
    static int season(JSONObject file){return file.optInt("season",1);}
    static String season(Context context,int value){return value==-1?context.getString(R.string.episode_all_seasons):value==0?context.getString(R.string.episode_specials):context.getString(R.string.episode_season,value);}
    static String file(Context context,JSONObject file,boolean series,int index){
        String name=file.optString("name","");if(name.isEmpty())name=context.getString(R.string.episode_file_number,index);
        return series&&!file.isNull("season")&&!file.isNull("episode")?context.getString(R.string.episode_number_label,file.optInt("season"),file.optInt("episode"),name):name;
    }
}
