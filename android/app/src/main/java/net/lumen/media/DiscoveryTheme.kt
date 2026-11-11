package net.lumen.media

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import net.lumen.media.ui.theme.LumenTheme

internal object DiscoveryDimensions {
    val Page = 16.dp
    val GridGap = 12.dp
    val Gap = 8.dp
    val TouchTarget = 48.dp
    val SearchHeight = 56.dp
    val Icon = 24.dp
}

/** Discovery and native controls read the same application design system. */
@Composable
fun DiscoveryTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    LumenTheme(darkTheme, content)
}
