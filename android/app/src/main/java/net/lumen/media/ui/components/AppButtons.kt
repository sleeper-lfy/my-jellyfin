package net.lumen.media.ui.components

import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.PlayArrow
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.tooling.preview.Preview
import net.lumen.media.R
import net.lumen.media.ui.theme.AppDimensions
import net.lumen.media.ui.theme.LocalAppSpacing
import net.lumen.media.ui.theme.LumenTheme

@Composable
fun PrimaryButton(label: String, onClick: () -> Unit, modifier: Modifier = Modifier,
    enabled: Boolean = true, leadingIcon: ImageVector? = null) {
    ButtonTouchTarget(modifier) { visual ->
        Button(onClick, visual, enabled, shape = MaterialTheme.shapes.small,
            contentPadding = compactButtonPadding()) { ButtonLabel(label, leadingIcon) }
    }
}

@Composable
fun TonalButton(label: String, onClick: () -> Unit, modifier: Modifier = Modifier,
    enabled: Boolean = true, leadingIcon: ImageVector? = null) {
    ButtonTouchTarget(modifier) { visual ->
        FilledTonalButton(onClick, visual, enabled, shape = MaterialTheme.shapes.small,
            contentPadding = compactButtonPadding()) { ButtonLabel(label, leadingIcon) }
    }
}

@Composable
fun DangerButton(label: String, onClick: () -> Unit, modifier: Modifier = Modifier,
    enabled: Boolean = true, leadingIcon: ImageVector? = null) {
    ButtonTouchTarget(modifier) { visual ->
        Button(onClick, visual, enabled, shape = MaterialTheme.shapes.small,
            contentPadding = compactButtonPadding(),
            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error,
                contentColor = MaterialTheme.colorScheme.onError)) { ButtonLabel(label, leadingIcon) }
    }
}

@Composable
fun AppTextButton(label: String, onClick: () -> Unit, modifier: Modifier = Modifier,
    enabled: Boolean = true, leadingIcon: ImageVector? = null) {
    ButtonTouchTarget(modifier) { visual ->
        TextButton(onClick, visual, enabled, shape = MaterialTheme.shapes.small,
            contentPadding = compactButtonPadding()) { ButtonLabel(label, leadingIcon) }
    }
}

/** Keep the official Material hit expansion; only the painted container becomes compact. */
@Composable
private fun ButtonTouchTarget(modifier: Modifier, content: @Composable (Modifier) -> Unit) {
    Box(modifier.sizeIn(minWidth = AppDimensions.TouchTarget, minHeight = AppDimensions.ButtonHeight),
        contentAlignment = Alignment.Center, propagateMinConstraints = true) {
        // Reset vertical minimum only. A caller's weight/fill-width constraint still reaches the button.
        content(Modifier.wrapContentHeight().defaultMinSize(
            minWidth = AppDimensions.TouchTarget, minHeight = AppDimensions.ButtonVisualHeight))
    }
}

/** Adjacent actions reserve real external space; button content padding cannot replace it. */
@Composable
fun AppActionRow(modifier: Modifier = Modifier, content: @Composable RowScope.() -> Unit) {
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(LocalAppSpacing.current.md),
        verticalAlignment = Alignment.CenterVertically, content = content)
}

@Composable
private fun compactButtonPadding(): PaddingValues {
    val spacing = LocalAppSpacing.current
    return PaddingValues(horizontal = spacing.sm, vertical = spacing.xs)
}

@Composable
private fun ButtonLabel(label: String, leadingIcon: ImageVector?) {
    if (leadingIcon != null) {
        Icon(leadingIcon, contentDescription = null, modifier = Modifier.size(AppDimensions.ButtonIcon))
        Spacer(Modifier.width(LocalAppSpacing.current.xs))
    }
    Text(label, style = MaterialTheme.typography.labelLarge)
}

@Preview(name = "Buttons · Dark", showBackground = true)
@Composable
private fun ButtonsDarkPreview() { LumenTheme(true) { Surface { androidx.compose.foundation.layout.Box(Modifier.padding(LocalAppSpacing.current.page)) { ButtonExamples() } } } }

@Preview(name = "Buttons · Light", showBackground = true)
@Composable
private fun ButtonsLightPreview() { LumenTheme(false) { Surface { androidx.compose.foundation.layout.Box(Modifier.padding(LocalAppSpacing.current.page)) { ButtonExamples() } } } }

@Preview(name = "Action row · Dark", showBackground = true, widthDp = 393)
@Composable
private fun ActionRowDarkPreview() { LumenTheme(true) { ActionRowExample() } }

@Preview(name = "Action row · Light", showBackground = true, widthDp = 393)
@Composable
private fun ActionRowLightPreview() { LumenTheme(false) { ActionRowExample() } }

@Composable
private fun ActionRowExample() {
    Surface {
        AppActionRow(Modifier.padding(LocalAppSpacing.current.page)) {
            TonalButton(stringResource(R.string.design_system_previous_page), {})
            TonalButton(stringResource(R.string.design_system_next_page), {})
        }
    }
}

@Composable
internal fun ButtonExamples() {
    androidx.compose.foundation.layout.Column(verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(LocalAppSpacing.current.sm)) {
        PrimaryButton(stringResource(R.string.design_system_play), {}, leadingIcon = Icons.Outlined.PlayArrow)
        TonalButton(stringResource(R.string.design_system_favorite), {})
        DangerButton(stringResource(R.string.design_system_shutdown), {})
        AppTextButton(stringResource(R.string.design_system_reset), {})
        PrimaryButton(stringResource(R.string.design_system_apply), {}, enabled = false)
    }
}
