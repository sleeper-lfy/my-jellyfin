package net.lumen.media

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Discovery is the Compose migration boundary; the rest of the app retains its View theme. */
private val DarkDiscoveryColors = darkColorScheme(
    primary = Color(0xff79d8ec), onPrimary = Color(0xff00363d),
    primaryContainer = Color(0xff174b55), onPrimaryContainer = Color(0xffb5eff7),
    secondary = Color(0xffa9cad1), onSecondary = Color(0xff12343b),
    secondaryContainer = Color(0xff29474f), onSecondaryContainer = Color(0xffc5e7ee),
    tertiary = Color(0xffa9cad1), onTertiary = Color(0xff12343b),
    tertiaryContainer = Color(0xff29474f), onTertiaryContainer = Color(0xffc5e7ee),
    background = Color(0xff0b1117), onBackground = Color(0xffeef3f5),
    surface = Color(0xff0b1117), onSurface = Color(0xffeef3f5),
    surfaceVariant = Color(0xff293640), onSurfaceVariant = Color(0xffbbc8cf),
    outline = Color(0xff89989f), outlineVariant = Color(0xff3e4b54),
    surfaceDim = Color(0xff0b1117), surfaceBright = Color(0xff34414a),
    surfaceContainerLowest = Color(0xff070d12), surfaceContainerLow = Color(0xff111b23),
    surfaceContainer = Color(0xff15212c), surfaceContainerHigh = Color(0xff1e2b35),
    surfaceContainerHighest = Color(0xff293640),
)

private val LightDiscoveryColors = lightColorScheme(
    primary = Color(0xff00505e), onPrimary = Color.White,
    primaryContainer = Color(0xffa8ecfa), onPrimaryContainer = Color(0xff001f27),
    secondary = Color(0xff4a6269), onSecondary = Color.White,
    secondaryContainer = Color(0xffcde7ef), onSecondaryContainer = Color(0xff062027),
    tertiary = Color(0xff4a6269), onTertiary = Color.White,
    tertiaryContainer = Color(0xffcde7ef), onTertiaryContainer = Color(0xff062027),
    background = Color(0xfff7fafc), onBackground = Color(0xff172126),
    surface = Color(0xfff7fafc), onSurface = Color(0xff172126),
    surfaceVariant = Color(0xffdbe5ea), onSurfaceVariant = Color(0xff404c52),
    outline = Color(0xff707d84), outlineVariant = Color(0xffbfc9ce),
    surfaceDim = Color(0xffd5dfe4), surfaceBright = Color(0xfff7fafc),
    surfaceContainerLowest = Color.White, surfaceContainerLow = Color(0xffeff5f8),
    surfaceContainer = Color(0xffe9f0f4), surfaceContainerHigh = Color(0xffe3eaee),
    surfaceContainerHighest = Color(0xffdce5ea),
)

private val DiscoveryTypography = Typography().let { defaults ->
    defaults.copy(
        titleLarge = defaults.titleLarge.copy(fontSize = 20.sp, lineHeight = 28.sp),
        bodyMedium = defaults.bodyMedium.copy(fontSize = 14.sp, lineHeight = 20.sp),
        labelLarge = defaults.labelLarge.copy(fontSize = 14.sp, lineHeight = 20.sp),
        bodySmall = defaults.bodySmall.copy(fontSize = 12.sp, lineHeight = 16.sp),
    )
}

private val DiscoveryShapes = Shapes(
    extraSmall = RoundedCornerShape(4.dp), small = RoundedCornerShape(8.dp),
    medium = RoundedCornerShape(12.dp), large = RoundedCornerShape(16.dp),
    extraLarge = RoundedCornerShape(28.dp),
)

internal object DiscoveryDimensions {
    val Page = 16.dp
    val GridGap = 12.dp
    val Gap = 8.dp
    val TouchTarget = 48.dp
    val SearchHeight = 56.dp
    val Icon = 24.dp
}

@Composable
fun DiscoveryTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkDiscoveryColors else LightDiscoveryColors,
        typography = DiscoveryTypography,
        shapes = DiscoveryShapes,
        content = content,
    )
}
