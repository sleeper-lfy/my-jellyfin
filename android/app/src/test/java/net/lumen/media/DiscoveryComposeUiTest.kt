package net.lumen.media

import android.content.Context
import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.Canvas
import android.util.LruCache
import android.util.DisplayMetrics
import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.width
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.compositeOver
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsNotDisplayed
import androidx.compose.ui.test.assertHasClickAction
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToIndex
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeUp
import androidx.compose.ui.test.swipeDown
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import java.io.File
import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.max
import kotlin.math.min
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.shadows.ShadowDialog
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import okio.Buffer
import net.lumen.media.ui.theme.AppDimensions
import net.lumen.media.ui.theme.AppPosterColors
import net.lumen.media.ui.theme.LocalAppPosterColors

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [33], qualifiers = "w393dp-h852dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class DiscoveryComposeUiTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()
    private val context: Context get() = ApplicationProvider.getApplicationContext()
    private fun work(index: Int, favorite: Boolean = false, pending: Boolean = false, cover: String = ""): DiscoveryUiState.Work {
        val title = context.getString(R.string.discovery_preview_movie_one) + " " + index
        return DiscoveryUiState.Work(JSONObject().put("id", index).put("title", title)
            .put("year", 2025).put("kind", "movie").put("community_rating", 8.4)
            .put("rating", 9).put("cover", cover).put("favorite", if (favorite) 1 else 0), pending)
    }
    private fun state(): DiscoveryUiState = DiscoveryUiState.Builder().apply {
        items = (1..20).map { work(it) }; total = items.size
    }.build()

    @Test fun materialFavoriteTouchIsFortyEightDpAndNeverOpensTheMovie() {
        val opened = AtomicInteger(); val favorites = AtomicInteger()
        val current = mutableStateOf(work(1))
        compose.setContent {
            DiscoveryTheme(false) {
                Column(Modifier.width(180.dp)) {
                    DiscoveryMovieCard(current.value, null, false, 0,
                        { opened.incrementAndGet() },
                        { favorites.incrementAndGet(); current.value = work(1, favorite = true) },
                        previewPainter = painterResource(R.drawable.discovery_preview_coast))
                }
            }
        }
        val favorite = compose.onNodeWithTag("discoveryFavorite:1")
        val size = favorite.getUnclippedBoundsInRoot()
        assertTrue(size.right - size.left >= 48.dp); assertTrue(size.bottom - size.top >= 48.dp)
        favorite.performClick()
        compose.runOnIdle { assertEquals(1, favorites.get()); assertEquals(0, opened.get()) }
        compose.runOnIdle { current.value = work(1, favorite = true, pending = true) }
        favorite.assertIsNotEnabled()
        compose.onNodeWithTag("discoveryMovie:1").performClick()
        compose.runOnIdle { assertEquals(1, opened.get()); assertEquals(1, favorites.get()) }
    }

    @Test fun lightScreenUsesMaterialInsetsAndKeepsLastTitleAboveNavigation() { verifyScreen(false) }
    @Test fun darkScreenUsesMaterialInsetsAndKeepsLastTitleAboveNavigation() { verifyScreen(true) }

    @Test @Config(sdk = [33], qualifiers = "w320dp-h720dp-mdpi")
    fun narrowLargeTextKeepsSearchSortTargetsAndTheLastCardInsideTheViewport() {
        val resources = compose.activity.resources
        val configuration = Configuration(resources.configuration).apply { fontScale = 1.5f }
        val metrics = DisplayMetrics().apply { setTo(resources.displayMetrics); scaledDensity = density * 1.5f }
        resources.updateConfiguration(configuration, metrics)
        val sorted = mutableListOf<String>(); val openedFilters = AtomicInteger()
        val data = DiscoveryUiState.Builder().apply {
            items = (1..20).map { work(it) }; total = items.size; sortField = "site_added"
        }.build()
        val callbacks = object : DiscoveryCallbacks by PreviewDiscoveryCallbacks {
            override fun onSelectSort(field: String) { sorted += field }
            override fun onOpenFilters() { openedFilters.incrementAndGet() }
        }
        var renderedFontScale = 0f
        compose.setContent { DiscoveryTheme(true) {
            renderedFontScale = LocalDensity.current.fontScale
            DiscoveryScreen(data, callbacks, previewPainter = painterResource(R.drawable.discovery_preview_coast))
        } }
        compose.runOnIdle { assertEquals(1.5f, renderedFontScale, .01f) }
        val search = compose.onNodeWithTag("discoverySearch").getUnclippedBoundsInRoot()
        val filterButton = compose.onNodeWithTag("discoveryFilter").assertHasClickAction()
        val filter = filterButton.getUnclippedBoundsInRoot()
        val sort = compose.onNodeWithTag("discoverySort").assertHasClickAction().getUnclippedBoundsInRoot()
        val count = compose.onNodeWithText(context.getString(R.string.discovery_results_count, data.total)).getUnclippedBoundsInRoot()
        assertTrue("SearchBar bounds=$search must retain 56dp input height", search.bottom - search.top >= 56.dp)
        assertTrue("filter clickable bounds=$filter must be at least 48dp wide", filter.right - filter.left >= 48.dp)
        assertTrue("filter clickable bounds=$filter must be at least 48dp high", filter.bottom - filter.top >= 48.dp)
        assertTrue("sort clickable bounds=$sort must be at least 48dp wide", sort.right - sort.left >= 48.dp)
        assertTrue("sort clickable bounds=$sort must be at least 48dp high", sort.bottom - sort.top >= 48.dp)
        assertTrue(filter.left >= search.left && filter.right <= search.right)
        assertTrue(search.left >= 0.dp && search.right <= 320.dp)
        assertTrue("count and sort must not overlap with enlarged text", count.right <= sort.left)
        assertTrue(sort.right <= 320.dp)
        screenshot("discovery-compose-narrow-large-text.png")
        compose.onNodeWithTag("discoverySort").performClick()
        val selectedSort = context.getString(R.string.discovery_sort_selected,
            context.getString(R.string.discovery_sort_site_added), context.getString(R.string.discovery_sort_descending))
        compose.onNodeWithContentDescription(selectedSort).performClick()
        compose.runOnIdle { assertEquals(listOf("site_added"), sorted); assertEquals(0, openedFilters.get()) }
        filterButton.performClick()
        compose.onNodeWithTag("filterForm").assertIsDisplayed()
        compose.runOnIdle { assertEquals(1, openedFilters.get()) }
        compose.onNodeWithTag("filterApply").performClick()
        compose.onNodeWithTag("discoveryGrid").performScrollToIndex(19)
        compose.onNodeWithText(data.items.last().title, useUnmergedTree = true).assertIsDisplayed()
        val card = compose.onNodeWithTag("discoveryMovie:20").getUnclippedBoundsInRoot()
        val navigation = compose.onNodeWithTag("discoveryNavigation").getUnclippedBoundsInRoot()
        assertTrue("the entire last card must stay above navigation", card.bottom <= navigation.top)
        screenshot("discovery-compose-narrow-large-text-bottom.png")
    }

    @Test fun authenticatedBitmapAndFailureUseTheSameMaterialPosterBounds() {
        val png = Buffer(); Bitmap.createBitmap(24, 36, Bitmap.Config.ARGB_8888).apply { eraseColor(android.graphics.Color.BLUE) }
            .compress(Bitmap.CompressFormat.PNG, 100, png.outputStream())
        MockWebServer().use { server ->
            server.dispatcher = object : Dispatcher() {
                override fun dispatch(request: RecordedRequest): MockResponse {
                    assertEquals("Bearer abcdefghijklmnopqrstuvwxyz123456", request.getHeader("Authorization"))
                    return if (request.path == "/api/works/1/cover") MockResponse().setBody(png.clone()) else MockResponse().setResponseCode(404)
                }
            }; server.start()
            val requests = ImageRequests(LruCache<String, Bitmap>(8))
            val loader = DiscoveryImageLoader(context, Api(Connection(server.url("/").toString(), "abcdefghijklmnopqrstuvwxyz123456")), requests)
            val current = mutableStateOf(work(1, cover = "/api/works/1/cover"))
            try {
                compose.setContent { DiscoveryTheme(true) { Column(Modifier.width(180.dp)) {
                    DiscoveryMovieCard(current.value, loader, true, 0, {}, {})
                } } }
                val description = context.getString(R.string.discovery_poster_description, current.value.title)
                compose.waitUntil(6000) { compose.onAllNodesWithContentDescription(description, useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }
                compose.onNodeWithContentDescription(description, useUnmergedTree = true).assertIsDisplayed()
                val loaded = compose.onNodeWithTag("discoveryPoster:1", useUnmergedTree = true).getUnclippedBoundsInRoot()
                compose.runOnIdle { current.value = work(1, cover = "/api/works/2/cover") }
                val missing = context.getString(R.string.discovery_poster_failed)
                compose.waitUntil(6000) { compose.onAllNodesWithText(missing).fetchSemanticsNodes().isNotEmpty() }
                compose.onNodeWithText(missing).assertIsDisplayed()
                val failed = compose.onNodeWithTag("discoveryPoster:1", useUnmergedTree = true).getUnclippedBoundsInRoot()
                assertEquals(loaded, failed)
            } finally { requests.close() }
        }
    }

    @Test fun downwardScrollHidesBothBarsAndEditingSearchKeepsTheInputVisible() {
        compose.setContent { DiscoveryTheme(false) { DiscoveryScreen(state(), PreviewDiscoveryCallbacks,
            previewPainter = painterResource(R.drawable.discovery_preview_coast)) } }
        val grid = compose.onNodeWithTag("discoveryGrid")
        grid.performTouchInput { swipeUp() }
        compose.waitForIdle()
        compose.onNodeWithTag("discoverySearch").assertDoesNotExist()
        compose.onNodeWithTag("discoveryTopBar").assertIsNotDisplayed()
        grid.performTouchInput { swipeDown() }
        compose.waitForIdle()
        compose.onNodeWithTag("discoverySearch").assertIsDisplayed()
        compose.onNodeWithTag("discoveryTopBar").assertIsDisplayed()
        compose.onNode(hasSetTextAction()).performClick()
        grid.performTouchInput { swipeUp() }
        compose.waitForIdle()
        compose.onNodeWithTag("discoverySearch").assertIsDisplayed()
    }

    @Test fun typingShowsGroupedSuggestionsAndSelectingATagClosesSearch() {
        val tag = context.getString(R.string.discovery_preview_tag_two)
        val term = tag.take(1)
        val title = context.getString(R.string.discovery_preview_movie_two)
        val selected = mutableListOf<Pair<String, String>>()
        fun searching(query: String, chip: String? = null) = DiscoveryUiState.Builder().apply {
            items = (1..4).map { work(it) }; total = items.size
            this.query = query; suggestionQuery = query
            suggestions = listOf(DiscoveryUiState.Suggestion("title", title), DiscoveryUiState.Suggestion("tag", tag))
            if (chip != null) chips = listOf(DiscoveryUiState.Chip("tag", chip, chip))
        }.build()
        val current = mutableStateOf(searching(""))
        val callbacks = object : DiscoveryCallbacks by PreviewDiscoveryCallbacks {
            override fun onQueryChanged(value: String) { current.value = searching(value) }
            override fun onSelectSuggestion(group: String, value: String) {
                selected += group to value; current.value = searching("", value)
            }
        }
        compose.setContent { DiscoveryTheme(false) { DiscoveryScreen(current.value, callbacks,
            previewPainter = painterResource(R.drawable.discovery_preview_coast)) } }
        compose.onNode(hasSetTextAction()).performClick().performTextInput(term)
        compose.onNodeWithText(context.getString(R.string.discovery_search_title_group)).assertIsDisplayed()
        compose.onNodeWithText(title).assertIsDisplayed()
        compose.onNodeWithText(context.getString(R.string.discovery_search_tag_group)).performScrollTo().assertIsDisplayed()
        compose.onNodeWithText(tag).performScrollTo().assertIsDisplayed()
        screenshot("discovery-compose-search-suggestions.png")
        compose.onNodeWithText(tag).performClick()
        compose.runOnIdle { assertEquals(listOf("tag" to tag), selected) }
        compose.onNodeWithText(context.getString(R.string.discovery_search_tag_group)).assertDoesNotExist()
        compose.onNodeWithTag("discoveryChip:tag:$tag").assertIsDisplayed()
        compose.onNodeWithContentDescription(context.getString(R.string.discovery_more_action)).performClick()
        for (label in listOf(R.string.discovery_more_save_list, R.string.discovery_more_shuffle, R.string.discovery_more_phone_queue)) {
            compose.onNodeWithText(context.getString(label)).assertIsDisplayed()
        }
        compose.onNodeWithText(context.getString(R.string.discovery_more_phone_queue)).performClick()
    }

    @Test fun loadingEmptyErrorAndNormalStatesKeepClearAndRetryActionsAvailable() {
        val cleared = AtomicInteger(); val retried = AtomicInteger(); val sourceRetried = AtomicInteger()
        val current = mutableStateOf(DiscoveryUiState.Builder().apply { loading = true }.build())
        val callbacks = object : DiscoveryCallbacks by PreviewDiscoveryCallbacks {
            override fun onClearFilters() { cleared.incrementAndGet() }
            override fun onRefresh() { retried.incrementAndGet() }
            override fun onListAction(action: String) { if (action == "retry") sourceRetried.incrementAndGet() }
        }
        compose.setContent { DiscoveryTheme(true) { DiscoveryScreen(current.value, callbacks,
            previewPainter = painterResource(R.drawable.discovery_preview_coast)) } }
        assertTrue(compose.onAllNodesWithTag("discoveryLoadingCard").fetchSemanticsNodes().isNotEmpty())
        compose.onNodeWithText(context.getString(R.string.discovery_empty_title)).assertDoesNotExist()
        screenshot("discovery-compose-loading.png")
        compose.runOnIdle { current.value = DiscoveryUiState.empty() }
        compose.onNodeWithText(context.getString(R.string.discovery_empty_title)).assertIsDisplayed()
        compose.onNodeWithText(context.getString(R.string.discovery_empty_clear)).performClick()
        compose.runOnIdle { assertEquals(1, cleared.get()) }
        screenshot("discovery-compose-empty.png")
        compose.runOnIdle { current.value = DiscoveryUiState.Builder().apply {
            error = context.getString(R.string.discovery_load_error)
        }.build() }
        compose.onNodeWithText(context.getString(R.string.discovery_load_error)).assertIsDisplayed()
        compose.onNodeWithText(context.getString(R.string.discovery_retry)).performClick()
        compose.runOnIdle { assertEquals(1, retried.get()) }
        screenshot("discovery-compose-error.png")
        compose.runOnIdle { current.value = state() }
        compose.onNodeWithTag("discoveryMovie:1").assertIsDisplayed()
        compose.onNodeWithText(context.getString(R.string.discovery_empty_title)).assertDoesNotExist()
        screenshot("discovery-compose-restored.png")
        compose.runOnIdle { current.value = DiscoveryUiState.Builder().apply {
            items = (1..4).map { work(it) }; total = items.size
            statusError = context.getString(R.string.discovery_load_error)
        }.build() }
        compose.onNodeWithTag("discoveryMovie:1").assertIsDisplayed()
        compose.onNodeWithText(context.getString(R.string.discovery_source_error_details)).performClick()
        compose.onNodeWithText(context.getString(R.string.discovery_source_details_title)).assertIsDisplayed()
        compose.onNodeWithText(context.getString(R.string.discovery_source_retry)).performClick()
        compose.runOnIdle { assertEquals(1, sourceRetried.get()) }
        compose.runOnIdle { current.value = DiscoveryUiState.Builder().apply {
            items = (1..4).map { work(it) }; total = items.size; busy = true
            statusError = context.getString(R.string.discovery_load_error)
        }.build() }
        compose.onNodeWithText(context.getString(R.string.discovery_source_error_details)).performClick()
        compose.onNodeWithText(context.getString(R.string.discovery_source_retry)).assertIsNotEnabled()
        screenshot("discovery-compose-source-error.png")
        compose.onNodeWithText(context.getString(R.string.discovery_close)).performClick()
    }

    private fun verifyScreen(dark: Boolean) {
        val data = state(); var colors: ColorScheme? = null; var posterColors: AppPosterColors? = null
        compose.setContent {
            DiscoveryTheme(dark) {
                colors = MaterialTheme.colorScheme
                posterColors = LocalAppPosterColors.current
                DiscoveryScreen(data, PreviewDiscoveryCallbacks,
                    previewPainter = painterResource(R.drawable.discovery_preview_coast))
            }
        }
        compose.onNodeWithTag("discoverySearch").assertIsDisplayed()
        compose.onNodeWithTag("filterForm").assertDoesNotExist()
        val first = compose.onNodeWithTag("discoveryPoster:1", useUnmergedTree = true).getUnclippedBoundsInRoot()
        val second = compose.onNodeWithTag("discoveryPoster:2", useUnmergedTree = true).getUnclippedBoundsInRoot()
        val firstWidth = (first.right - first.left).value
        val firstHeight = (first.bottom - first.top).value
        val secondWidth = (second.right - second.left).value
        assertTrue(kotlin.math.abs(firstHeight - firstWidth * 1.5f) <= 1f)
        // GridCells.Fixed distributes an odd physical pixel between its two columns.
        assertEquals(firstWidth, secondWidth, 1f)
        assertEquals(12f, second.left.value - first.right.value, .1f)
        compose.runOnIdle { verifyContrast(requireNotNull(colors), requireNotNull(posterColors)) }
        screenshot(if (dark) "discovery-compose-dark.png" else "discovery-compose-light.png")
        compose.onNodeWithTag("discoveryGrid").performScrollToIndex(19)
        val title = data.items.last().title
        compose.onNodeWithText(title, useUnmergedTree = true).assertIsDisplayed()
        val bottomTitle = compose.onNodeWithText(title, useUnmergedTree = true).getUnclippedBoundsInRoot()
        val navigation = compose.onNodeWithTag("discoveryNavigation").getUnclippedBoundsInRoot()
        assertTrue("last title must remain above the navigation", bottomTitle.bottom <= navigation.top)
        screenshot(if (dark) "discovery-compose-dark-bottom.png" else "discovery-compose-light-bottom.png")
    }

    private fun verifyContrast(colors: ColorScheme, posterColors: AppPosterColors) {
        fun ratio(first: Color, second: Color): Float {
            val one = first.luminance(); val two = second.luminance()
            return (max(one, two) + .05f) / (min(one, two) + .05f)
        }
        assertTrue("body copy must meet AA", ratio(colors.onSurface, colors.surface) >= 4.5f)
        assertTrue("small supporting copy must meet AA", ratio(colors.onSurfaceVariant, colors.surface) >= 4.5f)
        assertTrue("primary button text must meet AA", ratio(colors.onPrimary, colors.primary) >= 4.5f)
        for (photo in listOf(Color.Black, Color.White)) {
            val button = colors.scrim.copy(alpha = AppDimensions.FavoriteScrimAlpha).compositeOver(photo)
            assertTrue("selected favorite must contrast against either photo extreme", ratio(posterColors.onScrim, button) >= 3f)
            assertTrue("unselected favorite must contrast against either photo extreme", ratio(posterColors.onScrimUnselected, button) >= 3f)
        }
    }

    private fun screenshot(name: String) {
        val directory = System.getenv("LUMEN_UI_SCREENSHOTS") ?: return
        val file = File(directory, name); file.parentFile?.mkdirs()
        val bitmap = compose.runOnIdle {
            val dialog = ShadowDialog.getLatestDialog()
            val view = if (dialog?.isShowing == true) dialog.window!!.decorView else compose.activity.window.decorView
            assertTrue("actual Compose window must have measured bounds", view.width > 0 && view.height > 0)
            Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888).also { result -> view.draw(Canvas(result)) }
        }
        val samples = mutableSetOf<Int>()
        for (y in 0 until bitmap.height step 7) for (x in 0 until bitmap.width step 7) samples += bitmap.getPixel(x, y)
        assertTrue("native window draw must include interface content rather than a blank surface", samples.size > 8)
        file.outputStream().use { bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
    }
}
