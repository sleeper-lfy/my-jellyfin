package net.lumen.media.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.res.vectorResource
import androidx.compose.ui.tooling.preview.Preview
import net.lumen.media.R
import net.lumen.media.ui.theme.AppDimensions
import net.lumen.media.ui.theme.LocalAppSpacing
import net.lumen.media.ui.theme.LumenTheme

/** Official Material assets, with one distinct symbol for each application destination/action. */
object AppIcons {
    val Home: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_home)
    val Library: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_library)
    val Discover: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_discover)
    val Mine: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_mine)
    val Favorite: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_favorite)
    val Watchlist: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_watchlist)
    val SmartPlaylist: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_smart_playlist)
    val Statistics: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_statistics)
    val PhoneQueue: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_phone_queue)
    val Remote: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_remote)
    val Tasks: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_tasks)
    val Connections: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_connections)
    val Sort: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_sort)
    val Filter: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_filter)
    val Search: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_search)
    val More: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_more)

    val HomeFilled: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_home_filled)
    val LibraryFilled: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_library_filled)
    val DiscoverFilled: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_discover_filled)
    val MineFilled: ImageVector @Composable get() = ImageVector.vectorResource(R.drawable.design_system_mine_filled)
}

@Composable
internal fun IconExamples() {
    val icons = listOf(
        R.string.design_system_nav_home to AppIcons.Home,
        R.string.design_system_nav_library to AppIcons.Library,
        R.string.design_system_nav_discover to AppIcons.Discover,
        R.string.design_system_nav_mine to AppIcons.Mine,
        R.string.design_system_icon_favorite to AppIcons.Favorite,
        R.string.design_system_icon_watchlist to AppIcons.Watchlist,
        R.string.design_system_icon_smart_playlist to AppIcons.SmartPlaylist,
        R.string.design_system_icon_statistics to AppIcons.Statistics,
        R.string.design_system_icon_phone_queue to AppIcons.PhoneQueue,
        R.string.design_system_icon_remote to AppIcons.Remote,
        R.string.design_system_icon_tasks to AppIcons.Tasks,
        R.string.design_system_icon_connections to AppIcons.Connections,
        R.string.design_system_icon_sort to AppIcons.Sort,
        R.string.design_system_icon_filter to AppIcons.Filter,
        R.string.design_system_icon_search to AppIcons.Search,
        R.string.design_system_icon_more to AppIcons.More,
    )
    Column(verticalArrangement = Arrangement.spacedBy(LocalAppSpacing.current.lg)) {
        icons.chunked(4).forEach { group ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                group.forEach { (label, icon) ->
                    Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(LocalAppSpacing.current.xs)) {
                        // The adjacent label already names this non-interactive specimen.
                        Icon(icon, contentDescription = null, modifier = Modifier.size(AppDimensions.Icon))
                        Text(stringResource(label), style = MaterialTheme.typography.labelMedium)
                    }
                }
            }
        }
    }
}

@Preview(name = "AppIcons · Dark", showBackground = true)
@Composable
private fun IconsDarkPreview() { LumenTheme(true) { Surface { Column(Modifier.padding(LocalAppSpacing.current.page)) { IconExamples() } } } }

@Preview(name = "AppIcons · Light", showBackground = true)
@Composable
private fun IconsLightPreview() { LumenTheme(false) { Surface { Column(Modifier.padding(LocalAppSpacing.current.page)) { IconExamples() } } } }
