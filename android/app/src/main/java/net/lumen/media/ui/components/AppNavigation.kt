@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package net.lumen.media.ui.components

import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.TopAppBarScrollBehavior
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import net.lumen.media.R
import net.lumen.media.ui.theme.AppDimensions
import net.lumen.media.ui.theme.LocalAppSpacing
import net.lumen.media.ui.theme.LumenTheme

@Composable
fun AppTopBar(
    title: String,
    modifier: Modifier = Modifier,
    onBack: (() -> Unit)? = null,
    scrollBehavior: TopAppBarScrollBehavior? = null,
    actions: @Composable RowScope.() -> Unit = {},
) {
    TopAppBar(
        title = { Text(title, style = MaterialTheme.typography.titleLarge, maxLines = 1,
            overflow = TextOverflow.Ellipsis, modifier = Modifier.semantics { heading() }) },
        modifier = modifier,
        navigationIcon = {
            if (onBack != null) IconButton(onClick = onBack, modifier = Modifier.size(AppDimensions.TouchTarget)) {
                Icon(Icons.AutoMirrored.Outlined.ArrowBack,
                    contentDescription = stringResource(R.string.design_system_navigation_back),
                    modifier = Modifier.size(AppDimensions.Icon))
            }
        },
        actions = actions,
        colors = TopAppBarDefaults.topAppBarColors(
            containerColor = MaterialTheme.colorScheme.surface,
            scrolledContainerColor = MaterialTheme.colorScheme.surfaceContainer,
            navigationIconContentColor = MaterialTheme.colorScheme.onSurface,
            titleContentColor = MaterialTheme.colorScheme.onSurface,
            actionIconContentColor = MaterialTheme.colorScheme.onSurfaceVariant,
        ),
        scrollBehavior = scrollBehavior,
    )
}

@Composable
fun SectionHeader(
    title: String,
    modifier: Modifier = Modifier,
    onViewAll: (() -> Unit)? = null,
    viewAllLabel: String = stringResource(R.string.design_system_navigation_view_all),
) {
    Row(modifier.fillMaxWidth().heightIn(min = AppDimensions.TouchTarget),
        verticalAlignment = Alignment.CenterVertically) {
        Text(title, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurface,
            modifier = Modifier.weight(1f).semantics { heading() }, maxLines = 2, overflow = TextOverflow.Ellipsis)
        if (onViewAll != null) {
            Spacer(Modifier.width(LocalAppSpacing.current.md))
            TextButton(onClick = onViewAll, modifier = Modifier.heightIn(min = AppDimensions.TouchTarget)) {
                Text(viewAllLabel, style = MaterialTheme.typography.labelLarge)
            }
        }
    }
}

/** The existing four top-level destinations, without navigation or data-layer ownership. */
enum class AppDestination(val id: String, @StringRes val labelRes: Int) {
    Home("home", R.string.design_system_nav_home),
    Library("library", R.string.design_system_nav_library),
    Discover("discover", R.string.design_system_nav_discover),
    Mine("mine", R.string.design_system_nav_mine),
}

@Composable
private fun AppDestination.icon(selected: Boolean): ImageVector = when (this) {
    AppDestination.Home -> if (selected) AppIcons.HomeFilled else AppIcons.Home
    AppDestination.Library -> if (selected) AppIcons.LibraryFilled else AppIcons.Library
    AppDestination.Discover -> if (selected) AppIcons.DiscoverFilled else AppIcons.Discover
    AppDestination.Mine -> if (selected) AppIcons.MineFilled else AppIcons.Mine
}

@Composable
fun AppBottomNavigation(
    selected: AppDestination,
    onSelect: (AppDestination) -> Unit,
    modifier: Modifier = Modifier,
) {
    NavigationBar(modifier = modifier, containerColor = MaterialTheme.colorScheme.surfaceContainer) {
        AppDestination.entries.forEach { destination ->
            val isSelected = destination == selected
            NavigationBarItem(
                selected = isSelected,
                onClick = { onSelect(destination) },
                icon = { Icon(destination.icon(isSelected), contentDescription = null,
                    modifier = Modifier.size(AppDimensions.Icon)) },
                label = { Text(stringResource(destination.labelRes), style = MaterialTheme.typography.labelMedium,
                    maxLines = 1, overflow = TextOverflow.Ellipsis) },
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = MaterialTheme.colorScheme.onSecondaryContainer,
                    selectedTextColor = MaterialTheme.colorScheme.onSurface,
                    indicatorColor = MaterialTheme.colorScheme.secondaryContainer,
                    unselectedIconColor = MaterialTheme.colorScheme.onSurfaceVariant,
                    unselectedTextColor = MaterialTheme.colorScheme.onSurfaceVariant,
                ),
            )
        }
    }
}

