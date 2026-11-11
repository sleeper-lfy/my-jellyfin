package net.lumen.media

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.mapSaver
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.tooling.preview.Preview
import java.util.Locale
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.KeyboardArrowUp
import net.lumen.media.ui.components.AppIcons
import net.lumen.media.ui.theme.AppDimensions
import net.lumen.media.ui.theme.LocalAppSpacing

/** The only filter surface for discovery. Draft changes never mutate the coordinator. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DiscoveryFilterBottomSheet(
    state: DiscoveryUiState,
    callbacks: DiscoveryCallbacks,
    onDismiss: () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        shape = MaterialTheme.shapes.large,
        containerColor = MaterialTheme.colorScheme.surfaceContainer,
        dragHandle = { Surface(Modifier.padding(vertical = LocalAppSpacing.current.sm)
            .size(AppDimensions.SheetHandleWidth, AppDimensions.SheetHandleHeight),
            shape = MaterialTheme.shapes.small, color = MaterialTheme.colorScheme.onSurfaceVariant, content = {}) },
        contentWindowInsets = { WindowInsets.safeDrawing },
    ) {
        DiscoveryFilterContent(state, callbacks, onDismiss)
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
internal fun DiscoveryFilterContent(
    state: DiscoveryUiState,
    callbacks: DiscoveryCallbacks,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var draft by rememberSaveable(stateSaver = DiscoveryDraftSaver) { mutableStateOf(state.filters.copy()) }
    var tagQuery by rememberSaveable { mutableStateOf("") }
    var tagLimit by rememberSaveable { mutableIntStateOf(12) }
    var advanced by rememberSaveable { mutableStateOf(hasAdvancedFilters(state.filters)) }
    var errors by remember { mutableStateOf(emptyMap<String, Int>()) }
    val spacing = LocalAppSpacing.current
    fun change(update: (DiscoveryFilters) -> Unit) { draft = draft.copy().also(update) }
    val selected = filterTokens(draft.tagsAll)
    val availableTags = remember(state.facets, selected, tagQuery) {
        val values = state.facets.optJSONArray("tags")
        val all = (selected + (0 until (values?.length() ?: 0)).map { values!!.optString(it) }).distinct()
        all.filter { it.isNotBlank() && it.lowercase(Locale.ROOT).contains(tagQuery.trim().lowercase(Locale.ROOT)) }
    }
    Column(modifier.fillMaxWidth().navigationBarsPadding().imePadding().fillMaxHeight(AppDimensions.SheetMaxHeightFraction)) {
        Text(stringResource(R.string.discovery_filter_title),
            modifier = Modifier.padding(horizontal = spacing.page, vertical = spacing.sm),
            style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.onSurface)
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth().testTag("filterForm"),
            contentPadding = PaddingValues(horizontal = spacing.page, vertical = spacing.sm),
            verticalArrangement = Arrangement.spacedBy(spacing.md),
        ) {
            if (draft.online) item {
                ProviderField(state, draft.provider, { value -> change { it.provider = value } }, callbacks::onRefreshProviders)
                Spacer(Modifier.height(spacing.sm))
                FilterTextField(draft.searchTag, { value -> change { it.searchTag = value } }, R.string.discovery_filter_search_tag, "filterSearchTag", error = errors["searchTag"])
                Text(stringResource(R.string.discovery_filter_search_note), modifier = Modifier.padding(top = spacing.xs),
                    style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            item {
                FilterSectionTitle(R.string.discovery_filter_watch)
                FlowRow(Modifier.fillMaxWidth().testTag("filterWatch"),
                    horizontalArrangement = Arrangement.spacedBy(spacing.sm), verticalArrangement = Arrangement.spacedBy(spacing.xs)) {
                    listOf("" to R.string.discovery_watch_all_short, "unwatched" to R.string.discovery_watch_unwatched_short,
                        "progress" to R.string.discovery_filter_watch_progress, "completed" to R.string.discovery_watch_completed_short).forEach { (value, label) ->
                        DiscoveryChoiceChip(stringResource(label), draft.watch == value, "filterWatch:${value.ifEmpty { "all" }}",
                            { change { it.watch = value } })
                    }
                }
            }
            item {
                FilterSectionTitle(R.string.discovery_filter_preferences)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(spacing.sm), verticalArrangement = Arrangement.spacedBy(spacing.xs)) {
                    DiscoveryChoiceChip(stringResource(R.string.discovery_filter_favorite), draft.favorite, "filterFavorite",
                        { change { it.favorite = !it.favorite; if (it.favorite) it.disliked = false } }, AppIcons.Favorite)
                    DiscoveryChoiceChip(stringResource(R.string.discovery_filter_wanted), draft.wanted, "filterWanted",
                        { change { it.wanted = !it.wanted } }, AppIcons.Watchlist)
                    DiscoveryChoiceChip(stringResource(R.string.discovery_filter_disliked), draft.disliked, "filterDisliked",
                        { change { it.disliked = !it.disliked; if (it.disliked) it.favorite = false } })
                }
            }
            item {
                FilterSectionTitle(R.string.discovery_tags_section)
                FilterTextField(tagQuery, { tagQuery = it; tagLimit = 12 }, R.string.discovery_filter_tag_search,
                    "filterTagSearch", placeholder = R.string.discovery_tags_search_placeholder, showLabel = false)
                if (selected.isNotEmpty()) Text(stringResource(R.string.discovery_tags_selected_count, selected.size),
                    modifier = Modifier.padding(top = spacing.xs), style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                if (availableTags.isEmpty()) Text(stringResource(R.string.discovery_filter_tag_empty),
                    modifier = Modifier.padding(top = spacing.sm), style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                FlowRow(modifier = Modifier.fillMaxWidth().testTag("filterTags"),
                    horizontalArrangement = Arrangement.spacedBy(spacing.sm), verticalArrangement = Arrangement.spacedBy(spacing.xs)) {
                    availableTags.take(tagLimit).forEach { tag ->
                        DiscoveryChoiceChip(tag, tag in selected, "filterTagChoice:$tag", {
                            change { value -> value.tagsAll = (if (tag in selected) selected - tag else selected + tag).joinToString(",") }
                        })
                    }
                }
                if (availableTags.size > tagLimit) TextButton(onClick = { tagLimit += 12 },
                    modifier = Modifier.heightIn(min = AppDimensions.TouchTarget)) { Text(stringResource(R.string.discovery_filter_more_tags)) }
            }
            item {
                FilterSectionTitle(R.string.discovery_filter_actor)
                FilterTextField(draft.actor, { value -> change { it.actor = value } }, R.string.discovery_filter_actor,
                    "filterActor", error = errors["actor"], placeholder = R.string.discovery_actor_search_placeholder, showLabel = false)
            }
            item {
                FilterSectionTitle(R.string.discovery_year_section)
                Row(horizontalArrangement = Arrangement.spacedBy(spacing.md)) {
                    FilterTextField(draft.yearMin, { value -> change { it.yearMin = value } }, R.string.discovery_filter_year_from,
                        "filterYearFrom", error = errors["yearMin"], numeric = true, modifier = Modifier.weight(1f), placeholder = R.string.discovery_year_from_placeholder, showLabel = false)
                    FilterTextField(draft.yearMax, { value -> change { it.yearMax = value } }, R.string.discovery_filter_year_to,
                        "filterYearTo", error = errors["yearMax"], numeric = true, modifier = Modifier.weight(1f), placeholder = R.string.discovery_year_to_placeholder, showLabel = false)
                }
            }
            item {
                TextButton(onClick = { advanced = !advanced }, modifier = Modifier.fillMaxWidth()
                    .heightIn(min = AppDimensions.TouchTarget).testTag("filterAdvanced")) {
                    Text(stringResource(R.string.discovery_advanced_short), style = MaterialTheme.typography.titleMedium)
                    Spacer(Modifier.weight(1f))
                    Icon(if (advanced) Icons.Default.KeyboardArrowUp else Icons.Default.KeyboardArrowDown, contentDescription = null)
                }
            }
            if (advanced) {
                item { FilterTextField(draft.tag, { value -> change { it.tag = value } }, R.string.discovery_filter_tag_keyword, "filterTag", error = errors["tag"]) }
                item { FilterTextField(draft.tagsAll, { value -> change { it.tagsAll = value } }, R.string.discovery_filter_tags_all, "filterTagsAll", error = errors["tagsAll"], placeholder = R.string.discovery_filter_tags_hint) }
                item { FilterTextField(draft.tagsAny, { value -> change { it.tagsAny = value } }, R.string.discovery_filter_tags_any, "filterTagsAny", error = errors["tagsAny"], placeholder = R.string.discovery_filter_tags_hint) }
                item { FilterTextField(draft.tagsNot, { value -> change { it.tagsNot = value } }, R.string.discovery_filter_tags_not, "filterTagsNot", error = errors["tagsNot"], placeholder = R.string.discovery_filter_tags_hint) }
                item { FilterTextField(draft.ratingMin, { value -> change { it.ratingMin = value } }, R.string.discovery_filter_rating, "filterRating", error = errors["ratingMin"], numeric = true) }
            }
        }
        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
        Row(Modifier.fillMaxWidth().padding(horizontal = spacing.page, vertical = spacing.md).testTag("filterFooter"),
            horizontalArrangement = Arrangement.spacedBy(spacing.md), verticalAlignment = Alignment.CenterVertically) {
            TextButton(
                onClick = { draft = DiscoveryFilters().also { it.online = draft.online; it.provider = draft.provider; it.searchTag = draft.searchTag; it.hasResults = draft.hasResults }; tagQuery = ""; errors = emptyMap(); advanced = false },
                modifier = Modifier.weight(1f).heightIn(min = AppDimensions.TouchTarget).testTag("filterReset"),
            ) { Text(stringResource(R.string.discovery_filter_reset)) }
            Button(
                onClick = {
                    val result = normalizedDiscoveryFilters(draft)
                    errors = validateDiscoveryFilters(result)
                    if (errors.isEmpty()) { callbacks.onApplyFilters(result); onDismiss() }
                },
                modifier = Modifier.weight(1f).heightIn(min = AppDimensions.TouchTarget).testTag("filterApply"),
                shape = MaterialTheme.shapes.medium,
            ) { Text(stringResource(R.string.discovery_filter_apply)) }
        }
    }
}

/** Compact Material visual in an independent 48dp touch slot; selected semantics stay on the chip. */
@Composable
private fun DiscoveryChoiceChip(label: String, selected: Boolean, tag: String, action: () -> Unit, icon: ImageVector? = null) {
    Box(Modifier.heightIn(min = AppDimensions.TouchTarget).testTag("$tag:touch"), contentAlignment = Alignment.Center) {
        FilterChip(selected, action, label = { Text(label, style = MaterialTheme.typography.labelMedium) },
            modifier = Modifier.heightIn(min = AppDimensions.ChipHeight, max = AppDimensions.ChipHeight).testTag(tag),
            leadingIcon = (icon ?: if (selected) Icons.Default.Check else null)?.let { glyph ->
                { Icon(glyph, contentDescription = null, modifier = Modifier.size(AppDimensions.ChipIcon)) }
            },
            shape = MaterialTheme.shapes.extraLarge,
            colors = filterChipColors(),
            border = FilterChipDefaults.filterChipBorder(enabled = true, selected = selected,
                borderColor = MaterialTheme.colorScheme.outlineVariant, selectedBorderColor = MaterialTheme.colorScheme.secondaryContainer))
    }
}

