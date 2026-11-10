package net.lumen.media.ui.components

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.outlined.FavoriteBorder
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilledIconToggleButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import net.lumen.media.R
import net.lumen.media.ui.theme.AppDimensions
import net.lumen.media.ui.theme.LocalAppPosterColors
import net.lumen.media.ui.theme.LocalAppSpacing
import net.lumen.media.ui.theme.LumenTheme

/** Rendering state only. The caller owns fetching, decoding, retries and image-cache lifetimes. */
sealed interface PosterState {
    data object Loading : PosterState
    data object Failure : PosterState
    data class ReadyPainter(val painter: Painter) : PosterState
}

/** A reusable Material card with stable artwork geometry and a separate favourite action. */
@Composable
fun PosterCard(
    title: String,
    subtitle: String,
    posterState: PosterState,
    onClick: () -> Unit,
    isFavorite: Boolean,
    onFavoriteChange: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    favoriteEnabled: Boolean = true,
    posterContentDescription: String? = null,
    favoriteContentDescription: String? = null,
) {
    val spacing = LocalAppSpacing.current
    val colors = MaterialTheme.colorScheme
    val posterColors = LocalAppPosterColors.current
    val imageDescription = posterContentDescription ?: stringResource(R.string.design_system_card_poster_description, title)
    val favoriteDescription = favoriteContentDescription ?: stringResource(
        if (isFavorite) R.string.design_system_card_unfavorite else R.string.design_system_card_favorite, title)
    val imageStateDescription = stringResource(when (posterState) {
        PosterState.Loading -> R.string.design_system_card_loading
        PosterState.Failure -> R.string.design_system_card_failed
        is PosterState.ReadyPainter -> R.string.design_system_card_loaded
    })
    Card(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier,
        shape = MaterialTheme.shapes.medium,
        colors = CardDefaults.cardColors(containerColor = colors.surfaceContainer),
    ) {
        Column {
            Box(Modifier.fillMaxWidth().aspectRatio(AppDimensions.PosterRatio)
                .clip(MaterialTheme.shapes.medium)
                .semantics { contentDescription = imageDescription; stateDescription = imageStateDescription }) {
                when (posterState) {
                    is PosterState.ReadyPainter -> Image(posterState.painter, null,
                        Modifier.matchParentSize(), contentScale = ContentScale.Crop)
                    PosterState.Loading -> PosterShimmer(Modifier.matchParentSize())
                    PosterState.Failure -> Column(Modifier.matchParentSize().background(colors.surfaceContainerHigh),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(spacing.sm, Alignment.CenterVertically)) {
                        Icon(Icons.Outlined.Info, null, Modifier.size(AppDimensions.Icon), tint = colors.onSurfaceVariant)
                        Text(stringResource(R.string.design_system_card_failed),
                            style = MaterialTheme.typography.labelMedium, color = colors.onSurfaceVariant)
                    }
                }
                val scrim = colors.scrim.copy(alpha = AppDimensions.FavoriteScrimAlpha)
                FilledIconToggleButton(
                    checked = isFavorite,
                    onCheckedChange = onFavoriteChange,
                    enabled = enabled && favoriteEnabled,
                    modifier = Modifier.align(Alignment.TopEnd).padding(spacing.sm).size(AppDimensions.TouchTarget),
                    shape = MaterialTheme.shapes.extraLarge,
                    colors = IconButtonDefaults.filledIconToggleButtonColors(
                        containerColor = scrim, checkedContainerColor = scrim,
                        contentColor = posterColors.onScrim, checkedContentColor = posterColors.onScrim,
                        disabledContainerColor = scrim,
                        disabledContentColor = posterColors.onScrim.copy(alpha = .38f),
                    ),
                ) {
                    Icon(if (isFavorite) Icons.Filled.Favorite else Icons.Outlined.FavoriteBorder,
                        favoriteDescription, Modifier.size(AppDimensions.Icon))
                }
            }
            Column(Modifier.fillMaxWidth().padding(spacing.sm), verticalArrangement = Arrangement.spacedBy(spacing.xs)) {
                Text(title, style = MaterialTheme.typography.bodyMedium, color = colors.onSurface,
                    minLines = 2, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text(subtitle, style = MaterialTheme.typography.labelMedium, color = colors.onSurfaceVariant,
                    minLines = 1, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

@Composable
private fun PosterShimmer(modifier: Modifier = Modifier) {
    val colors = MaterialTheme.colorScheme
    val progress by rememberInfiniteTransition(label = "posterShimmer").animateFloat(
        initialValue = 0f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(AppDimensions.ShimmerDurationMillis, easing = LinearEasing), RepeatMode.Restart),
        label = "posterShimmerProgress",
    )
    BoxWithConstraints(modifier) {
        val density = LocalDensity.current
        val width = with(density) { maxWidth.toPx() }
        val height = with(density) { maxHeight.toPx() }
        val start = width * (progress * 3f - 1f)
        val base = colors.surfaceContainerHigh
        val highlight = lerp(base, colors.onSurface, .08f)
        Box(Modifier.matchParentSize().background(Brush.linearGradient(listOf(base, highlight, base),
            start = Offset(start, 0f), end = Offset(start + width, height))))
    }
}

@Composable
private fun PosterExamples() {
    val spacing = LocalAppSpacing.current
    val title = stringResource(R.string.design_system_card_preview_title)
    val subtitle = stringResource(R.string.design_system_card_preview_subtitle)
    Row(Modifier.padding(spacing.page), horizontalArrangement = Arrangement.spacedBy(spacing.md)) {
        PosterCard(title, subtitle, PosterState.ReadyPainter(painterResource(R.drawable.discovery_preview_coast)),
            {}, false, {}, Modifier.width(AppDimensions.PosterPreviewWidth))
        PosterCard(title, subtitle, PosterState.Failure, {}, true, {}, Modifier.width(AppDimensions.PosterPreviewWidth))
    }
}

@Preview(name = "Poster cards · Dark", showBackground = true, widthDp = 360)
@Composable
private fun PosterDarkPreview() { LumenTheme(darkTheme = true) { Surface { PosterExamples() } } }

@Preview(name = "Poster cards · Light", showBackground = true, widthDp = 360)
@Composable
private fun PosterLightPreview() { LumenTheme(darkTheme = false) { Surface { PosterExamples() } } }

@Preview(name = "Poster loading · Dark", showBackground = true, widthDp = 180)
@Composable
private fun PosterLoadingDarkPreview() {
    LumenTheme(darkTheme = true) { Surface { PosterCard(stringResource(R.string.design_system_card_preview_title),
        stringResource(R.string.design_system_card_preview_subtitle), PosterState.Loading, {}, false, {}) } }
}

@Preview(name = "Poster loading · Light", showBackground = true, widthDp = 180)
@Composable
private fun PosterLoadingLightPreview() {
    LumenTheme(darkTheme = false) { Surface { PosterCard(stringResource(R.string.design_system_card_preview_title),
        stringResource(R.string.design_system_card_preview_subtitle), PosterState.Loading, {}, false, {}) } }
}
