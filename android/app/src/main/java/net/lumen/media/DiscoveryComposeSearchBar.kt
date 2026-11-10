package net.lumen.media

import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.DockedSearchBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.tooling.preview.Preview

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun DiscoveryComposeSearchBar(
    state: DiscoveryUiState,
    callbacks: DiscoveryCallbacks,
    active: Boolean,
    onFilters: () -> Unit,
    modifier: Modifier = Modifier,
    onSearchActiveChanged: (Boolean) -> Unit = {},
) {
    var expanded by rememberSaveable { mutableStateOf(false) }
    val focus = LocalFocusManager.current
    val keyboard = LocalSoftwareKeyboardController.current
    fun finishSearch() { expanded = false; focus.clearFocus(); keyboard?.hide() }
    LaunchedEffect(active) { if (!active) expanded = false }
    LaunchedEffect(expanded, active) { onSearchActiveChanged(active && expanded) }
    DockedSearchBar(
        query = state.query,
        onQueryChange = { callbacks.onQueryChanged(it); expanded = true },
        onSearch = { finishSearch(); callbacks.onSubmitSearch(it) },
        active = expanded,
        onActiveChange = { expanded = it },
        modifier = modifier.fillMaxWidth().heightIn(min = DiscoveryDimensions.SearchHeight).testTag("discoverySearch"),
        placeholder = { Text(stringResource(R.string.discovery_search_hint), style = MaterialTheme.typography.bodyMedium) },
        leadingIcon = { Icon(Icons.Default.Search, stringResource(R.string.discovery_search_action)) },
        trailingIcon = {
            Row {
                if (state.query.isNotEmpty()) IconButton(onClick = { callbacks.onQueryChanged("") },
                    modifier = Modifier.size(DiscoveryDimensions.TouchTarget).testTag("discoveryClearSearch")) {
                    Icon(Icons.Default.Close, stringResource(R.string.discovery_search_clear))
                }
                IconButton(onClick = { finishSearch(); onFilters() },
                    modifier = Modifier.size(DiscoveryDimensions.TouchTarget).testTag("discoveryFilter")) {
                    Icon(painterResource(R.drawable.discovery_filter_alt), stringResource(R.string.discovery_filter_action))
                }
            }
        },
    ) {
        val query = state.query.trim()
        Column(Modifier.verticalScroll(rememberScrollState())) { if (query.isNotEmpty()) {
            listOf("title", "tag").forEach { group ->
                Text(stringResource(if (group == "title") R.string.discovery_search_title_group else R.string.discovery_search_tag_group),
                    modifier = Modifier.padding(horizontal = DiscoveryDimensions.Page, vertical = DiscoveryDimensions.Gap),
                    style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                ListItem(
                    headlineContent = { Text(stringResource(if (group == "title") R.string.discovery_search_by_title else R.string.discovery_search_by_tag, query),
                        style = MaterialTheme.typography.bodyMedium) },
                    modifier = Modifier.clickable { finishSearch(); callbacks.onSelectSuggestion(group, query) },
                )
                state.suggestions.filter { it.group == group && it.value != query }.take(4).forEach { suggestion ->
                    ListItem(headlineContent = { Text(suggestion.value, style = MaterialTheme.typography.bodyMedium, maxLines = 2) },
                        modifier = Modifier.clickable { finishSearch(); callbacks.onSelectSuggestion(suggestion.group, suggestion.value) })
                }
            }
        } }
    }
}

@Preview(name = "Search bar · Light", showBackground = true, widthDp = 393)
@Composable
private fun SearchLightPreview() { DiscoveryTheme(false) { DiscoveryComposeSearchBar(discoveryPreviewState(), PreviewDiscoveryCallbacks, true, {}) } }

@Preview(name = "Search bar · Dark", showBackground = true, widthDp = 393)
@Composable
private fun SearchDarkPreview() { DiscoveryTheme(true) { DiscoveryComposeSearchBar(discoveryPreviewState(), PreviewDiscoveryCallbacks, true, {}) } }