@Composable private fun FilterSectionTitle(label: Int) { Text(stringResource(label), style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurface) }
@Composable private fun filterChipColors() = FilterChipDefaults.filterChipColors(selectedContainerColor = MaterialTheme.colorScheme.secondaryContainer, selectedLabelColor = MaterialTheme.colorScheme.onSecondaryContainer, selectedLeadingIconColor = MaterialTheme.colorScheme.onSecondaryContainer)

@Composable
private fun FilterTextField(value: String, changed: (String) -> Unit, label: Int, tag: String, modifier: Modifier = Modifier, error: Int? = null, placeholder: Int? = null, numeric: Boolean = false, showLabel: Boolean = true) {
    val fieldLabel = stringResource(label)
    OutlinedTextField(value, changed, modifier.fillMaxWidth().heightIn(min = AppDimensions.TouchTarget).testTag(tag)
        .then(if (showLabel) Modifier else Modifier.semantics { contentDescription = fieldLabel }),
        label = if (showLabel) ({ Text(fieldLabel) }) else null,
        placeholder = placeholder?.let { { Text(stringResource(it), style = MaterialTheme.typography.bodyMedium) } },
        singleLine = true, isError = error != null, supportingText = error?.let { { Text(stringResource(it)) } },
        textStyle = MaterialTheme.typography.bodyMedium, shape = MaterialTheme.shapes.medium,
        keyboardOptions = KeyboardOptions(keyboardType = if (numeric) KeyboardType.Number else KeyboardType.Text))
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FilterChoiceField(label: Int, value: String, choices: List<Pair<String, String>>, onSelect: (String) -> Unit, tag: String, enabled: Boolean = true) {
    var expanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded, onExpandedChange = { if (enabled) expanded = it }) {
        OutlinedTextField(choices.firstOrNull { it.first == value }?.second.orEmpty(), {}, Modifier.menuAnchor().fillMaxWidth().heightIn(min = AppDimensions.TouchTarget).testTag(tag), enabled = enabled, readOnly = true, label = { Text(stringResource(label)) }, trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) }, textStyle = MaterialTheme.typography.bodyMedium, shape = MaterialTheme.shapes.medium)
        ExposedDropdownMenu(expanded, onDismissRequest = { expanded = false }) { choices.forEach { (key, title) -> DropdownMenuItem(text = { Text(title, style = MaterialTheme.typography.bodyMedium) }, onClick = { onSelect(key); expanded = false }, modifier = Modifier.heightIn(min = AppDimensions.TouchTarget)) } }
    }
}

