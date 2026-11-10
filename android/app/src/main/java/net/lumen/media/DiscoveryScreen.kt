package net.lumen.media

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
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
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.text.style.TextOverflow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.filter

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
    Scaffold(
        modifier = Modifier.fillMaxSize().nestedScroll(scrollBehavior.nestedScrollConnection),
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.discovery_title), style = MaterialTheme.typography.titleLarge) },
                actions = {
                    IconButton(onClick = { moreExpanded = true }) { Icon(Icons.Default.MoreVert, stringResource(R.string.discovery_more_action)) }
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
    ) { contentPadding ->
        Column(Modifier.fillMaxSize().padding(contentPadding).consumeWindowInsets(contentPadding)) {
            AnimatedVisibility(searchVisible, enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
                DiscoveryComposeSearchBar(state, callbacks, active,
                    onFilters = { callbacks.onOpenFilters(); filtersVisible = true },
                    modifier = Modifier.padding(horizontal = DiscoveryDimensions.Page),
                    onSearchActiveChanged = { searchActive = it })
            }
            DiscoveryFilterChipRow(state.chips, callbacks::onRemoveChip, callbacks::onClearFilters,
                Modifier.padding(horizontal = DiscoveryDimensions.Page))
            Row(Modifier.fillMaxWidth().padding(horizontal = DiscoveryDimensions.Page),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween) {
                Text(stringResource(R.string.discovery_results_count, state.total),
                    style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                DiscoverySortMenu(state.sortField, state.descending, callbacks::onSelectSort)
            }
            if (state.statusMessage.isNotBlank()) Text(state.statusMessage,
                Modifier.padding(horizontal = DiscoveryDimensions.Page),
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (state.statusError.isNotBlank()) TextButton(
                onClick = { sourceDetailsVisible = true }, modifier = Modifier.padding(horizontal = DiscoveryDimensions.Gap)) {
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
        text = { Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(DiscoveryDimensions.Gap)) {
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
    val colors = NavigationBarItemDefaults.colors(
        selectedIconColor = MaterialTheme.colorScheme.onPrimaryContainer,
        selectedTextColor = MaterialTheme.colorScheme.primary,
        indicatorColor = MaterialTheme.colorScheme.primaryContainer,
        unselectedIconColor = MaterialTheme.colorScheme.onSurfaceVariant,
        unselectedTextColor = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    NavigationBar(modifier = Modifier.testTag("discoveryNavigation")) {
        NavigationBarItem(selected = false, onClick = { onNavigate("home") },
            icon = { Icon(Icons.Default.Home, null) }, label = { Text(stringResource(R.string.discovery_nav_home)) }, colors = colors)
        NavigationBarItem(selected = false, onClick = { onNavigate("library") },
            icon = { Icon(Icons.AutoMirrored.Filled.List, null) }, label = { Text(stringResource(R.string.discovery_nav_library)) }, colors = colors)
        NavigationBarItem(selected = true, onClick = { onNavigate("discover") },
            icon = { Icon(painterResource(R.drawable.discovery_explore), null) }, label = { Text(stringResource(R.string.discovery_nav_discover)) }, colors = colors)
        NavigationBarItem(selected = false, onClick = { onNavigate("mine") },
            icon = { Icon(Icons.Default.Person, null) }, label = { Text(stringResource(R.string.discovery_nav_mine)) }, colors = colors)
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
