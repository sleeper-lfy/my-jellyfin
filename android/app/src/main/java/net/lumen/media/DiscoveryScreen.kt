package net.lumen.media

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.text.style.TextOverflow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.filter
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import net.lumen.media.ui.components.AppTopBar
import net.lumen.media.ui.components.AppScreenScaffold
import net.lumen.media.ui.components.AppBottomNavigation
import net.lumen.media.ui.components.AppDestination
import net.lumen.media.ui.components.AppIcons
import net.lumen.media.ui.theme.LocalAppSpacing

/** Official Material components, with all business state hoisted into the Java coordinator. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun DiscoveryScreen(
    state: DiscoveryUiState,
    callbacks: DiscoveryCallbacks,
    loader: DiscoveryImageLoader? = null,
    active: Boolean = true,
    imageEpoch: Int = 0,
    snackbarHostState: SnackbarHostState = remember { SnackbarHostState() },
    previewPainter: Painter? = null,
) {
    var searchActive by rememberSaveable { mutableStateOf(false) }
    val scrollBehavior = TopAppBarDefaults.enterAlwaysScrollBehavior(canScroll = { !searchActive })
    val searchVisible by remember { derivedStateOf { searchActive || scrollBehavior.state.collapsedFraction < .5f } }
    val grid = rememberLazyGridState(state.initialScrollIndex, state.initialScrollOffset)
    var filtersVisible by rememberSaveable { mutableStateOf(false) }
    var moreExpanded by rememberSaveable { mutableStateOf(false) }
    var sourceDetailsVisible by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(searchActive) { if (searchActive) scrollBehavior.state.heightOffset = 0f }
    LaunchedEffect(active, state.restoringScroll, state.initialScrollIndex, state.initialScrollOffset,
        state.items.size, state.loading, state.loadingMore) {
        val target = state.initialScrollIndex.coerceAtMost((state.total - 1).coerceAtLeast(0))
        if (active && state.restoringScroll && state.items.size > target && !state.loading && !state.loadingMore) {
            grid.scrollToItem(target, state.initialScrollOffset)
        }
    }
    LaunchedEffect(active, grid) {
        if (active) snapshotFlow { grid.firstVisibleItemIndex to grid.firstVisibleItemScrollOffset }
            .distinctUntilChanged().collect { (index, offset) -> callbacks.onScrollPosition(index, offset) }
    }
    LaunchedEffect(active, state.hasMore, state.loading, state.loadingMore, state.items.size, state.error) {
        if (active && state.hasMore && !state.loading && !state.loadingMore && state.items.isNotEmpty() && state.error.isBlank()) {
            snapshotFlow { (grid.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: -1) >= state.items.size - 4 }
                .distinctUntilChanged().filter { it }.collect { callbacks.onLoadMore() }
        }
    }
    LaunchedEffect(active) { if (!active) { filtersVisible = false; moreExpanded = false; sourceDetailsVisible = false } }
    AppScreenScaffold(
        modifier = Modifier.fillMaxSize(), scrollBehavior = scrollBehavior,
        topBar = {
            AppTopBar(
                title = stringResource(R.string.discovery_title),
                actions = {
                    IconButton(onClick = { moreExpanded = true }) { Icon(AppIcons.More, stringResource(R.string.discovery_more_action)) }
                    DropdownMenu(moreExpanded, onDismissRequest = { moreExpanded = false }) {
                        listOf("save" to R.string.discovery_more_save_list, "shuffle" to R.string.discovery_more_shuffle,
                            "queue" to R.string.discovery_more_phone_queue).forEach { (action, label) ->
                            DropdownMenuItem(text = { Text(stringResource(label)) },
                                onClick = { moreExpanded = false; callbacks.onListAction(action) })
                        }
                    }
                },
                modifier = Modifier.testTag("discoveryTopBar"),
                scrollBehavior = scrollBehavior,
            )
        },
        bottomBar = { DiscoveryNavigation(callbacks::onNavigatePrimary) },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) {
        Column(Modifier.fillMaxSize()) {
            AnimatedVisibility(searchVisible, enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
                DiscoveryComposeSearchBar(state, callbacks, active,
                    onFilters = { callbacks.onOpenFilters(); filtersVisible = true },
                    modifier = Modifier.padding(horizontal = LocalAppSpacing.current.page),
                    onSearchActiveChanged = { searchActive = it })
            }
            DiscoverySourceTabs(state, callbacks, active)
            DiscoveryFilterChipRow(state.chips, callbacks::onRemoveChip, callbacks::onClearFilters,
                Modifier.padding(horizontal = LocalAppSpacing.current.page))
            Row(Modifier.fillMaxWidth().padding(horizontal = LocalAppSpacing.current.page),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween) {
                Text(stringResource(R.string.discovery_results_count, state.total),
                    style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                DiscoverySortMenu(state.sortField, state.descending, callbacks::onSelectSort)
            }
            if (state.statusMessage.isNotBlank()) Text(state.statusMessage,
                Modifier.padding(horizontal = LocalAppSpacing.current.page),
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (state.statusError.isNotBlank()) TextButton(
                onClick = { sourceDetailsVisible = true }, modifier = Modifier.padding(horizontal = LocalAppSpacing.current.sm)) {
                Text(stringResource(R.string.discovery_source_error_details), style = MaterialTheme.typography.labelLarge)
            }
            PullToRefreshBox(isRefreshing = state.refreshing, onRefresh = callbacks::onRefresh,
                modifier = Modifier.weight(1f)) {
                DiscoveryMovieGrid(state, callbacks, loader, active, imageEpoch, grid,
                    previewPainter = previewPainter)
            }
        }
    }
    if (filtersVisible && active) DiscoveryFilterBottomSheet(state, callbacks) { filtersVisible = false }
    if (sourceDetailsVisible && active) AlertDialog(
        onDismissRequest = { sourceDetailsVisible = false },
        title = { Text(stringResource(R.string.discovery_source_details_title)) },
        text = { Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(LocalAppSpacing.current.sm)) {
            if (state.statusMessage.isNotBlank()) Text(state.statusMessage)
            Text(state.statusError)
        } },
        confirmButton = { TextButton(enabled = !state.busy,
            onClick = { sourceDetailsVisible = false; callbacks.onListAction("retry") }) {
            Text(stringResource(R.string.discovery_source_retry))
        } },
        dismissButton = { TextButton(onClick = { sourceDetailsVisible = false }) { Text(stringResource(R.string.discovery_close)) } },
    )
}

@Composable
private fun DiscoveryNavigation(onNavigate: (String) -> Unit) {
    AppBottomNavigation(AppDestination.Discover, { onNavigate(it.id) },
        modifier = Modifier.testTag("discoveryNavigation"))
}

/** Source selection is a page-level destination choice, separate from the filter draft. */
@Composable
private fun DiscoverySourceTabs(state: DiscoveryUiState, callbacks: DiscoveryCallbacks, active: Boolean) {
    val selected = if (state.online) 1 else 0
    TabRow(selectedTabIndex = selected, containerColor = MaterialTheme.colorScheme.surface,
        contentColor = MaterialTheme.colorScheme.primary,
        modifier = Modifier.padding(horizontal = LocalAppSpacing.current.page),
        divider = { androidx.compose.material3.HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant) }) {
        listOf(R.string.discovery_filter_local, R.string.discovery_filter_online).forEachIndexed { index, label ->
            Tab(selected = index == selected, enabled = active,
                onClick = { if (index != selected) callbacks.onApplyFilters(state.filters.copy().also { it.online = index == 1 }) },
                text = { Text(stringResource(label), style = if (index == selected) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodyMedium) },
                selectedContentColor = MaterialTheme.colorScheme.onSurface,
                unselectedContentColor = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.testTag("discoveryScope:$index"))
        }
    }
}

@Preview(name = "Discovery · Light", showBackground = true, widthDp = 393, heightDp = 852)
@Composable
private fun DiscoveryLightPreview() {
    DiscoveryTheme(false) { DiscoveryScreen(discoveryPreviewState(), PreviewDiscoveryCallbacks,
        previewPainter = painterResource(R.drawable.discovery_preview_coast)) }
}

@Preview(name = "Discovery · Dark", showBackground = true, widthDp = 393, heightDp = 852)
@Composable
private fun DiscoveryDarkPreview() {
    DiscoveryTheme(true) { DiscoveryScreen(discoveryPreviewState(), PreviewDiscoveryCallbacks,
        previewPainter = painterResource(R.drawable.discovery_preview_coast)) }
}
