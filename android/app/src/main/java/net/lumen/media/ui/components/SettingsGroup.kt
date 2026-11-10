package net.lumen.media.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.material.icons.outlined.PlayArrow
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.tooling.preview.Preview
import net.lumen.media.R
import net.lumen.media.ui.theme.AppDimensions
import net.lumen.media.ui.theme.LocalAppSpacing
import net.lumen.media.ui.theme.LumenTheme

typealias SettingsContent = @Composable () -> Unit

/** One surface per group. The group owns separators, so pages never style individual rows. */
@Composable
fun SettingsGroup(items: List<SettingsContent>, modifier: Modifier = Modifier) {
    Surface(modifier, shape = MaterialTheme.shapes.medium,
        color = MaterialTheme.colorScheme.surfaceContainer) {
        Column {
            items.forEachIndexed { index, item ->
                if (index > 0) HorizontalDivider(
                    modifier = Modifier.padding(horizontal = LocalAppSpacing.current.lg),
                    color = MaterialTheme.colorScheme.outlineVariant)
                item()
            }
        }
    }
}

/** Trailing content is mutually exclusive: switch, value, navigation arrow, or information. */
@Composable
fun SettingsItem(title: String, leadingIcon: ImageVector, modifier: Modifier = Modifier,
    subtitle: String? = null, value: String? = null, onClick: (() -> Unit)? = null,
    checked: Boolean? = null, onCheckedChange: ((Boolean) -> Unit)? = null, enabled: Boolean = true) {
    require((checked == null) == (onCheckedChange == null)) { "Switch state and callback must be provided together" }
    require(checked == null || (value == null && onClick == null)) { "A switch row cannot also navigate or display a value" }
    val interactive = when {
        checked != null -> modifier.toggleable(checked, enabled, Role.Switch) { onCheckedChange?.invoke(it) }
        onClick != null -> modifier.clickable(enabled = enabled, role = Role.Button, onClick = onClick)
        else -> modifier
    }
    val foreground = if (enabled) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant
    ListItem(
        headlineContent = { Text(title, style = MaterialTheme.typography.bodyLarge) },
        modifier = interactive.heightIn(min = AppDimensions.TouchTarget),
        supportingContent = subtitle?.let { { Text(it, style = MaterialTheme.typography.bodyMedium) } },
        leadingContent = { Icon(leadingIcon, contentDescription = null, Modifier.size(AppDimensions.Icon)) },
        trailingContent = when {
            checked != null -> ({ Switch(checked, onCheckedChange = null, enabled = enabled,
                colors = SwitchDefaults.colors(
                    checkedThumbColor = MaterialTheme.colorScheme.onSecondaryContainer,
                    checkedTrackColor = MaterialTheme.colorScheme.secondaryContainer,
                    checkedBorderColor = MaterialTheme.colorScheme.outlineVariant)) })
            value != null -> ({ Text(value, style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant) })
            onClick != null -> ({ Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, contentDescription = null) })
            else -> null
        },
        colors = ListItemDefaults.colors(containerColor = MaterialTheme.colorScheme.surfaceContainer,
            headlineColor = foreground, leadingIconColor = MaterialTheme.colorScheme.onSurfaceVariant,
            supportingColor = MaterialTheme.colorScheme.onSurfaceVariant),
    )
}

@Preview(name = "Settings group · Dark", showBackground = true, widthDp = 393)
@Composable
private fun SettingsDarkPreview() { LumenTheme(true) { SettingsExamples() } }

@Preview(name = "Settings group · Light", showBackground = true, widthDp = 393)
@Composable
private fun SettingsLightPreview() { LumenTheme(false) { SettingsExamples() } }

@Composable
internal fun SettingsExamples() {
    SettingsGroup(listOf(
        { SettingsItem(stringResource(R.string.design_system_remote), AppIcons.Remote,
            subtitle = stringResource(R.string.design_system_remote_summary), onClick = {}) },
        { SettingsItem(stringResource(R.string.design_system_queue), AppIcons.PhoneQueue,
            value = stringResource(R.string.design_system_queue_value), onClick = {}) },
        { SettingsItem(stringResource(R.string.design_system_autoplay), Icons.Outlined.PlayArrow,
            checked = true, onCheckedChange = {}) },
    ))
}