@Composable
private fun ProviderField(state: DiscoveryUiState, selected: String, onSelect: (String) -> Unit, refresh: () -> Unit) {
    val sources = (0 until state.providers.length()).mapNotNull { state.providers.optJSONObject(it) }
    val choices = mutableListOf("" to stringResource(R.string.discovery_filter_all_providers))
    sources.forEach { choices += it.optString("id") to it.optString("name", it.optString("id")) }
    if (selected.isNotEmpty() && choices.none { it.first == selected }) choices += selected to stringResource(R.string.discovery_filter_missing_provider)
    FilterChoiceField(R.string.discovery_filter_provider, selected, choices, onSelect, "discoveryProvider", !state.providerLoading && sources.isNotEmpty())
    val source = sources.firstOrNull { it.optString("id") == selected }
    val message = when {
        state.providerLoading -> stringResource(R.string.discovery_filter_provider_loading)
        state.providerError.isNotEmpty() -> stringResource(R.string.discovery_filter_provider_error, state.providerError)
        sources.isEmpty() -> stringResource(R.string.discovery_filter_provider_empty)
        selected.isNotEmpty() && source == null -> stringResource(R.string.discovery_filter_provider_unavailable)
        source != null && !source.optBoolean("supports_tags") -> stringResource(R.string.discovery_filter_provider_title_only)
        else -> null
    }
    if (message != null) Text(message, modifier = Modifier.padding(top = LocalAppSpacing.current.sm), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    TextButton(onClick = refresh, enabled = !state.providerLoading, modifier = Modifier.heightIn(min = AppDimensions.TouchTarget)) { Icon(Icons.Default.Refresh, null); Spacer(Modifier.width(LocalAppSpacing.current.sm)); Text(stringResource(R.string.discovery_filter_provider_refresh)) }
}

private fun filterTokens(value: String) = value.replace('，', ',').split(',').map(String::trim).filter(String::isNotEmpty).distinct()
private fun hasAdvancedFilters(value: DiscoveryFilters) = listOf(value.actor, value.yearMin, value.yearMax, value.ratingMin, value.tagsAny, value.tagsNot).any(String::isNotEmpty)
private val DiscoveryDraftSaver = mapSaver<DiscoveryFilters>(
    save = { mapOf("tag" to it.tag, "actor" to it.actor, "yearMin" to it.yearMin, "yearMax" to it.yearMax, "ratingMin" to it.ratingMin,
        "tagsAll" to it.tagsAll, "tagsAny" to it.tagsAny, "tagsNot" to it.tagsNot, "watch" to it.watch, "provider" to it.provider,
        "searchTag" to it.searchTag, "favorite" to it.favorite, "wanted" to it.wanted, "disliked" to it.disliked, "online" to it.online, "hasResults" to it.hasResults) },
    restore = { saved -> DiscoveryFilters().also {
        it.tag = saved["tag"] as? String ?: ""; it.actor = saved["actor"] as? String ?: ""
        it.yearMin = saved["yearMin"] as? String ?: ""; it.yearMax = saved["yearMax"] as? String ?: ""; it.ratingMin = saved["ratingMin"] as? String ?: ""
        it.tagsAll = saved["tagsAll"] as? String ?: ""; it.tagsAny = saved["tagsAny"] as? String ?: ""; it.tagsNot = saved["tagsNot"] as? String ?: ""
        it.watch = saved["watch"] as? String ?: ""; it.provider = saved["provider"] as? String ?: ""; it.searchTag = saved["searchTag"] as? String ?: ""
        it.favorite = saved["favorite"] as? Boolean ?: false; it.wanted = saved["wanted"] as? Boolean ?: false; it.disliked = saved["disliked"] as? Boolean ?: false
        it.online = saved["online"] as? Boolean ?: false; it.hasResults = saved["hasResults"] as? Boolean ?: false
    } },
)
internal fun normalizedDiscoveryFilters(value: DiscoveryFilters) = value.copy().also {
    it.tag = it.tag.trim(); it.searchTag = it.searchTag.trim(); it.actor = it.actor.trim()
    it.yearMin = it.yearMin.trim(); it.yearMax = it.yearMax.trim(); it.ratingMin = it.ratingMin.trim()
    it.tagsAll = filterTokens(it.tagsAll).joinToString(","); it.tagsAny = filterTokens(it.tagsAny).joinToString(","); it.tagsNot = filterTokens(it.tagsNot).joinToString(",")
}
internal fun validateDiscoveryFilters(value: DiscoveryFilters): Map<String, Int> {
    val errors = mutableMapOf<String, Int>()
    listOf("yearMin" to value.yearMin, "yearMax" to value.yearMax).forEach { (key, year) -> if (year.isNotEmpty() && (year.length != 4 || year.toIntOrNull() !in 1800..2200)) errors[key] = R.string.discovery_filter_error_year }
    if (errors.isEmpty() && value.yearMin.isNotEmpty() && value.yearMax.isNotEmpty() && value.yearMin.toInt() > value.yearMax.toInt()) errors["yearMin"] = R.string.discovery_filter_error_range
    if (value.ratingMin.isNotEmpty() && value.ratingMin.toIntOrNull() !in 0..10) errors["ratingMin"] = R.string.discovery_filter_error_rating
    listOf("tag" to value.tag, "searchTag" to value.searchTag, "actor" to value.actor, "tagsAll" to value.tagsAll, "tagsAny" to value.tagsAny, "tagsNot" to value.tagsNot).forEach { (key, text) -> if (text.length > 2000) errors[key] = R.string.discovery_filter_error_length }
    return errors
}

@Preview(name = "FilterBottomSheet light", locale = "zh", widthDp = 393, heightDp = 760, showBackground = true)
@Composable private fun FilterBottomSheetLightPreview() { DiscoveryTheme(darkTheme = false) { Surface(shape = MaterialTheme.shapes.large, color = MaterialTheme.colorScheme.surfaceContainer) { DiscoveryFilterContent(DiscoveryUiState.empty(), PreviewFilterCallbacks, {}) } } }
@Preview(name = "FilterBottomSheet dark", locale = "zh", widthDp = 393, heightDp = 760, showBackground = true)
@Composable private fun FilterBottomSheetDarkPreview() { DiscoveryTheme(darkTheme = true) { Surface(shape = MaterialTheme.shapes.large, color = MaterialTheme.colorScheme.surfaceContainer) { DiscoveryFilterContent(DiscoveryUiState.empty(), PreviewFilterCallbacks, {}) } } }

private object PreviewFilterCallbacks : DiscoveryCallbacks {
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
