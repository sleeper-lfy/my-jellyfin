package net.lumen.media.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.PlayArrow
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import net.lumen.media.R
import net.lumen.media.ui.theme.AppDimensions
import net.lumen.media.ui.theme.LocalAppSpacing
import net.lumen.media.ui.theme.LumenTheme

@Composable
fun EmptyState(icon: ImageVector, message: String, modifier: Modifier = Modifier,
    supportingText: String? = null, actionLabel: String? = null, onAction: (() -> Unit)? = null) {
    require((actionLabel == null) == (onAction == null)) { "An empty-state action needs both a label and callback" }
    val spacing = LocalAppSpacing.current
    Column(modifier.fillMaxWidth().padding(spacing.xl), horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(spacing.md)) {
        Icon(icon, contentDescription = null, Modifier.size(AppDimensions.TouchTarget),
            tint = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(message, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurface,
            textAlign = TextAlign.Center)
        if (supportingText != null) Text(supportingText, style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
        if (actionLabel != null && onAction != null) AppTextButton(actionLabel, onAction)
    }
}

@Preview(name = "Empty state · Dark", showBackground = true, widthDp = 393)
@Composable
private fun EmptyDarkPreview() { LumenTheme(true) { Surface { EmptyExample() } } }

@Preview(name = "Empty state · Light", showBackground = true, widthDp = 393)
@Composable
private fun EmptyLightPreview() { LumenTheme(false) { Surface { EmptyExample() } } }

@Composable
internal fun EmptyExample() {
    EmptyState(Icons.Outlined.PlayArrow, stringResource(R.string.design_system_empty),
        supportingText = stringResource(R.string.design_system_empty_supporting),
        actionLabel = stringResource(R.string.design_system_select_movie), onAction = {})
}
