package net.lumen.media

import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.Canvas
import android.util.DisplayMetrics
import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.test.assertHasClickAction
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotSelected
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToIndex
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.unit.dp
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotSame
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.shadows.ShadowDialog

/** Integration snapshots for the approved refinement, separate from the foundation and business tests. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [33], qualifiers = "w393dp-h852dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class DiscoveryVisualRefinementTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    private fun filters() = DiscoveryFilters().apply {
        tag = "旅行"; actor = "示例演员"; yearMin = "2020"; yearMax = "2025"; ratingMin = "7"
        tagsAll = "海岸,自然"; tagsAny = "剧情,纪实"; tagsNot = "排除分类"; watch = "progress"
        provider = "chosen-site"; searchTag = "风景"; favorite = true; wanted = true; hasResults = true
    }

    private fun state(filters: DiscoveryFilters = DiscoveryFilters()) = DiscoveryUiState.Builder().apply {
        this.filters = filters; online = filters.online
        items = (1..16).map { index -> DiscoveryUiState.Work(JSONObject()
            .put("id", index).put("title", "海岸纪行 · 第 $index 章")
            .put("kind", if (index % 2 == 0) "vr" else "movie").put("year", 2025)
            .put("community_rating", 8.4).put("rating", 9).put("favorite", if (index == 2) 1 else 0), false) }
        total = items.size
        facets = JSONObject().put("tags", JSONArray().put("海岸").put("旅行").put("自然"))
        providers = JSONArray().put(JSONObject().put("id", "chosen-site").put("name", "示例搜索来源").put("supports_tags", true))
    }.build()

    private fun assertSameFiltersExceptMode(expected: DiscoveryFilters, actual: DiscoveryFilters) {
        assertEquals(expected.tag, actual.tag); assertEquals(expected.actor, actual.actor)
        assertEquals(expected.yearMin, actual.yearMin); assertEquals(expected.yearMax, actual.yearMax)
        assertEquals(expected.ratingMin, actual.ratingMin); assertEquals(expected.tagsAll, actual.tagsAll)
        assertEquals(expected.tagsAny, actual.tagsAny); assertEquals(expected.tagsNot, actual.tagsNot)
        assertEquals(expected.watch, actual.watch); assertEquals(expected.provider, actual.provider)
        assertEquals(expected.searchTag, actual.searchTag); assertEquals(expected.hasResults, actual.hasResults)
        assertEquals(expected.favorite, actual.favorite); assertEquals(expected.wanted, actual.wanted)
        assertEquals(expected.disliked, actual.disliked)
    }

    @Test fun sourceTabsEmitCopiedFiltersWithoutDroppingTheExistingScope() {
        val original = filters()
        val current = mutableStateOf(state(original))
        val submitted = mutableListOf<DiscoveryFilters>()
        val callbacks = object : DiscoveryCallbacks by PreviewDiscoveryCallbacks {
            override fun onApplyFilters(value: DiscoveryFilters) {
                submitted += value
                current.value = state(value)
            }
        }
        compose.setContent { DiscoveryTheme(true) {
            DiscoveryScreen(current.value, callbacks, previewPainter = painterResource(R.drawable.discovery_preview_coast))
        } }
        val local = compose.onNodeWithTag("discoveryScope:0").assertIsDisplayed().assertIsSelected()
        val online = compose.onNodeWithTag("discoveryScope:1").assertIsDisplayed().assertIsNotSelected()
        local.performClick()
        compose.runOnIdle { assertTrue("Reselecting the active scope must not resubmit it", submitted.isEmpty()) }
        online.performClick()
        compose.runOnIdle {
            assertEquals(1, submitted.size); assertNotSame(original, submitted.single())
            assertTrue(submitted.single().online); assertFalse(original.online)
            assertSameFiltersExceptMode(original, submitted.single())
        }
        online.assertIsSelected(); local.assertIsNotSelected()
        local.performClick()
        compose.runOnIdle {
            assertEquals(2, submitted.size); assertFalse(submitted.last().online)
            assertSameFiltersExceptMode(original, submitted.last())
            assertFalse(original.online)
        }
    }

    @Test fun realDarkDiscoveryMatchesTheApprovedLayoutAndKeepsTheLastCardVisible() = screen(dark = true)

    @Test fun realLightDiscoveryRetainsTheSameSourcesAndNavigationContracts() = screen(dark = false)

    private fun screen(dark: Boolean) {
        val data = state()
        compose.setContent { DiscoveryTheme(dark) {
            assertEquals("Discovery must use the shared accent", net.lumen.media.ui.theme.NativeActionTokens.primary(dark), MaterialTheme.colorScheme.primary.toArgb())
            assertEquals("Discovery must use the shared surfaces", net.lumen.media.ui.theme.NativeActionTokens.surfaceContainer(dark), MaterialTheme.colorScheme.surfaceContainer.toArgb())
            DiscoveryScreen(data, PreviewDiscoveryCallbacks, previewPainter = painterResource(R.drawable.discovery_preview_coast))
        } }
        compose.onNodeWithTag("discoveryScope:0").assertIsDisplayed().assertIsSelected()
        compose.onNodeWithTag("discoveryScope:1").assertIsDisplayed().assertHasClickAction()
        compose.onNodeWithTag("discoverySearch").assertIsDisplayed()
        compose.onNodeWithTag("filterForm").assertDoesNotExist()
        val first = compose.onNodeWithTag("discoveryPoster:1", useUnmergedTree = true).getUnclippedBoundsInRoot()
        val second = compose.onNodeWithTag("discoveryPoster:2", useUnmergedTree = true).getUnclippedBoundsInRoot()
        assertEquals(1.5f, (first.bottom - first.top).value / (first.right - first.left).value, .01f)
        assertEquals((first.right - first.left).value, (second.right - second.left).value, 1f)
        assertEquals(12f, (second.left - first.right).value, 1f)
        screenshot("bilibili-discovery-${if (dark) "dark" else "light"}-393.png")
        compose.onNodeWithTag("discoveryGrid").performScrollToIndex(data.items.lastIndex)
        compose.onNodeWithText(data.items.last().title, useUnmergedTree = true).assertIsDisplayed()
        val card = compose.onNodeWithTag("discoveryMovie:16").getUnclippedBoundsInRoot()
        val navigation = compose.onNodeWithTag("discoveryNavigation").getUnclippedBoundsInRoot()
        assertTrue("The last complete card must remain above bottom navigation: $card / $navigation", card.bottom <= navigation.top)
        screenshot("bilibili-discovery-${if (dark) "dark" else "light"}-393-bottom.png")
    }

    @Test @Config(qualifiers = "w320dp-h720dp-mdpi")
    fun narrowLargeTextKeepsBothSourceTabsAndEveryTopActionReachable() {
        val resources = compose.activity.resources
        val config = Configuration(resources.configuration).apply { fontScale = 1.5f }
        val metrics = DisplayMetrics().apply { setTo(resources.displayMetrics); scaledDensity = density * 1.5f }
        resources.updateConfiguration(config, metrics)
        val data = state(); var actualFontScale = 0f
        compose.setContent { DiscoveryTheme(true) {
            actualFontScale = LocalDensity.current.fontScale
            DiscoveryScreen(data, PreviewDiscoveryCallbacks, previewPainter = painterResource(R.drawable.discovery_preview_coast))
        } }
        compose.runOnIdle { assertEquals(1.5f, actualFontScale, .01f) }
        val local = compose.onNodeWithTag("discoveryScope:0").assertIsDisplayed().assertHasClickAction().getUnclippedBoundsInRoot()
        val online = compose.onNodeWithTag("discoveryScope:1").assertIsDisplayed().assertHasClickAction().getUnclippedBoundsInRoot()
        assertTrue(local.left >= 0.dp && online.right <= 320.dp)
        assertTrue("Source tabs must stay in the same row", kotlin.math.abs((local.top - online.top).value) <= 1f)
        assertTrue("Both source tabs need real 48dp touch height", local.bottom - local.top >= 48.dp && online.bottom - online.top >= 48.dp)
        for ((resource, tab) in listOf(R.string.discovery_filter_local to local, R.string.discovery_filter_online to online)) {
            val label = compose.activity.getString(resource)
            val node = compose.onNodeWithText(label, useUnmergedTree = true)
            val bounds = node.getUnclippedBoundsInRoot()
            val layouts = mutableListOf<TextLayoutResult>()
            node.performSemanticsAction(SemanticsActions.GetTextLayoutResult) { it(layouts) }
            val text = layouts.single()
            assertTrue("Source label must stay inside its touch target: $label / $bounds / $tab", bounds.left >= tab.left && bounds.right <= tab.right && bounds.top >= tab.top && bounds.bottom <= tab.bottom)
            assertFalse("Source label height must not be clipped: $label", text.didOverflowHeight)
            assertEquals("Every source-label character must remain visible", label.length, text.getLineEnd(text.lineCount - 1, visibleEnd = true))
            for (line in 0 until text.lineCount) {
                assertFalse("Source labels must not be ellipsized", text.isLineEllipsized(line))
                assertTrue("Source glyphs must fit the measured width", text.getLineLeft(line) >= 0f && text.getLineRight(line) <= text.size.width + 1f)
            }
        }
        val filter = compose.onNodeWithTag("discoveryFilter").assertIsDisplayed().assertHasClickAction().getUnclippedBoundsInRoot()
        val sort = compose.onNodeWithTag("discoverySort").assertIsDisplayed().assertHasClickAction().getUnclippedBoundsInRoot()
        for (bounds in listOf(filter, sort)) {
            assertTrue("Action must stay inside the narrow viewport: $bounds", bounds.left >= 0.dp && bounds.right <= 320.dp)
            assertTrue(bounds.right - bounds.left >= 48.dp && bounds.bottom - bounds.top >= 48.dp)
        }
        val count = compose.onNodeWithText(compose.activity.getString(R.string.discovery_results_count, data.total)).getUnclippedBoundsInRoot()
        assertTrue("Result count must not overlap sort at 1.5x", count.right <= sort.left)
        screenshot("bilibili-discovery-dark-320-font150.png")
        compose.onNodeWithTag("discoveryFilter").performClick()
        compose.onNodeWithTag("filterForm").assertIsDisplayed()
        screenshot("bilibili-discovery-filter-dark-320-font150.png")
        compose.onNodeWithTag("filterApply").assertIsDisplayed().performClick()
        compose.onNodeWithTag("discoveryGrid").performScrollToIndex(data.items.lastIndex)
        val bottom = compose.onNodeWithTag("discoveryMovie:16").getUnclippedBoundsInRoot()
        val navigation = compose.onNodeWithTag("discoveryNavigation").getUnclippedBoundsInRoot()
        assertTrue("Enlarged last card must not be covered by navigation", bottom.bottom <= navigation.top)
        screenshot("bilibili-discovery-dark-320-font150-bottom.png")
    }

    private fun screenshot(name: String) {
        val directory = System.getenv("LUMEN_UI_SCREENSHOTS") ?: return
        val bitmap = compose.runOnIdle {
            val dialog = ShadowDialog.getLatestDialog()
            val view = if (dialog?.isShowing == true) dialog.window!!.decorView else compose.activity.window.decorView
            assertTrue("Screenshot must come from a measured native window", view.width > 0 && view.height > 0)
            Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888).also { view.draw(Canvas(it)) }
        }
        val colors = mutableSetOf<Int>()
        for (y in 0 until bitmap.height step 7) for (x in 0 until bitmap.width step 7) colors += bitmap.getPixel(x, y)
        assertTrue("Screenshot must contain rendered controls and artwork", colors.size > 8)
        val file = File(directory, name); file.parentFile?.mkdirs()
        file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }
}
