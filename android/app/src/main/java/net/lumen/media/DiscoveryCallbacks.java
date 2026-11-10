package net.lumen.media;

/** User intent only. No Compose component constructs HTTP requests or mutates page state. */
public interface DiscoveryCallbacks {
    void onQueryChanged(String value);
    void onSubmitSearch(String value);
    void onSelectSuggestion(String group,String value);
    void onOpenFilters();
    void onApplyFilters(DiscoveryFilters filters);
    void onSelectSort(String field);
    void onRemoveChip(String id,String value);
    void onClearFilters();
    void onOpenMovie(long id);
    void onToggleFavorite(long id);
    void onLoadMore();
    void onRefresh();
    void onNavigatePrimary(String page);
    void onListAction(String action);
    void onRefreshProviders();
    void onScrollPosition(int firstVisibleItem,int offset);
}
