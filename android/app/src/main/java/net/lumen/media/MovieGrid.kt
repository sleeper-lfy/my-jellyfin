package net.lumen.media

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyGridState
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.tooling.preview.Preview
import net.lumen.media.ui.theme.AppDimensions
import net.lumen.media.ui.theme.LocalAppSpacing

@Composable
internal fun DiscoveryMovieGrid(
    state: DiscoveryUiState,
    callbacks: DiscoveryCallbacks,
    loader: DiscoveryImageLoader?,
    active: Boolean,
    imageEpoch: Int,
    gridState: LazyGridState,
    modifier: Modifier = Modifier,
    previewPainter: Painter? = null,
) {
    LazyVerticalGrid(
        columns = GridCells.Fixed(2), state = gridState, modifier = modifier.fillMaxSize().testTag("discoveryGrid"),
        contentPadding = PaddingValues(start = LocalAppSpacing.current.page, end = LocalAppSpacing.current.page,
            top = LocalAppSpacing.current.xs, bottom = LocalAppSpacing.current.page),
        horizontalArrangement = Arrangement.spacedBy(LocalAppSpacing.current.md),
        verticalArrangement = Arrangement.spacedBy(LocalAppSpacing.current.md),
    ) {
        if (state.loading && state.items.isEmpty()) {
            items(6, key = { "loading:$it" }) { DiscoveryMovieSkeleton() }
        } else {
            items(state.items, key = { it.id }, contentType = { "movie" }) { work ->
                DiscoveryMovieCard(work, loader, active, imageEpoch, { callbacks.onOpenMovie(work.id) },
                    { callbacks.onToggleFavorite(work.id) }, previewPainter = previewPainter)
            }
            if (state.items.isEmpty()) {
                item(key = "empty", span = { GridItemSpan(maxLineSpan) }) {
                    Column(Modifier.fillMaxWidth().padding(vertical = AppDimensions.TouchTarget),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(LocalAppSpacing.current.md)) {
                        Icon(Icons.Default.Search, null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(stringResource(if (state.error.isBlank()) R.string.discovery_empty_title else R.string.discovery_load_error),
                            style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurface)
                        Text(stringResource(R.string.discovery_empty_message), style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                        if (state.error.isBlank()) Button(onClick = callbacks::onClearFilters) { Text(stringResource(R.string.discovery_empty_clear)) }
                        else Button(onClick = callbacks::onRefresh) { Text(stringResource(R.string.discovery_retry)) }
                    }
                }
            } else if (state.loadingMore) {
                item(key = "loadingMore", span = { GridItemSpan(maxLineSpan) }) {
                    Column(Modifier.fillMaxWidth().padding(LocalAppSpacing.current.page), horizontalAlignment = Alignment.CenterHorizontally) {
                        CircularProgressIndicator()
                    }
                }
            } else if (state.hasMore) {
                item(key = "loadMore", span = { GridItemSpan(maxLineSpan) }) {
                    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
                        if (state.error.isNotBlank()) Text(stringResource(R.string.discovery_load_error),
                            style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.error)
                        TextButton(onClick = callbacks::onLoadMore) {
                            Text(stringResource(if (state.error.isBlank()) R.string.discovery_load_more else R.string.discovery_retry))
                        }
                    }
                }
            }
        }
    }
}

@Preview(name = "Movie grid · Light", showBackground = true, widthDp = 393, heightDp = 600)
@Composable
private fun GridLightPreview() {
    DiscoveryTheme(false) {
        DiscoveryMovieGrid(discoveryPreviewState(), PreviewDiscoveryCallbacks, null, false, 0,
            rememberLazyGridState(), previewPainter = painterResource(R.drawable.discovery_preview_coast))
    }
}

@Preview(name = "Movie grid · Dark", showBackground = true, widthDp = 393, heightDp = 600)
@Composable
private fun GridDarkPreview() {
    DiscoveryTheme(true) {
        DiscoveryMovieGrid(discoveryPreviewState(), PreviewDiscoveryCallbacks, null, false, 0,
            rememberLazyGridState(), previewPainter = painterResource(R.drawable.discovery_preview_coast))
    }
}
