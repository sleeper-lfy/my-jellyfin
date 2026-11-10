package net.lumen.media

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import org.json.JSONObject

/** Fictional data only; previews never connect to a server or change the user's library. */
@Composable
internal fun discoveryPreviewState(): DiscoveryUiState {
    val context = LocalContext.current
    return remember(context) {
        val names = listOf(R.string.discovery_preview_movie_one, R.string.discovery_preview_movie_two,
            R.string.discovery_preview_movie_three, R.string.discovery_preview_movie_four)
        DiscoveryUiState.Builder().apply {
            items = names.mapIndexed { index, name ->
                DiscoveryUiState.Work(JSONObject().put("id", index + 1).put("title", context.getString(name))
                    .put("kind", "movie").put("year", 2025).put("favorite", if (index == 1) 1 else 0)
                    .put("community_rating", 8.4), false)
            }
            total = items.size
            chips = listOf(DiscoveryUiState.Chip("tag", "travel", context.getString(R.string.discovery_preview_tag_two)))
        }.build()
    }
}

internal val PreviewDiscoveryCallbacks = object : DiscoveryCallbacks {
    override fun onQueryChanged(value: String) = Unit
    override fun onSubmitSearch(value: String) = Unit
    override fun onSelectSuggestion(group: String, value: String) = Unit
    override fun onOpenFilters() = Unit
    override fun onApplyFilters(filters: DiscoveryFilters) = Unit
    override fun onSelectSort(field: String) = Unit
    override fun onRemoveChip(id: String, value: String) = Unit
    override fun onClearFilters() = Unit
    override fun onOpenMovie(id: Long) = Unit
    override fun onToggleFavorite(id: Long) = Unit
    override fun onLoadMore() = Unit
    override fun onRefresh() = Unit
    override fun onNavigatePrimary(page: String) = Unit
    override fun onListAction(action: String) = Unit
    override fun onRefreshProviders() = Unit
    override fun onScrollPosition(index: Int, offset: Int) = Unit
}
