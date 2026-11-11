package net.lumen.media.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// Shared by the Compose screens and the native Material component token bridge.
internal val DarkColors = darkColorScheme(
    primary = Color(0xff79d8ec), onPrimary = Color(0xff00363d),
    inversePrimary = Color(0xff00505e),
    primaryContainer = Color(0xff174b55), onPrimaryContainer = Color(0xffb5eff7),
    secondary = Color(0xffc0c8cd), onSecondary = Color(0xff293238),
    secondaryContainer = Color(0xff303c43), onSecondaryContainer = Color(0xffe0e9ef),
    tertiary = Color(0xffc0c8cd), onTertiary = Color(0xff293238),
    tertiaryContainer = Color(0xff303c43), onTertiaryContainer = Color(0xffe0e9ef),
    surface = Color(0xff0b1117), onSurface = Color(0xffeef3f5),
    background = Color(0xff0b1117), onBackground = Color(0xffeef3f5),
    surfaceVariant = Color(0xff30363b), onSurfaceVariant = Color(0xffc3c6ca),
    outline = Color(0xff8f8f8f), outlineVariant = Color(0xff454545),
    surfaceDim = Color(0xff0b1117), surfaceBright = Color(0xff343b42),
    surfaceContainerLowest = Color(0xff080d12), surfaceContainerLow = Color(0xff111a22),
    surfaceContainer = Color(0xff18212a), surfaceContainerHigh = Color(0xff222c35),
    surfaceContainerHighest = Color(0xff2d3740),
)

internal val LightColors = lightColorScheme(
    primary = Color(0xff00505e), onPrimary = Color.White,
    inversePrimary = Color(0xff79d8ec),
    primaryContainer = Color(0xffa8ecfa), onPrimaryContainer = Color(0xff001f27),
    secondary = Color(0xff505d65), onSecondary = Color.White,
    secondaryContainer = Color(0xffdce5eb), onSecondaryContainer = Color(0xff172127),
    tertiary = Color(0xff505d65), onTertiary = Color.White,
    tertiaryContainer = Color(0xffdce5eb), onTertiaryContainer = Color(0xff172127),
    surface = Color(0xfff7fafc), onSurface = Color(0xff172126),
    background = Color(0xfff7fafc), onBackground = Color(0xff172126),
    surfaceVariant = Color(0xffe1e4e7), onSurfaceVariant = Color(0xff444a50),
    outline = Color(0xff737373), outlineVariant = Color(0xffc6c6c6),
    surfaceDim = Color(0xffd7dce0), surfaceBright = Color(0xfff7fafc),
    surfaceContainerLowest = Color.White, surfaceContainerLow = Color(0xfff0f4f7),
    surfaceContainer = Color(0xffeaf0f4), surfaceContainerHigh = Color(0xffe3e9ed),
    surfaceContainerHighest = Color(0xffdce2e6),
)

internal val AppTypography = Typography().let { base ->
    base.copy(
        titleLarge = base.titleLarge.copy(fontSize = 22.sp, lineHeight = 28.sp, fontWeight = FontWeight.Normal),
        titleMedium = base.titleMedium.copy(fontSize = 16.sp, lineHeight = 24.sp, fontWeight = FontWeight.SemiBold),
        bodyLarge = base.bodyLarge.copy(fontSize = 16.sp, lineHeight = 24.sp),
        bodyMedium = base.bodyMedium.copy(fontSize = 14.sp, lineHeight = 20.sp),
        labelMedium = base.labelMedium.copy(fontSize = 12.sp, lineHeight = 16.sp),
    )
}

internal val AppShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp), small = RoundedCornerShape(8.dp),
    medium = RoundedCornerShape(12.dp), large = RoundedCornerShape(16.dp),
    extraLarge = RoundedCornerShape(28.dp),
)

/** Shared design foundation; callers explicitly opt in at their approved migration stage. */
@Composable
fun LumenTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val scheme = if (darkTheme) DarkColors else LightColors
    CompositionLocalProvider(LocalAppSpacing provides AppSpacing(),
        LocalAppPosterColors provides AppPosterColors(if (darkTheme) scheme.primary else scheme.inversePrimary,
            DarkColors.onSurface)) {
        MaterialTheme(colorScheme = scheme,
            typography = AppTypography, shapes = AppShapes, content = content)
    }
}

/** A semantic alias for an icon over a dark photo scrim, sourced from the M3 scheme. */
@Immutable
data class AppPosterColors(val onScrim: Color, val onScrimUnselected: Color = DarkColors.onSurface)

val LocalAppPosterColors = staticCompositionLocalOf { AppPosterColors(DarkColors.primary) }
