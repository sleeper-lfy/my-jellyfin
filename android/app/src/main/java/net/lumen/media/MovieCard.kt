package net.lumen.media

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
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilledIconToggleButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import net.lumen.media.ui.theme.AppDimensions
import net.lumen.media.ui.theme.LocalAppSpacing
import net.lumen.media.ui.theme.LocalAppPosterColors

@Composable
internal fun DiscoveryMovieCard(
    work: DiscoveryUiState.Work,
    loader: DiscoveryImageLoader?,
    active: Boolean,
    imageEpoch: Int,
    onOpen: () -> Unit,
    onFavorite: () -> Unit,
    modifier: Modifier = Modifier,
    previewPainter: Painter? = null,
) {
    var poster by remember(work.cover, loader) { mutableStateOf<PosterLoadState>(PosterLoadState.Loading) }
    DisposableEffect(work.cover, loader, active, imageEpoch) {
        val request = if (active && loader != null) loader.load(work.cover) { poster = it } else null
        onDispose { request?.close() }
    }
    val colors = MaterialTheme.colorScheme
    Card(
        onClick = onOpen,
        modifier = modifier.fillMaxWidth().testTag("discoveryMovie:${work.id}"),
        shape = MaterialTheme.shapes.medium,
        colors = CardDefaults.cardColors(containerColor = colors.surface.copy(alpha = 0f)),
    ) {
        Column {
            Box(
                modifier = Modifier.fillMaxWidth().aspectRatio(AppDimensions.PosterRatio)
                    .clip(MaterialTheme.shapes.medium).background(colors.surfaceContainerHighest)
                    .testTag("discoveryPoster:${work.id}"),
            ) {
                val description = stringResource(R.string.discovery_poster_description, work.title)
                when {
                    previewPainter != null -> Image(previewPainter, description, Modifier.matchParentSize(), contentScale = ContentScale.Crop)
                    poster is PosterLoadState.Ready -> Image(
                        (poster as PosterLoadState.Ready).bitmap.asImageBitmap(), description,
                        Modifier.matchParentSize(), contentScale = ContentScale.Crop,
                    )
                    else -> DiscoveryPosterPlaceholder(work.title, poster == PosterLoadState.Loading)
                }
                FilledIconToggleButton(
                    checked = work.favorite,
                    onCheckedChange = { onFavorite() },
                    enabled = !work.pending,
                    modifier = Modifier.align(Alignment.TopEnd).padding(LocalAppSpacing.current.sm).size(AppDimensions.TouchTarget)
                        .testTag("discoveryFavorite:${work.id}"),
                    shape = MaterialTheme.shapes.extraLarge,
                    colors = IconButtonDefaults.filledIconToggleButtonColors(
                        containerColor = colors.surface.copy(alpha = 0f),
                        contentColor = LocalAppPosterColors.current.onScrimUnselected,
                        checkedContainerColor = colors.surface.copy(alpha = 0f),
                        checkedContentColor = LocalAppPosterColors.current.onScrim,
                        disabledContainerColor = colors.surface.copy(alpha = 0f),
                    ),
                ) {
                    Surface(Modifier.size(AppDimensions.ButtonVisualHeight), shape = MaterialTheme.shapes.extraLarge,
                        color = colors.scrim.copy(alpha = AppDimensions.FavoriteScrimAlpha)) {
                        Box(contentAlignment = Alignment.Center) {
                            Icon(if (work.favorite) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                                stringResource(if (work.favorite) R.string.discovery_remove_favorite else R.string.discovery_add_favorite, work.title),
                                Modifier.size(AppDimensions.SmallIcon))
                        }
                    }
                }
            }
            Column(Modifier.padding(top = LocalAppSpacing.current.sm), verticalArrangement = Arrangement.spacedBy(LocalAppSpacing.current.xs)) {
                Text(work.title, style = MaterialTheme.typography.bodyMedium, color = colors.onSurface,
                    maxLines = 2, minLines = 2, overflow = TextOverflow.Ellipsis)
                Text(discoveryMetadata(work), style = MaterialTheme.typography.labelMedium,
                    color = colors.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                work.rating?.let { rating ->
                    Text(stringResource(R.string.discovery_personal_rating, rating),
                        style = MaterialTheme.typography.labelMedium, color = colors.onSurfaceVariant)
                }
            }
        }
    }
}

@Composable
private fun discoveryMetadata(work: DiscoveryUiState.Work): String {
    val kind = when (work.kind) {
        "movie" -> stringResource(R.string.discovery_kind_movie)
        "series" -> stringResource(R.string.discovery_kind_series)
        "vr" -> stringResource(R.string.discovery_kind_vr)
        "fans" -> stringResource(R.string.discovery_kind_fans)
        "other" -> stringResource(R.string.discovery_kind_other)
        else -> ""
    }
    val source = work.communityRating?.let { stringResource(R.string.discovery_source_rating, it) }.orEmpty()
    return listOf(work.year, kind, source).filter { it.isNotEmpty() }
        .joinToString(stringResource(R.string.discovery_metadata_separator))
}

@Composable
private fun DiscoveryPosterPlaceholder(title: String, loading: Boolean) {
    val description = if (loading) stringResource(R.string.discovery_poster_loading, title)
        else stringResource(R.string.discovery_poster_failed)
    Box(Modifier.fillMaxWidth().aspectRatio(AppDimensions.PosterRatio)
        .then(if (loading) Modifier.discoveryShimmer() else Modifier.background(MaterialTheme.colorScheme.surfaceContainerHighest))
        .semantics { contentDescription = description }, contentAlignment = Alignment.Center) {
        if (!loading) {
            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(LocalAppSpacing.current.sm)) {
                Icon(Icons.Default.PlayArrow, null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(stringResource(R.string.discovery_poster_failed), style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
internal fun DiscoveryMovieSkeleton(modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().testTag("discoveryLoadingCard"), verticalArrangement = Arrangement.spacedBy(LocalAppSpacing.current.sm)) {
        DiscoveryPosterPlaceholder("", loading = true)
        Box(Modifier.fillMaxWidth().size(AppDimensions.TouchTarget).clip(MaterialTheme.shapes.small)
            .discoveryShimmer())
        Box(Modifier.fillMaxWidth(.6f).size(AppDimensions.Icon).clip(MaterialTheme.shapes.small)
            .discoveryShimmer())
    }
}

@Composable
private fun Modifier.discoveryShimmer(): Modifier {
    val progress = rememberInfiniteTransition(label = "posterLoading").animateFloat(
        initialValue = -1f, targetValue = 2f,
        animationSpec = infiniteRepeatable(tween(AppDimensions.ShimmerDurationMillis, easing = LinearEasing), RepeatMode.Restart),
        label = "posterHighlight",
    )
    val base = MaterialTheme.colorScheme.surfaceContainerHigh
    val highlight = MaterialTheme.colorScheme.surfaceContainerHighest
    return drawWithCache {
        onDrawBehind {
            val edge = size.width * progress.value
            drawRect(Brush.linearGradient(listOf(base, highlight, base),
                start = Offset(edge - size.width, 0f), end = Offset(edge + size.width, size.height)))
        }
    }
}

@Preview(name = "Movie card · Light", showBackground = true, widthDp = 180)
@Composable
private fun MovieCardLightPreview() {
    DiscoveryTheme(darkTheme = false) {
        DiscoveryMovieCard(discoveryPreviewState().items.first(), null, false, 0, {}, {}, previewPainter = painterResource(R.drawable.discovery_preview_coast))
    }
}

@Preview(name = "Movie card · Dark", showBackground = true, widthDp = 180)
@Composable
private fun MovieCardDarkPreview() {
    DiscoveryTheme(darkTheme = true) {
        DiscoveryMovieCard(discoveryPreviewState().items[1], null, false, 0, {}, {}, previewPainter = painterResource(R.drawable.discovery_preview_coast))
    }
}
