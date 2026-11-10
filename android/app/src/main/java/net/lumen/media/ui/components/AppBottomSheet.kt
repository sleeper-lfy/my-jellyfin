package net.lumen.media.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import net.lumen.media.R
import net.lumen.media.ui.theme.AppDimensions
import net.lumen.media.ui.theme.LocalAppSpacing
import net.lumen.media.ui.theme.LumenTheme

/** A reset belongs in either the title row or footer, never in both. */
enum class SheetResetPlacement { Header, Footer }

/** Material 3 sheet chrome only; callers own all draft values and apply behavior. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AppBottomSheet(
    title: String,
    onDismiss: () -> Unit,
    onReset: () -> Unit,
    onApply: () -> Unit,
    modifier: Modifier = Modifier,
    applyLabel: String = stringResource(R.string.design_system_sheet_apply),
    resetLabel: String = stringResource(R.string.design_system_sheet_reset),
    resetEnabled: Boolean = true,
    applyEnabled: Boolean = true,
    resetPlacement: SheetResetPlacement = SheetResetPlacement.Footer,
    content: LazyListScope.() -> Unit,
) {
    val spacing = LocalAppSpacing.current
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        modifier = modifier,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        shape = MaterialTheme.shapes.large,
        containerColor = MaterialTheme.colorScheme.surfaceContainer,
        contentWindowInsets = { WindowInsets.safeDrawing },
        dragHandle = {
            // The standard DragHandle includes large vertical padding. Keep
            // the same decorative cue compact; the sheet owns drag semantics.
            Surface(
                modifier = Modifier.padding(vertical = spacing.sm).size(
                    width = AppDimensions.SheetHandleWidth,
                    height = AppDimensions.SheetHandleHeight,
                ),
                shape = MaterialTheme.shapes.small,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                content = {},
            )
        },
    ) {
        AppBottomSheetContent(
            title = title,
            onReset = onReset,
            onApply = onApply,
            applyLabel = applyLabel,
            resetLabel = resetLabel,
            resetEnabled = resetEnabled,
            applyEnabled = applyEnabled,
            resetPlacement = resetPlacement,
            content = content,
        )
    }
}

/** Inline sheet content for previews and reuse; it uses the same real footer. */
@Composable
fun AppBottomSheetContent(
    title: String,
    onReset: () -> Unit,
    onApply: () -> Unit,
    modifier: Modifier = Modifier,
    applyLabel: String = stringResource(R.string.design_system_sheet_apply),
    resetLabel: String = stringResource(R.string.design_system_sheet_reset),
    resetEnabled: Boolean = true,
    applyEnabled: Boolean = true,
    resetPlacement: SheetResetPlacement = SheetResetPlacement.Footer,
    content: LazyListScope.() -> Unit,
) {
    val spacing = LocalAppSpacing.current
    Column(
        modifier.fillMaxWidth()
            .heightIn(max = LocalConfiguration.current.screenHeightDp.dp * AppDimensions.SheetMaxHeightFraction)
            .navigationBarsPadding()
            .imePadding(),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().heightIn(min = AppDimensions.TouchTarget)
                .padding(horizontal = spacing.page, vertical = spacing.sm),
            horizontalArrangement = Arrangement.spacedBy(spacing.md),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = title,
                modifier = Modifier.weight(1f),
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onSurface,
            )
            if (resetPlacement == SheetResetPlacement.Header) {
                AppTextButton(resetLabel, onReset, enabled = resetEnabled)
            }
        }
        LazyColumn(
            modifier = Modifier.weight(1f, fill = false).fillMaxWidth(),
            contentPadding = PaddingValues(horizontal = spacing.page, vertical = spacing.md),
            verticalArrangement = Arrangement.spacedBy(spacing.md),
            content = content,
        )
        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = spacing.page, vertical = spacing.md),
            horizontalArrangement = Arrangement.spacedBy(spacing.md),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (resetPlacement == SheetResetPlacement.Footer) {
                AppTextButton(resetLabel, onReset, Modifier.weight(1f), enabled = resetEnabled)
            }
            PrimaryButton(applyLabel, onApply, Modifier.weight(1f), enabled = applyEnabled)
        }
    }
}

@Composable
private fun BottomSheetContentPreview(dark: Boolean) {
    LumenTheme(darkTheme = dark) {
        Surface(color = MaterialTheme.colorScheme.surfaceContainer, shape = MaterialTheme.shapes.large) {
            AppBottomSheetContent(
                title = stringResource(R.string.design_system_sheet_preview_title),
                onReset = {},
                onApply = {},
            ) {
                item {
                    Text(
                        stringResource(R.string.design_system_sheet_preview_content),
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurface,
                    )
                }
            }
        }
    }
}

@Preview(name = "AppBottomSheet dark", locale = "zh", widthDp = 393, heightDp = 280, showBackground = true)
@Composable private fun AppBottomSheetDarkPreview() = BottomSheetContentPreview(dark = true)

@Preview(name = "AppBottomSheet light", locale = "zh", widthDp = 393, heightDp = 280, showBackground = true)
@Composable private fun AppBottomSheetLightPreview() = BottomSheetContentPreview(dark = false)
