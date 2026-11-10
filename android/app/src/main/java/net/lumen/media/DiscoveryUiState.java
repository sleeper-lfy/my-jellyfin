package net.lumen.media;

import java.util.*;
import org.json.*;

/** Immutable presentation snapshots shared by the Java coordinator and Compose. */
public final class DiscoveryUiState {
    public final List<Work> items;
    public final List<Chip> chips;
    public final List<Suggestion> suggestions;
    public final String query,suggestionQuery,error,sortField,statusMessage,statusError,providerError;
    public final int total,initialScrollIndex,initialScrollOffset;
    public final boolean loading,refreshing,loadingMore,hasMore,descending,online,busy,providerLoading,restoringScroll;
    public final DiscoveryFilters filters;
    public final JSONObject facets;
    public final JSONArray providers;
    private DiscoveryUiState(Builder b){
        items=Collections.unmodifiableList(new ArrayList<>(b.items));chips=Collections.unmodifiableList(new ArrayList<>(b.chips));suggestions=Collections.unmodifiableList(new ArrayList<>(b.suggestions));
        query=b.query;suggestionQuery=b.suggestionQuery;error=b.error;sortField=b.sortField;statusMessage=b.statusMessage;statusError=b.statusError;providerError=b.providerError;total=b.total;initialScrollIndex=b.initialScrollIndex;initialScrollOffset=b.initialScrollOffset;
        loading=b.loading;refreshing=b.refreshing;loadingMore=b.loadingMore;hasMore=b.hasMore;descending=b.descending;online=b.online;busy=b.busy;providerLoading=b.providerLoading;restoringScroll=b.restoringScroll;filters=b.filters.copy();
        JSONObject copiedFacets;JSONArray copiedProviders;try{copiedFacets=new JSONObject(b.facets.toString());copiedProviders=new JSONArray(b.providers.toString());}catch(JSONException invalid){copiedFacets=new JSONObject();copiedProviders=new JSONArray();}facets=copiedFacets;providers=copiedProviders;
    }
    public static DiscoveryUiState empty(){return new Builder().build();}
    public static final class Builder {
        public List<Work> items=new ArrayList<>();public List<Chip> chips=new ArrayList<>();public List<Suggestion> suggestions=new ArrayList<>();
        public String query="",suggestionQuery="",error="",sortField="discovered",statusMessage="",statusError="",providerError="";
        public int total,initialScrollIndex,initialScrollOffset;
        public boolean loading,refreshing,loadingMore,hasMore,descending=true,online,busy,providerLoading,restoringScroll;
        public DiscoveryFilters filters=new DiscoveryFilters();public JSONObject facets=new JSONObject();public JSONArray providers=new JSONArray();
        public DiscoveryUiState build(){return new DiscoveryUiState(this);}
    }
    public static final class Work {
        public final long id;
        public final String title,cover,year,kind;
        public final Double communityRating;
        public final Integer rating;
        public final boolean favorite,pending;
        public Work(JSONObject value,boolean pending){id=value.optLong("id");title=value.optString("title");cover=value.isNull("cover")?"":value.optString("cover");year=value.isNull("year")?"":value.optString("year");kind=value.optString("kind");communityRating=value.isNull("community_rating")?null:value.optDouble("community_rating");rating=value.isNull("rating")?null:value.optInt("rating");favorite=value.optInt("favorite")==1;this.pending=pending;}
    }
    public static final class Chip {
        public final String id,value,label;
        public Chip(String id,String value,String label){this.id=id;this.value=value;this.label=label;}
    }
    public static final class Suggestion {
        public final String id,group,value;
        public Suggestion(String group,String value){this.group=group;this.value=value;id=group+":"+value;}
    }
}
