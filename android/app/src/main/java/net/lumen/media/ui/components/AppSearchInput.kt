package net.lumen.media.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.tooling.preview.Preview
import net.lumen.media.R
import net.lumen.media.ui.theme.AppDimensions
import net.lumen.media.ui.theme.LocalAppSpacing
import net.lumen.media.ui.theme.LumenTheme

/** UI values only: group identities and requests are owned by the caller. */
@Immutable
data class AppSearchSuggestion(val id: String, val label: String, val supportingText: String? = null)

@Immutable
data class AppSearchSuggestionGroup(val id: String, val title: String, val items: List<AppSearchSuggestion>)

/** A selection/search input with an explicit, caller-specific placeholder. */
@Composable
fun AppSearchInput(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    placeholder: String,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    suggestionGroups: List<AppSearchSuggestionGroup> = emptyList(),
    onSuggestionSelected: (groupId: String, item: AppSearchSuggestion) -> Unit = { _, _ -> },
    onSearch: ((String) -> Unit)? = null,
) {
    val spacing = LocalAppSpacing.current
    val keyboard = LocalSoftwareKeyboardController.current
    val focusRequester = remember { FocusRequester() }
    Column(modifier.fillMaxWidth().imePadding(), verticalArrangement = Arrangement.spacedBy(spacing.sm)) {
        OutlinedTextField(
            value = value,
            onValueChange = onValueChange,
            modifier = Modifier.fillMaxWidth().heightIn(min = AppDimensions.TouchTarget).focusRequester(focusRequester),
            enabled = enabled,
            label = { Text(label) },
            placeholder = { Text(placeholder) },
            singleLine = true,
            textStyle = MaterialTheme.typography.bodyLarge,
            shape = MaterialTheme.shapes.medium,
            leadingIcon = { Icon(AppIcons.Search, contentDescription = null, modifier = Modifier.size(AppDimensions.Icon)) },
            trailingIcon = if (value.isNotEmpty()) {
                {
                    IconButton(
                        onClick = { onValueChange(""); focusRequester.requestFocus() },
                        modifier = Modifier.size(AppDimensions.TouchTarget),
                        enabled = enabled,
                    ) {
                        Icon(Icons.Outlined.Close, contentDescription = stringResource(R.string.design_system_input_clear))
                    }
                }
            } else null,
            keyboardOptions = KeyboardOptions(imeAction = if (onSearch == null) ImeAction.Done else ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { onSearch?.invoke(value) }, onDone = { keyboard?.hide() }),
        )
        if (enabled && suggestionGroups.any { it.items.isNotEmpty() }) {
            Surface(shape = MaterialTheme.shapes.medium, color = MaterialTheme.colorScheme.surfaceContainer) {
                LazyColumn(
                    modifier = Modifier.fillMaxWidth().heightIn(max = AppDimensions.SearchSuggestionsMaxHeight),
                    verticalArrangement = Arrangement.spacedBy(spacing.xs),
                ) {
                    suggestionGroups.filter { it.items.isNotEmpty() }.forEach { group ->
                        item(key = "group:${group.id}") {
                            Text(
                                group.title,
                                modifier = Modifier.padding(horizontal = spacing.lg, vertical = spacing.sm),
                                style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        items(group.items.size, key = { index -> "${group.id}:${group.items[index].id}" }) { index ->
                            val suggestion = group.items[index]
                            ListItem(
                                headlineContent = { Text(suggestion.label, style = MaterialTheme.typography.bodyLarge) },
                                supportingContent = suggestion.supportingText?.let { support ->
                                    { Text(support, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                                },
                                modifier = Modifier.fillMaxWidth().heightIn(min = AppDimensions.TouchTarget)
                                    .clickable { onSuggestionSelected(group.id, suggestion) },
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SearchInputPreview(dark: Boolean) {
    LumenTheme(darkTheme = dark) {
        val spacing = LocalAppSpacing.current
        Surface(color = MaterialTheme.colorScheme.surface) {
            Column(Modifier.padding(spacing.page), verticalArrangement = Arrangement.spacedBy(spacing.xl)) {
                AppSearchInput(
                    value = stringResource(R.string.design_system_input_preview_query),
                    onValueChange = {},
                    label = stringResource(R.string.design_system_input_preview_label),
                    placeholder = stringResource(R.string.design_system_input_preview_placeholder),
                    suggestionGroups = listOf(
                        AppSearchSuggestionGroup("titles", stringResource(R.string.design_system_input_preview_movies), listOf(
                            AppSearchSuggestion("coast", stringResource(R.string.design_system_input_preview_movie_one)),
                            AppSearchSuggestion("mountain", stringResource(R.string.design_system_input_preview_movie_two)),
                        )),
                        AppSearchSuggestionGroup("tags", stringResource(R.string.design_system_input_preview_tags), listOf(
                            AppSearchSuggestion("coast", stringResource(R.string.design_system_input_preview_tag)),
                        )),
                    ),
                )
                AppSearchInput(
                    value = "",
                    onValueChange = {},
                    label = stringResource(R.string.design_system_input_preview_year_label),
                    placeholder = stringResource(R.string.design_system_input_preview_year_placeholder),
                )
            }
        }
    }
}

@Preview(name = "AppSearchInput dark", locale = "zh", widthDp = 393, heightDp = 520, showBackground = true)
@Composable private fun AppSearchInputDarkPreview() = SearchInputPreview(dark = true)

@Preview(name = "AppSearchInput light", locale = "zh", widthDp = 393, heightDp = 520, showBackground = true)
@Composable private fun AppSearchInputLightPreview() = SearchInputPreview(dark = false)
