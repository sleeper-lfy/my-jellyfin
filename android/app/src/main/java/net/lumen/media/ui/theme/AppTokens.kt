package net.lumen.media.ui.theme

import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

@Immutable
data class AppSpacing(
    val xs: Dp = 4.dp, val sm: Dp = 8.dp, val md: Dp = 12.dp,
    val lg: Dp = 16.dp, val xl: Dp = 24.dp, val page: Dp = 16.dp,
)

val LocalAppSpacing = staticCompositionLocalOf { AppSpacing() }

/** Sizes with semantic meaning; page code does not choose independent measurements. */
object AppDimensions {
    val TouchTarget = 48.dp
    val ChipHeight = 32.dp
    val ButtonHeight = 48.dp
    val ButtonVisualHeight = 32.dp
    val ButtonIcon = 18.dp
    val Icon = 24.dp
    val SmallIcon = 20.dp
    val ChipIcon = 18.dp
    val SearchHeight = 56.dp
    val SearchSuggestionsMaxHeight = 240.dp
    val Avatar = 56.dp
    val PlaybackButton = 64.dp
    val PosterPreviewWidth = 144.dp
    val PosterMetadataHeight = 56.dp
    val SheetHandleWidth = 40.dp
    val SheetHandleHeight = 4.dp
    val SheetMaxHeightFraction = .92f
    const val PosterRatio = 2f / 3f
    const val FavoriteScrimAlpha = .6f
    const val ShimmerDurationMillis = 1200
}