/**
 * Insets are applied and consumed here exactly once, including the measured bars.
 * [content] receives the remaining content bounds: do not add Scaffold or system-bar padding again.
 * The Activity opts into edge-to-edge externally; this component never changes its Window.
 * Use the same [scrollBehavior] as [AppTopBar] to connect the content's nested scroll.
 */
@Composable
fun AppScreenScaffold(
    modifier: Modifier = Modifier,
    topBar: @Composable () -> Unit = {},
    bottomBar: @Composable () -> Unit = {},
    snackbarHost: @Composable () -> Unit = {},
    scrollBehavior: TopAppBarScrollBehavior? = null,
    imePadding: Boolean = false,
    contentWindowInsets: WindowInsets = WindowInsets.safeDrawing,
    content: @Composable BoxScope.() -> Unit,
) {
    val scrollModifier = if (scrollBehavior == null) modifier else modifier.nestedScroll(scrollBehavior.nestedScrollConnection)
    Scaffold(
        modifier = scrollModifier,
        topBar = topBar,
        bottomBar = bottomBar,
        snackbarHost = snackbarHost,
        containerColor = MaterialTheme.colorScheme.surface,
        contentColor = MaterialTheme.colorScheme.onSurface,
        contentWindowInsets = contentWindowInsets,
    ) { contentPadding ->
        Box(Modifier.fillMaxSize().padding(contentPadding).consumeWindowInsets(contentPadding)
            .then(if (imePadding) Modifier.imePadding() else Modifier), content = content)
    }
}

@Composable
internal fun TopBarExample() {
    AppTopBar(stringResource(R.string.design_system_navigation_preview_title), onBack = {}) {
        IconButton(onClick = {}, modifier = Modifier.size(AppDimensions.TouchTarget)) {
            Icon(AppIcons.Search, stringResource(R.string.design_system_icon_search), Modifier.size(AppDimensions.Icon))
        }
        IconButton(onClick = {}, modifier = Modifier.size(AppDimensions.TouchTarget)) {
            Icon(AppIcons.More, stringResource(R.string.design_system_icon_more), Modifier.size(AppDimensions.Icon))
        }
    }
}

@Composable
internal fun SectionHeaderExample() {
    SectionHeader(stringResource(R.string.design_system_navigation_preview_section), onViewAll = {},
        modifier = Modifier.padding(horizontal = LocalAppSpacing.current.page))
}

@Composable
internal fun BottomNavigationExample() { AppBottomNavigation(AppDestination.Home, {}) }

@Composable
internal fun ScaffoldExample() {
    val scroll = TopAppBarDefaults.enterAlwaysScrollBehavior()
    AppScreenScaffold(
        topBar = { AppTopBar(stringResource(R.string.design_system_navigation_preview_title), scrollBehavior = scroll) },
        bottomBar = { BottomNavigationExample() }, scrollBehavior = scroll, imePadding = true,
    ) {
        Text(stringResource(R.string.design_system_navigation_preview_content),
            style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(LocalAppSpacing.current.page))
    }
}

@Preview(name = "AppTopBar · Dark", showBackground = true)
@Composable private fun TopBarDarkPreview() { LumenTheme(true) { TopBarExample() } }
@Preview(name = "AppTopBar · Light", showBackground = true)
@Composable private fun TopBarLightPreview() { LumenTheme(false) { TopBarExample() } }
@Preview(name = "SectionHeader · Dark", showBackground = true)
@Composable private fun SectionHeaderDarkPreview() { LumenTheme(true) { Surface { SectionHeaderExample() } } }
@Preview(name = "SectionHeader · Light", showBackground = true)
@Composable private fun SectionHeaderLightPreview() { LumenTheme(false) { Surface { SectionHeaderExample() } } }
@Preview(name = "AppBottomNavigation · Dark", showBackground = true)
@Composable private fun BottomNavigationDarkPreview() { LumenTheme(true) { BottomNavigationExample() } }
@Preview(name = "AppBottomNavigation · Light", showBackground = true)
@Composable private fun BottomNavigationLightPreview() { LumenTheme(false) { BottomNavigationExample() } }
@Preview(name = "AppScreenScaffold · Dark", showBackground = true)
@Composable private fun ScaffoldDarkPreview() { LumenTheme(true) { ScaffoldExample() } }
@Preview(name = "AppScreenScaffold · Light", showBackground = true)
@Composable private fun ScaffoldLightPreview() { LumenTheme(false) { ScaffoldExample() } }
