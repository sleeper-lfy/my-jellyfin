package net.lumen.media.ui.preview

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.PlayArrow
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import net.lumen.media.R
import net.lumen.media.ui.components.*
import net.lumen.media.ui.theme.AppDimensions
import net.lumen.media.ui.theme.LocalAppSpacing
import net.lumen.media.ui.theme.LumenTheme

/** Only preview-viewport dimensions: these never style a migrated application page. */
private object PreviewDimensions {
    val WideBreakpoint = 840.dp
    val SheetHeight = 300.dp
}

/** A self-contained component gallery. It has no route, service, or business-model dependency. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DesignSystemPreview(modifier: Modifier = Modifier) {
    val spacing = LocalAppSpacing.current
    var destination by remember { mutableStateOf(AppDestination.Home) }
    var sheetVisible by remember { mutableStateOf(false) }
    AppScreenScaffold(
        modifier = modifier.testTag("designSystemGallery"),
        topBar = { AppTopBar(stringResource(R.string.design_system_title), onBack = {}) {
            IconButton({}, Modifier.size(AppDimensions.TouchTarget)) {
                Icon(AppIcons.More, stringResource(R.string.design_system_icon_more))
            }
        } },
        bottomBar = { AppBottomNavigation(destination, { destination = it }) },
    ) {
        BoxWithConstraints(Modifier.fillMaxSize().padding(horizontal = spacing.page)) {
            if (maxWidth >= PreviewDimensions.WideBreakpoint) {
                Row(Modifier.fillMaxSize().padding(vertical = spacing.lg),
                    horizontalArrangement = Arrangement.spacedBy(spacing.xl)) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(spacing.lg)) { ControlsColumn() }
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(spacing.lg)) { ContentColumn() }
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(spacing.lg)) { UtilityColumn { sheetVisible = true } }
                }
            } else {
                Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(vertical = spacing.lg),
                    verticalArrangement = Arrangement.spacedBy(spacing.xl)) {
                    ControlsColumn(); ContentColumn(); UtilityColumn { sheetVisible = true }
                }
            }
        }
    }
    if (sheetVisible) AppBottomSheet(stringResource(R.string.design_system_sheet_section),
        onDismiss = { sheetVisible = false }, onReset = {}, onApply = { sheetVisible = false }) {
        item { SheetExampleBody() }
    }
}

@Composable
private fun ColumnScope.ControlsColumn() {
    val spacing = LocalAppSpacing.current
    var selected by remember { mutableStateOf(true) }
    var text by remember { mutableStateOf("") }
    SectionHeader(stringResource(R.string.design_system_theme_section))
    Column(verticalArrangement = Arrangement.spacedBy(spacing.xs)) {
        Text(stringResource(R.string.design_system_type_title), style = MaterialTheme.typography.titleLarge)
        Text(stringResource(R.string.design_system_type_section), style = MaterialTheme.typography.titleMedium)
        Text(stringResource(R.string.design_system_type_body), style = MaterialTheme.typography.bodyLarge)
        Text(stringResource(R.string.design_system_type_supporting), style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(stringResource(R.string.design_system_type_label), style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    SectionHeader(stringResource(R.string.design_system_buttons_section))
    Column(verticalArrangement = Arrangement.spacedBy(spacing.sm)) {
        AppActionRow {
            PrimaryButton(stringResource(R.string.design_system_play), {}, leadingIcon = Icons.Outlined.PlayArrow)
            TonalButton(stringResource(R.string.design_system_favorite), {}, leadingIcon = AppIcons.Favorite)
        }
        AppActionRow {
            DangerButton(stringResource(R.string.design_system_shutdown), {})
            AppTextButton(stringResource(R.string.design_system_reset), {})
        }
        AppActionRow {
            PrimaryButton(stringResource(R.string.design_system_disabled), {}, enabled = false)
            TonalButton(stringResource(R.string.design_system_previous_page), {})
            TonalButton(stringResource(R.string.design_system_next_page), {})
        }
    }
    SectionHeader(stringResource(R.string.design_system_chips_section))
    Row(horizontalArrangement = Arrangement.spacedBy(spacing.sm)) {
        AppChip(stringResource(R.string.design_system_travel), selected, { selected = !selected })
        AppChip(stringResource(R.string.design_system_unselected), false, {})
        AppChip(stringResource(R.string.design_system_disabled), false, {}, enabled = false)
    }
    AppInputChip(stringResource(R.string.design_system_coast), {},
        stringResource(R.string.design_system_remove_coast))
    SectionHeader(stringResource(R.string.design_system_input_section))
    AppSearchInput(text, { text = it }, stringResource(R.string.design_system_tag_label),
        stringResource(R.string.design_system_tag_placeholder))
    AppSearchInput(stringResource(R.string.design_system_travel), {},
        stringResource(R.string.design_system_tag_label), stringResource(R.string.design_system_tag_placeholder))
}

@Composable
private fun ColumnScope.ContentColumn() {
    val spacing = LocalAppSpacing.current
    SectionHeader(stringResource(R.string.design_system_settings_group), onViewAll = {})
    SettingsExamples()
    SectionHeader(stringResource(R.string.design_system_poster_section))
    Row(horizontalArrangement = Arrangement.spacedBy(spacing.md)) {
        val states = listOf(PosterState.ReadyPainter(painterResource(R.drawable.discovery_preview_coast)),
            PosterState.Loading, PosterState.Failure)
        states.forEachIndexed { index, state ->
            PosterCard(stringResource(R.string.design_system_poster_title),
                stringResource(R.string.design_system_poster_subtitle), state, {}, index == 2, {}, Modifier.weight(1f))
        }
    }
    SectionHeader(stringResource(R.string.design_system_empty_section))
    EmptyState(AppIcons.Remote, stringResource(R.string.design_system_empty),
        supportingText = stringResource(R.string.design_system_empty_supporting),
        actionLabel = stringResource(R.string.design_system_select_movie), onAction = {})
}

@Composable
private fun ColumnScope.UtilityColumn(onOpenSheet: () -> Unit) {
    SectionHeader(stringResource(R.string.design_system_icons_section))
    IconExamples()
    SectionHeader(stringResource(R.string.design_system_sheet_section))
    Surface(shape = MaterialTheme.shapes.large, color = MaterialTheme.colorScheme.surfaceContainer) {
        AppBottomSheetContent(stringResource(R.string.design_system_sheet_section), {}, {},
            Modifier.heightIn(max = PreviewDimensions.SheetHeight)) { item { SheetExampleBody() } }
    }
    TonalButton(stringResource(R.string.design_system_sheet_open), onOpenSheet)
}

@Composable
private fun SheetExampleBody() {
    val spacing = LocalAppSpacing.current
    Column(verticalArrangement = Arrangement.spacedBy(spacing.sm)) {
        AppSearchInput("", {}, stringResource(R.string.design_system_tag_label), stringResource(R.string.design_system_tag_placeholder))
        Row(horizontalArrangement = Arrangement.spacedBy(spacing.sm)) {
            AppChip(stringResource(R.string.design_system_travel), true, {})
            AppChip(stringResource(R.string.design_system_coast), false, {})
        }
    }
}

@Preview(name = "Design system · Dark · All components", widthDp = 1280, heightDp = 1120, showBackground = true, locale = "zh")
@Composable
private fun DesignSystemDarkPreview() { LumenTheme(true) { DesignSystemPreview() } }

@Preview(name = "Design system · Light · All components", widthDp = 1280, heightDp = 1120, showBackground = true, locale = "zh")
@Composable
private fun DesignSystemLightPreview() { LumenTheme(false) { DesignSystemPreview() } }

@Preview(name = "Design system · Dark · Phone", widthDp = 393, heightDp = 852, showBackground = true, locale = "zh")
@Composable
private fun DesignSystemPhonePreview() { LumenTheme(true) { DesignSystemPreview() } }
