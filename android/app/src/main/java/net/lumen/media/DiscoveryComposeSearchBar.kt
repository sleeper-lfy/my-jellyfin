package net.lumen.media

import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.tooling.preview.Preview
import net.lumen.media.ui.components.AppIcons
import net.lumen.media.ui.theme.AppDimensions
import net.lumen.media.ui.theme.LocalAppSpacing

/** One field for title/tag suggestions, with one separate, full-size filter action. */
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
    val spacing = LocalAppSpacing.current
    fun finishSearch() { expanded = false; focus.clearFocus(); keyboard?.hide() }
    LaunchedEffect(active) { if (!active) expanded = false }
    LaunchedEffect(expanded, active) { onSearchActiveChanged(active && expanded) }
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(spacing.xs)) {
        Row(Modifier.fillMaxWidth().testTag("discoverySearch"),
            horizontalArrangement = Arrangement.spacedBy(spacing.sm), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(
                value = state.query,
                onValueChange = { callbacks.onQueryChanged(it); expanded = true },
                modifier = Modifier.weight(1f).heightIn(min = AppDimensions.SearchHeight)
                    .onFocusChanged { expanded = it.isFocused },
                placeholder = { Text(stringResource(R.string.discovery_search_hint), style = MaterialTheme.typography.bodyMedium) },
                leadingIcon = { Icon(AppIcons.Search, contentDescription = null, modifier = Modifier.size(AppDimensions.Icon)) },
                trailingIcon = if (state.query.isNotEmpty()) ({
                    IconButton(onClick = { callbacks.onQueryChanged("") },
                        modifier = Modifier.size(AppDimensions.TouchTarget).testTag("discoveryClearSearch")) {
                        Icon(Icons.Outlined.Close, stringResource(R.string.discovery_search_clear))
                    }
                }) else null,
                singleLine = true,
                textStyle = MaterialTheme.typography.bodyMedium,
                shape = MaterialTheme.shapes.medium,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { finishSearch(); callbacks.onSubmitSearch(state.query) }),
            )
            BadgedBox(badge = { if (state.chips.isNotEmpty()) Badge { Text(state.chips.size.toString()) } }) {
                IconButton(onClick = { finishSearch(); onFilters() },
                    modifier = Modifier.size(AppDimensions.TouchTarget).testTag("discoveryFilter")) {
                    Icon(AppIcons.Filter, stringResource(R.string.discovery_filter_action), Modifier.size(AppDimensions.Icon))
                }
            }
        }
        val query = state.query.trim()
        if (expanded && active && query.isNotEmpty()) Surface(shape = MaterialTheme.shapes.medium,
            color = MaterialTheme.colorScheme.surfaceContainer) {
            Column(Modifier.fillMaxWidth().heightIn(max = AppDimensions.SearchSuggestionsMaxHeight)
                .verticalScroll(rememberScrollState())) {
                listOf("title", "tag").forEach { group ->
                    Text(stringResource(if (group == "title") R.string.discovery_search_title_group else R.string.discovery_search_tag_group),
                        modifier = Modifier.padding(horizontal = spacing.page, vertical = spacing.sm),
                        style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    ListItem(
                        headlineContent = { Text(stringResource(if (group == "title") R.string.discovery_search_by_title else R.string.discovery_search_by_tag, query),
                            style = MaterialTheme.typography.bodyMedium) },
                        modifier = Modifier.heightIn(min = AppDimensions.TouchTarget)
                            .clickable { finishSearch(); callbacks.onSelectSuggestion(group, query) },
                    )
                    state.suggestions.filter { it.group == group && it.value != query }.take(4).forEach { suggestion ->
                        ListItem(headlineContent = { Text(suggestion.value, style = MaterialTheme.typography.bodyMedium, maxLines = 2) },
                            modifier = Modifier.heightIn(min = AppDimensions.TouchTarget)
                                .clickable { finishSearch(); callbacks.onSelectSuggestion(suggestion.group, suggestion.value) })
                    }
                }
            }
        }
    }
}

@Preview(name = "Search bar · Light", showBackground = true, widthDp = 393)
@Composable
private fun SearchLightPreview() { DiscoveryTheme(false) { DiscoveryComposeSearchBar(discoveryPreviewState(), PreviewDiscoveryCallbacks, true, {}) } }

@Preview(name = "Search bar · Dark", showBackground = true, widthDp = 393)
@Composable
private fun SearchDarkPreview() { DiscoveryTheme(true) { DiscoveryComposeSearchBar(discoveryPreviewState(), PreviewDiscoveryCallbacks, true, {}) } }
