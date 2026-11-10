package net.lumen.media.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.FavoriteBorder
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.InputChip
import androidx.compose.material3.InputChipDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.tooling.preview.Preview
import net.lumen.media.R
import net.lumen.media.ui.theme.AppDimensions
import net.lumen.media.ui.theme.LocalAppSpacing
import net.lumen.media.ui.theme.LumenTheme

/** The shared selection-chip entry point; labels and meaning always belong to the caller. */
@Composable
fun AppChip(
    label: String,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    leadingIcon: ImageVector? = null,
) = AppFilterChip(label, selected, onClick, modifier, enabled, leadingIcon)

/** A 32dp Material chip centred in a 48dp slot, retaining Material's expanded touch target. */
@Composable
fun AppFilterChip(
    label: String,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    leadingIcon: ImageVector? = null,
) {
    val colors = MaterialTheme.colorScheme
    val icon = if (selected) Icons.Outlined.Check else leadingIcon
    Box(modifier.sizeIn(minWidth = AppDimensions.TouchTarget, minHeight = AppDimensions.TouchTarget),
        contentAlignment = Alignment.Center) {
        FilterChip(
            selected = selected,
            onClick = onClick,
            enabled = enabled,
            modifier = Modifier.sizeIn(minHeight = AppDimensions.ChipHeight, maxHeight = AppDimensions.ChipHeight),
            label = { Text(label, style = MaterialTheme.typography.labelMedium) },
            leadingIcon = icon?.let { { Icon(it, null, Modifier.size(AppDimensions.ChipIcon)) } },
            shape = MaterialTheme.shapes.extraLarge,
            colors = FilterChipDefaults.filterChipColors(
                containerColor = colors.surface,
                labelColor = colors.onSurfaceVariant,
                iconColor = colors.onSurfaceVariant,
                selectedContainerColor = colors.secondaryContainer,
                selectedLabelColor = colors.onSecondaryContainer,
                selectedLeadingIconColor = colors.onSecondaryContainer,
            ),
            border = FilterChipDefaults.filterChipBorder(enabled, selected,
                borderColor = colors.outlineVariant, selectedBorderColor = colors.secondaryContainer),
        )
    }
}

/** Removable selection. Its entire chip is one Material action; the close icon is decorative. */
@Composable
fun AppInputChip(
    label: String,
    onRemove: () -> Unit,
    removeContentDescription: String,
    modifier: Modifier = Modifier,
    selected: Boolean = true,
    enabled: Boolean = true,
    leadingIcon: ImageVector? = null,
) {
    val colors = MaterialTheme.colorScheme
    val icon = if (selected) Icons.Outlined.Check else leadingIcon
    Box(modifier.sizeIn(minWidth = AppDimensions.TouchTarget, minHeight = AppDimensions.TouchTarget),
        contentAlignment = Alignment.Center) {
        InputChip(
            selected = selected,
            onClick = onRemove,
            enabled = enabled,
            modifier = Modifier.sizeIn(minHeight = AppDimensions.ChipHeight, maxHeight = AppDimensions.ChipHeight),
            label = { Text(label, style = MaterialTheme.typography.labelMedium) },
            leadingIcon = icon?.let { { Icon(it, null, Modifier.size(AppDimensions.ChipIcon)) } },
            trailingIcon = { Icon(Icons.Outlined.Close, removeContentDescription, Modifier.size(AppDimensions.ChipIcon)) },
            shape = MaterialTheme.shapes.extraLarge,
            colors = InputChipDefaults.inputChipColors(
                containerColor = colors.surface,
                labelColor = colors.onSurfaceVariant,
                leadingIconColor = colors.onSurfaceVariant,
                trailingIconColor = colors.onSurfaceVariant,
                selectedContainerColor = colors.secondaryContainer,
                selectedLabelColor = colors.onSecondaryContainer,
                selectedLeadingIconColor = colors.onSecondaryContainer,
                selectedTrailingIconColor = colors.onSecondaryContainer,
            ),
            border = InputChipDefaults.inputChipBorder(enabled, selected,
                borderColor = colors.outlineVariant, selectedBorderColor = colors.secondaryContainer),
        )
    }
}

@Composable
private fun ChipExamples() {
    val spacing = LocalAppSpacing.current
    val label = stringResource(R.string.design_system_card_preview_tag)
    Column(Modifier.padding(spacing.page), verticalArrangement = Arrangement.spacedBy(spacing.sm)) {
        AppChip(label, false, {}, leadingIcon = Icons.Outlined.FavoriteBorder)
        AppChip(label, true, {})
        AppInputChip(label, {}, stringResource(R.string.design_system_card_remove_tag, label))
        AppChip(label, false, {}, enabled = false)
    }
}

@Preview(name = "App chips · Dark", showBackground = true)
@Composable
private fun ChipsDarkPreview() { LumenTheme(darkTheme = true) { Surface { ChipExamples() } } }

@Preview(name = "App chips · Light", showBackground = true)
@Composable
private fun ChipsLightPreview() { LumenTheme(darkTheme = false) { Surface { ChipExamples() } } }
