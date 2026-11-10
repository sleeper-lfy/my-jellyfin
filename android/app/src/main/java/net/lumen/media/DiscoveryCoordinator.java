package net.lumen.media;

import java.util.*;
import org.json.*;
import android.view.View;

/** Discovery data coordination. Compose receives immutable snapshots and emits intents. */
final class DiscoveryCoordinator implements DiscoveryCallbacks {
    private final MainActivity page;
    private final DiscoveryComposeHost host;
    private DiscoveryUiState latest=DiscoveryUiState.empty();
    private final List<Long> ordered=new ArrayList<>();
    private final Map<Long,Boolean> favorites=new HashMap<>();
    private final List<DiscoveryUiState.Suggestion> suggestions=new ArrayList<>();
    private JSONObject facets=new JSONObject();
    private String queryText,error="",suggestionQuery="",providerError="";
    private int total,revision,suggestionVersion,pageGeneration,providerGeneration;
    private boolean active=true,loading,refreshing,providerLoading,disposed,restoring;
    private final int restoreIndex,restorePixel;
    private Runnable delayedSuggestion,providerReady;
    private static final Set<String> SORTS=new HashSet<>(Arrays.asList("discovered","site_added","title","year","community_rating"));

    DiscoveryCoordinator(MainActivity page){this.page=page;queryText=page.query;restoreIndex=page.discoveryGridIndex;restorePixel=page.discoveryGridScroll;restoring=page.discoveryRestoreScroll;host=new DiscoveryComposeHost(page,page.api,page.imageRequests,this);}
    View getView(){return host.getView();}
    DiscoveryUiState snapshot(){return latest;}
    void start(){
        publish();loadOptions();if(page.discoveryOnline)ensureProviders(null);
        if(!(page.discoveryOnline&&page.discoveryResultIds==null))loadPage();
    }
    void setActive(boolean value){
        if(disposed)return;boolean reactivating=value&&!active;active=value;
        // A cached discovery view may have missed a configuration dispatch while a native detail was attached.
        if(reactivating)host.getView().dispatchConfigurationChanged(page.getResources().getConfiguration());host.setActive(value);
        if(!value){cancelSuggestion();providerReady=null;suggestions.clear();suggestionVersion++;return;}
        if(loading&&pageGeneration!=page.generation){loading=false;loadPage();}
        if(providerLoading&&providerGeneration!=page.generation){providerLoading=false;if(page.discoveryOnline)ensureProviders(null);}
        publish();
    }
    void dispose(){disposed=true;active=false;cancelSuggestion();providerReady=null;host.dispose();}
    void message(String text){if(!disposed)host.showSnackbar(text);}
    private String text(int id,Object... args){return page.getString(id,args);}
    private boolean current(){return !disposed&&page.discoveryCoordinator==this&&page.discovery&&page.detailId==0;}
    void publish(){
        if(disposed)return;DiscoveryUiState.Builder state=new DiscoveryUiState.Builder();state.query=queryText;state.suggestionQuery=suggestionQuery;state.suggestions.addAll(suggestions);
        for(long id:ordered){JSONObject work=page.browseRecords.get(id);if(work==null)continue;JSONObject displayed=work;if(favorites.containsKey(id))try{displayed=new JSONObject(work.toString()).put("favorite",favorites.get(id)?1:0);}catch(JSONException ignored){}state.items.add(new DiscoveryUiState.Work(displayed,favorites.containsKey(id)));}
        state.chips=chips();state.total=total;state.loading=loading&&ordered.isEmpty();state.refreshing=refreshing;state.loadingMore=loading&&!ordered.isEmpty()&&!refreshing;state.hasMore=page.offset<total;state.error=error;
        state.sortField=page.discoverySort;state.descending=page.discoveryDescending;state.online=page.discoveryOnline;state.busy=page.discoverySearchBusy();state.statusError=page.discoverySearchErrors;
        if(page.discoveryOnline){List<String> identity=new ArrayList<>();identity.add(text(R.string.discovery_controller_source));if(!page.query.isEmpty())identity.add(page.query);if(!page.tagFilter.isEmpty())identity.add(text(R.string.discovery_controller_source_tag,page.tagFilter));state.statusMessage=android.text.TextUtils.join(" · ",identity)+(page.discoverySearchMessage.isEmpty()?"":"\n"+page.discoverySearchMessage);}
        state.filters=page.discoveryFilterState();state.facets=facets;state.providers=page.discoveryProviders;state.providerLoading=providerLoading;state.providerError=providerError;state.restoringScroll=restoring;state.initialScrollIndex=restoring?restoreIndex:page.discoveryGridIndex;state.initialScrollOffset=restoring?restorePixel:page.discoveryGridScroll;latest=state.build();host.update(latest);
    }
    private List<DiscoveryUiState.Chip> chips(){
        List<DiscoveryUiState.Chip> result=new ArrayList<>();String tag=page.discoveryOnline?page.discoveryResultTag:page.tagFilter;
        if(!page.discoveryOnline&&!page.query.isEmpty())result.add(new DiscoveryUiState.Chip("query",page.query,text(R.string.discovery_controller_title_chip,page.query)));
        if(!tag.isEmpty())result.add(new DiscoveryUiState.Chip("tag",tag,text(R.string.discovery_controller_tag_chip,tag)));
        if(!page.actorFilter.isEmpty())result.add(new DiscoveryUiState.Chip("actor",page.actorFilter,text(R.string.discovery_controller_actor_chip,page.actorFilter)));
        if(!page.yearMinFilter.isEmpty()||!page.yearMaxFilter.isEmpty())result.add(new DiscoveryUiState.Chip("year","",text(R.string.discovery_controller_year_chip,page.yearMinFilter,page.yearMaxFilter)));
        if(!page.ratingMinFilter.isEmpty())result.add(new DiscoveryUiState.Chip("rating",page.ratingMinFilter,text(R.string.discovery_controller_rating_chip,page.ratingMinFilter)));
        for(String[] group:new String[][]{{"all",page.tagsAllFilter},{"any",page.tagsAnyFilter},{"not",page.tagsNotFilter}})for(String value:tokens(group[1])){int label=group[0].equals("all")?R.string.discovery_controller_all_chip:group[0].equals("any")?R.string.discovery_controller_any_chip:R.string.discovery_controller_not_chip;result.add(new DiscoveryUiState.Chip(group[0],value,text(label,value)));}
        if(!page.watchFilter.isEmpty())result.add(new DiscoveryUiState.Chip("watch",page.watchFilter,text(page.watchFilter.equals("completed")?R.string.discovery_controller_completed:page.watchFilter.equals("progress")?R.string.discovery_controller_progress:R.string.discovery_controller_unwatched)));
        if(page.favorites)result.add(new DiscoveryUiState.Chip("favorite","",text(R.string.discovery_controller_favorite_chip)));if(page.watchlistOnly)result.add(new DiscoveryUiState.Chip("wanted","",text(R.string.discovery_controller_wanted_chip)));if(page.dislikedOnly)result.add(new DiscoveryUiState.Chip("disliked","",text(R.string.discovery_controller_disliked_chip)));if(!page.savedList.isEmpty())result.add(new DiscoveryUiState.Chip("list",page.savedList,text(R.string.discovery_controller_list_chip,page.savedList)));return result;
    }
    private LinkedHashSet<String> tokens(String raw){LinkedHashSet<String> selected=new LinkedHashSet<>();for(String value:raw.replace('，',',').split(","))if(!value.trim().isEmpty())selected.add(value.trim());return selected;}
    private void cancelSuggestion(){if(delayedSuggestion!=null){page.downloadUpdates.removeCallbacks(delayedSuggestion);delayedSuggestion=null;}}
    @Override public void onQueryChanged(String value){if(!active||!current())return;queryText=value;cancelSuggestion();suggestions.clear();suggestionQuery=value;int version=++suggestionVersion;publish();if(value.trim().isEmpty())return;delayedSuggestion=()->requestSuggestions(value,version);page.downloadUpdates.postDelayed(delayedSuggestion,300);}
    private void requestSuggestions(String value,int version){
        if(!active||!current()||version!=suggestionVersion)return;
        page.request(()->page.api.get("/api/discover?offset=0&limit=3&q="+android.net.Uri.encode(value)+"&kind="+android.net.Uri.encode(page.kind)),reply->{
            if(!active||!current()||version!=suggestionVersion)return;suggestions.clear();JSONArray values=reply.optJSONArray("items");LinkedHashSet<String> names=new LinkedHashSet<>();names.add(value);if(values!=null)for(int i=0;i<values.length()&&names.size()<2;i++){JSONObject item=values.optJSONObject(i);if(item!=null&&!item.optString("title").isEmpty())names.add(item.optString("title"));}for(String name:names)suggestions.add(new DiscoveryUiState.Suggestion("title",name));
            JSONArray tags=facets.optJSONArray("tags");int count=0;if(tags!=null)for(int i=0;i<tags.length()&&count<3;i++){String tag=tags.optString(i);if(tag.toLowerCase(Locale.ROOT).contains(value.toLowerCase(Locale.ROOT))){suggestions.add(new DiscoveryUiState.Suggestion("tag",tag));count++;}}if(count==0)suggestions.add(new DiscoveryUiState.Suggestion("tag",value));publish();
        },failure->{if(active&&current()&&version==suggestionVersion){suggestions.clear();suggestions.add(new DiscoveryUiState.Suggestion("title",value));suggestions.add(new DiscoveryUiState.Suggestion("tag",value));publish();}});
    }
    private boolean guardBusy(){if(page.discoveryOnline&&page.discoverySearchBusy()){message(text(R.string.discovery_controller_busy));return true;}return false;}
    @Override public void onSubmitSearch(String value){if(!active||!current())return;if(guardBusy())return;cancelSuggestion();suggestions.clear();suggestionVersion++;queryText=value.trim();page.query=queryText;if(page.discoveryOnline)ensureProviders(()->page.startDiscoverySearch(null));else page.showLibrary();}
    @Override public void onSelectSuggestion(String group,String value){if(!active||!current())return;if(guardBusy())return;if(!group.equals("tag")){onSubmitSearch(value);return;}cancelSuggestion();suggestionVersion++;suggestions.clear();queryText="";page.query="";page.tagFilter=value;if(page.discoveryOnline)ensureProviders(()->page.startDiscoverySearch(null));else page.showLibrary();}
    private void loadOptions(){page.request(()->page.api.get("/api/filters?discover=true&kind="+android.net.Uri.encode(page.kind)),reply->{facets=reply;publish();},failure->message(text(R.string.discovery_controller_filter_error,failure)));}
    private void ensureProviders(Runnable ready){
        if(page.discoveryProvidersLoaded){if(ready!=null)ready.run();return;}if(ready!=null)providerReady=ready;if(providerLoading)return;providerLoading=true;providerError="";providerGeneration=page.generation;publish();
        page.request(()->page.api.get("/api/discovery/providers"),reply->{providerLoading=false;page.discoveryProviders=reply.optJSONArray("items");if(page.discoveryProviders==null)page.discoveryProviders=new JSONArray();page.discoveryProvidersLoaded=true;publish();Runnable action=providerReady;providerReady=null;if(action!=null&&active&&current())action.run();},failure->{providerLoading=false;providerError=failure;providerReady=null;publish();message(text(R.string.discovery_controller_source_error,failure));});
    }
    void startSearchWhenReady(){ensureProviders(()->page.startDiscoverySearch(null));}
    @Override public void onOpenFilters(){if(!active||!current())return;cancelSuggestion();suggestions.clear();suggestionVersion++;loadOptions();ensureProviders(null);publish();}
    @Override public void onApplyFilters(DiscoveryFilters selected){if(!active||!current())return;page.applyDiscoveryFilters(selected,queryText);}
    @Override public void onRefreshProviders(){if(!active||!current())return;page.discoveryProvidersLoaded=false;ensureProviders(null);}
    @Override public void onSelectSort(String field){if(!active||!current())return;if(!SORTS.contains(field))return;if(field.equals(page.discoverySort))page.discoveryDescending=!page.discoveryDescending;page.discoverySort=field;page.saveDiscoverySort();page.showLibrary();}
    @Override public void onRemoveChip(String id,String value){if(!active||!current())return;
        switch(id){case "query":page.query="";break;case "tag":if(page.discoveryOnline)page.discoveryResultTag="";else page.tagFilter="";break;case "actor":page.actorFilter="";break;case "year":page.yearMinFilter="";page.yearMaxFilter="";break;case "rating":page.ratingMinFilter="";break;case "watch":page.watchFilter="";break;case "favorite":page.favorites=false;break;case "wanted":page.watchlistOnly=false;break;case "disliked":page.dislikedOnly=false;break;case "list":page.savedList="";break;default:LinkedHashSet<String> chosen=tokens(id.equals("all")?page.tagsAllFilter:id.equals("any")?page.tagsAnyFilter:page.tagsNotFilter);chosen.remove(value);String combined=android.text.TextUtils.join(",",chosen);if(id.equals("all"))page.tagsAllFilter=combined;else if(id.equals("any"))page.tagsAnyFilter=combined;else if(id.equals("not"))page.tagsNotFilter=combined;else return;}page.showLibrary();
    }
    @Override public void onClearFilters(){if(!active||!current())return;if(!page.discoveryOnline){page.query="";page.tagFilter="";}page.discoveryNextSearchFilters=null;page.discoveryResultTag="";page.actorFilter="";page.yearMinFilter="";page.yearMaxFilter="";page.ratingMinFilter="";page.tagsAllFilter="";page.tagsAnyFilter="";page.tagsNotFilter="";page.watchFilter="";page.savedList="";page.favorites=false;page.watchlistOnly=false;page.dislikedOnly=false;page.showLibrary();}
    @Override public void onOpenMovie(long id){if(!active||!current())return;page.openDetail(id);}
    @Override public void onNavigatePrimary(String name){if(!active||!current())return;page.navigatePrimary(name);}
    @Override public void onListAction(String action){if(!active||!current())return;if(action.equals("save"))page.saveSmartList();else if(action.equals("shuffle"))page.shuffle();else if(action.equals("queue"))page.queueEditor();else if(action.equals("retry"))page.startDiscoverySearch(null);}
    @Override public void onScrollPosition(int index,int offset){if(!active||!current())return;boolean completed=false;if(restoring){int target=Math.min(restoreIndex,Math.max(0,total-1));if(total==0||loading||page.restoreOffset>0||page.offset<=target||index/2!=target/2)return;restoring=false;completed=true;}page.discoveryGridIndex=Math.max(0,index);page.discoveryGridScroll=Math.max(0,offset);if(completed)publish();}
    @Override public void onLoadMore(){if(active&&current()&&!loading&&page.offset<total)loadPage();}
    @Override public void onRefresh(){if(!active||!current()||loading)return;page.offset=0;refreshing=true;error="";loadPage();}
    void loadPage(){
        if(!active||!current()||loading)return;loading=true;error="";final int offset=page.offset,version=revision;pageGeneration=page.generation;final String path=page.listPath();publish();
        page.request(()->page.api.get(path),reply->{loading=false;if(version!=revision){loadPage();return;}JSONArray items=reply.optJSONArray("items");if(items==null)items=new JSONArray();total=reply.optInt("total");if(offset==0){ordered.clear();page.browseRecords.clear();page.browsePositions.clear();}
            for(int i=0;i<items.length();i++){JSONObject work=items.getJSONObject(i);long id=work.getLong("id");if(!page.browseRecords.containsKey(id))ordered.add(id);page.browseRecords.put(id,work);page.browsePositions.put(id,offset+i);}page.offset=offset+items.length();refreshing=false;publish();
            if(page.offset<page.restoreOffset&&page.offset<total&&items.length()>0){loadPage();return;}if(page.restoreOffset>0)page.restoreOffset=0;if(total==0){restoring=false;page.discoveryGridIndex=0;page.discoveryGridScroll=0;}publish();
        },failure->{loading=false;refreshing=false;error=failure;publish();});
    }
    void personalChanged(long id,JSONObject work){if(!ordered.contains(id))return;if((page.favorites&&work.optInt("favorite")==0)||(page.watchlistOnly&&work.optInt("watchlist")==0)||(page.dislikedOnly&&work.optInt("disliked")==0)||(!page.watchFilter.isEmpty()&&!page.watchFilter.equals(work.optString("watch_state"))))remove(id);publish();}
    private void remove(long id){if(!ordered.remove(id))return;page.offset=Math.max(0,page.offset-1);total=Math.max(0,total-1);revision++;int position=page.browsePositions.getOrDefault(id,-1);page.browsePositions.remove(id);page.browseRecords.remove(id);for(Long other:new ArrayList<>(page.browsePositions.keySet()))if(page.browsePositions.get(other)>position)page.browsePositions.put(other,page.browsePositions.get(other)-1);}
    @Override public void onToggleFavorite(long id){if(!active||!current())return;
        JSONObject work=page.browseRecords.get(id);if(work==null||favorites.containsKey(id))return;boolean value=work.optInt("favorite")!=1;favorites.put(id,value);final Api client=page.api;final long intent=page.beginPersonalWrite(client,id,"favorite");publish();
        page.network.execute(()->{try{JSONObject result=client.post("/api/works/"+id+"/personal",new JSONObject().put("favorite",value));page.runOnUiThread(()->{
            if(page.isDestroyed())return;JSONObject personal=page.confirmPersonalWrite(client,id,intent,result.optJSONObject("personal"),"favorite",value);MainActivity.copyPersonal(work,personal);
            // A refresh can replace the JSON object while the POST is in flight.
            // Update the currently displayed record, but never put a removed row back.
            JSONObject displayed=page.discoveryCoordinator==this&&!disposed?page.browseRecords.get(id):null;
            if(displayed!=null&&displayed!=work)MainActivity.copyPersonal(displayed,personal);
            favorites.remove(id);if(current()){if(displayed!=null)personalChanged(id,displayed);else publish();}
        });}catch(Exception failure){page.runOnUiThread(()->{favorites.remove(id);if(current()){publish();message(text(R.string.discovery_controller_save_error,failure.getMessage()));}});}});
    }
}
