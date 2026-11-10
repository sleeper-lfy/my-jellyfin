package net.lumen.media

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Insets
import android.view.ViewGroup
import android.view.WindowInsets as AndroidWindowInsets
import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.ime
import androidx.compose.material3.Surface
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.junit4.StateRestorationTester
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.shadows.ShadowDialog
import java.io.File
import java.util.concurrent.atomic.AtomicInteger

/** Exercises the shipped Compose filter surface, not the retired View filter. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [33], qualifiers = "w393dp-h852dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class DiscoveryFilterBottomSheetTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    private class Calls : DiscoveryCallbacks {
        var applied: DiscoveryFilters? = null
        var applyCount = 0
        var refreshCount = 0
        override fun onApplyFilters(filters: DiscoveryFilters) { applied = filters; applyCount++ }
        override fun onRefreshProviders() { refreshCount++ }
        override fun onQueryChanged(value: String) = Unit
        override fun onSubmitSearch(value: String) = Unit
        override fun onSelectSuggestion(group: String, value: String) = Unit
        override fun onOpenFilters() = Unit
        override fun onSelectSort(field: String) = Unit
        override fun onRemoveChip(id: String, value: String) = Unit
        override fun onClearFilters() = Unit
        override fun onOpenMovie(id: Long) = Unit
        override fun onToggleFavorite(id: Long) = Unit
        override fun onLoadMore() = Unit
        override fun onRefresh() = Unit
        override fun onNavigatePrimary(page: String) = Unit
        override fun onListAction(action: String) = Unit
        override fun onScrollPosition(firstVisibleItem: Int, offset: Int) = Unit
    }

    private fun state(filters: DiscoveryFilters = DiscoveryFilters(), loading: Boolean = false, error: String = "", sources: Boolean = true): DiscoveryUiState {
        return DiscoveryUiState.Builder().also { builder ->
            builder.filters = filters
            builder.online = filters.online
            builder.facets = JSONObject().put("tags", JSONArray().put("海岸").put("旅行").put("自然"))
            builder.providerLoading = loading
            builder.providerError = error
            if (sources) builder.providers = JSONArray().put(JSONObject().put("id", "single-site").put("name", "测试站点").put("supports_tags", true))
        }.build()
    }

    private fun showContent(value: DiscoveryUiState, calls: Calls, dark: Boolean = true) {
        compose.setContent {
            DiscoveryTheme(darkTheme = dark) {
                Surface(Modifier.fillMaxSize()) { DiscoveryFilterContent(value, calls, {}) }
            }
        }
    }

    private fun reveal(tag: String): SemanticsNodeInteraction {
        compose.onNodeWithTag("filterForm").performScrollToNode(hasTestTag(tag))
        return compose.onNodeWithTag(tag)
    }

    private fun text(id: Int): String = compose.activity.getString(id)

    @Test fun multiSelectionAndPreferenceChangesStayDraftUntilApply() {
        val original = DiscoveryFilters().also { it.favorite = true; it.tagsAny = "剧情" }
        val calls = Calls()
        showContent(state(original), calls)
        reveal("filterTagChoice:海岸").performClick()
        reveal("filterTagSearch").performTextReplacement("旅")
        reveal("filterTagChoice:旅行").performClick()
        compose.runOnIdle {
            assertEquals("", original.tagsAll)
            assertTrue(original.favorite)
            assertNull(calls.applied)
        }
        reveal("filterDisliked").performClick()
        compose.onNodeWithTag("filterApply").performClick()
        compose.runOnIdle {
            val applied = checkNotNull(calls.applied)
            assertEquals("海岸,旅行", applied.tagsAll)
            assertEquals("剧情", applied.tagsAny)
            assertTrue(applied.disliked)
            assertFalse(applied.favorite)
            assertTrue(original.favorite)
            assertFalse(original.disliked)
            assertEquals(1, calls.applyCount)
        }
    }

    @Test fun dismissingTheActualModalDoesNotApplyOrMutateItsSource() {
        val original = DiscoveryFilters().also { it.actor = "原演员" }
        val calls = Calls()
        var open by mutableStateOf(true)
        var dismissed = 0
        compose.setContent {
            DiscoveryTheme(darkTheme = true) {
                if (open) DiscoveryFilterBottomSheet(state(original), calls) { open = false; dismissed++ }
            }
        }
        reveal("filterTagChoice:海岸").performClick()
        compose.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsActions.Dismiss))
            .onFirst().performSemanticsAction(SemanticsActions.Dismiss) { dismiss -> dismiss() }
        compose.waitUntil { !open }
        compose.runOnIdle {
            assertEquals(1, dismissed)
            assertEquals(0, calls.applyCount)
            assertEquals("", original.tagsAll)
            assertEquals("原演员", original.actor)
        }
        compose.onNodeWithTag("filterApply").assertDoesNotExist()
    }

    @Test fun resetClearsOnlyDraftFiltersAndKeepsTheOnlineSearchIdentity() {
        val original = DiscoveryFilters().also {
            it.online = true; it.provider = "single-site"; it.searchTag = "站点关键词"; it.hasResults = true
            it.tagsAll = "海岸"; it.tagsAny = "剧情"; it.tagsNot = "悬疑"; it.actor = "原演员"
            it.yearMin = "2020"; it.ratingMin = "8"; it.favorite = true; it.watch = "completed"
        }
        val calls = Calls()
        showContent(state(original), calls)
        compose.onNodeWithTag("filterReset").performClick()
        compose.runOnIdle {
            assertNull(calls.applied)
            assertEquals("海岸", original.tagsAll)
            assertTrue(original.favorite)
        }
        compose.onNodeWithTag("filterApply").performClick()
        compose.runOnIdle {
            val value = checkNotNull(calls.applied)
            assertTrue(value.online)
            assertEquals("single-site", value.provider)
            assertEquals("站点关键词", value.searchTag)
            assertTrue(value.hasResults)
            listOf(value.tag, value.tagsAll, value.tagsAny, value.tagsNot, value.actor, value.yearMin, value.yearMax, value.ratingMin, value.watch).forEach { assertEquals("", it) }
            assertFalse(value.favorite)
            assertFalse(value.disliked)
            assertFalse(value.wanted)
        }
    }

    @Test fun savedInstanceStateRestoresTheUnappliedDraftRatherThanTheOriginalFilters() {
        val original = DiscoveryFilters().also { it.actor = "原演员"; it.favorite = true }
        val calls = Calls()
        val restoration = StateRestorationTester(compose)
        restoration.setContent {
            DiscoveryTheme(darkTheme = true) {
                Surface(Modifier.fillMaxSize()) { DiscoveryFilterContent(state(original), calls, {}) }
            }
        }
        reveal("filterTagChoice:海岸").performClick()
        reveal("filterTagChoice:旅行").performClick()
        reveal("filterDisliked").performClick()
        reveal("filterActor").performTextReplacement("草稿演员")
        reveal("filterYearFrom").performTextReplacement("2018")
        reveal("filterTagSearch").performTextReplacement("海")
        compose.runOnIdle {
            assertEquals("", original.tagsAll)
            assertEquals("原演员", original.actor)
            assertEquals("", original.yearMin)
            assertTrue(original.favorite)
            assertEquals(0, calls.applyCount)
        }

        restoration.emulateSavedInstanceStateRestore()
        reveal("filterTagSearch").assertTextContains("海")
        reveal("filterTagChoice:海岸").assertIsSelected()
        reveal("filterTagSearch").performTextReplacement("")
        reveal("filterTagChoice:旅行").assertIsSelected()
        reveal("filterDisliked").assertIsSelected()
        reveal("filterFavorite").assertIsNotSelected()
        reveal("filterActor").assertTextContains("草稿演员")
        reveal("filterYearFrom").assertTextContains("2018")
        compose.runOnIdle {
            assertNull(calls.applied)
            assertEquals(0, calls.applyCount)
            assertEquals("", original.tagsAll)
            assertEquals("原演员", original.actor)
            assertEquals("", original.yearMin)
            assertTrue(original.favorite)
        }
    }

    @Test fun providerLoadingAndFailureNeverReplaceTheSelectedSiteWithAllSites() {
        val original = DiscoveryFilters().also { it.online = true; it.provider = "single-site"; it.searchTag = "海岸" }
        val calls = Calls()
        var current by mutableStateOf(state(original, loading = true, sources = false))
        compose.setContent {
            DiscoveryTheme(darkTheme = true) { Surface(Modifier.fillMaxSize()) { DiscoveryFilterContent(current, calls, {}) } }
        }
        reveal("discoveryProvider").assertIsNotEnabled()
        compose.onNodeWithText(text(R.string.discovery_filter_provider_loading)).assertExists()
        compose.onNodeWithTag("filterApply").performClick()
        compose.runOnIdle {
            assertEquals("single-site", calls.applied?.provider)
            current = state(original, error = "测试连接失败", sources = false)
        }
        reveal("discoveryProvider").assertIsNotEnabled()
        compose.onNodeWithText(text(R.string.discovery_filter_provider_error).substringBefore('%'), substring = true).assertExists()
        compose.onNodeWithText(text(R.string.discovery_filter_provider_refresh)).performClick()
        compose.runOnIdle { assertEquals(1, calls.refreshCount) }
        compose.onNodeWithTag("filterApply").performClick()
        compose.runOnIdle {
            assertEquals("single-site", calls.applied?.provider)
            assertEquals("海岸", calls.applied?.searchTag)
            assertEquals("single-site", original.provider)
        }
    }

    @Test fun invalidYearAndRatingKeepTheSheetOpenUntilTheUserCorrectsThem() {
        val original = DiscoveryFilters().also { it.yearMin = "2025"; it.yearMax = "2020" }
        val calls = Calls()
        showContent(state(original), calls)
        compose.onNodeWithTag("filterApply").performClick()
        reveal("filterYearFrom")
        compose.onNodeWithText(text(R.string.discovery_filter_error_range)).assertExists()
        compose.runOnIdle { assertNull(calls.applied) }
        reveal("filterYearFrom").performTextReplacement("20")
        compose.onNodeWithTag("filterApply").performClick()
        compose.onNodeWithText(text(R.string.discovery_filter_error_year)).assertExists()
        reveal("filterYearFrom").performTextReplacement("2019")
        reveal("filterRating").performTextReplacement("11")
        compose.onNodeWithTag("filterApply").performClick()
        compose.onNodeWithText(text(R.string.discovery_filter_error_rating)).assertExists()
        compose.runOnIdle { assertEquals(0, calls.applyCount) }
        reveal("filterRating").performTextReplacement("8")
        compose.onNodeWithTag("filterApply").performClick()
        compose.runOnIdle {
            assertEquals(1, calls.applyCount)
            assertEquals("2019", calls.applied?.yearMin)
            assertEquals("2020", calls.applied?.yearMax)
            assertEquals("8", calls.applied?.ratingMin)
            assertEquals("2025", original.yearMin)
        }
    }

    @Test @Config(qualifiers = "w640dp-h320dp-mdpi")
    fun shortWindowKeepsTheFooterVisibleWhileTheRealLazyFormScrolls() {
        val value = state()
        for (i in 0..40) value.facets.getJSONArray("tags").put("分类 $i")
        val calls = Calls()
        showContent(value, calls)
        val before = compose.onNodeWithTag("filterFooter").getUnclippedBoundsInRoot()
        reveal("filterAdvanced").performClick()
        reveal("filterRating").assertIsDisplayed()
        val footer = compose.onNodeWithTag("filterFooter").getUnclippedBoundsInRoot()
        val root = compose.onRoot().getUnclippedBoundsInRoot()
        assertEquals(before.bottom.value, footer.bottom.value, 1f)
        assertTrue("The footer must stay above the measured window edge", footer.bottom <= root.bottom)
        val apply = compose.onNodeWithTag("filterApply").getUnclippedBoundsInRoot()
        val reset = compose.onNodeWithTag("filterReset").getUnclippedBoundsInRoot()
        assertTrue((apply.bottom - apply.top).value >= 48f)
        assertTrue((reset.right - reset.left).value >= 48f)
        compose.onNodeWithTag("filterApply").assertIsDisplayed()
        compose.onNodeWithTag("filterReset").assertIsDisplayed()
    }

    @Test fun actualImeInsetsMoveTheFooterAndRestoreItAfterTheKeyboardHides() {
        val calls = Calls()
        val observedImeBottom = AtomicInteger()
        compose.setContent {
            DiscoveryTheme(darkTheme = true) {
                val density = LocalDensity.current
                val imeBottom = WindowInsets.ime.getBottom(density)
                SideEffect { observedImeBottom.set(imeBottom) }
                Box(Modifier.fillMaxSize()) { DiscoveryFilterBottomSheet(state(), calls, {}) }
            }
        }
        // Establish this simulated device's system bars before taking the
        // baseline; opening the IME must not introduce a new navigation inset.
        dispatchIme(0)
        compose.waitForIdle()
        val before = compose.onNodeWithTag("filterFooter").getUnclippedBoundsInRoot().bottom.value
        dispatchIme(300)
        compose.waitUntil { observedImeBottom.get() == 300 }
        compose.waitForIdle()
        val keyboard = compose.onNodeWithTag("filterFooter").getUnclippedBoundsInRoot().bottom.value
        val windowBottom = compose.onAllNodes(isRoot()).fetchSemanticsNodes().maxOf { it.boundsInRoot.bottom }
        assertTrue("Real Compose IME insets must move the footer", keyboard < before - 200)
        assertTrue("The action row must remain above the keyboard", keyboard <= windowBottom - 300)
        compose.onNodeWithTag("filterApply").assertIsDisplayed()
        dispatchIme(0)
        compose.waitUntil { observedImeBottom.get() == 0 }
        compose.waitForIdle()
        val restored = compose.onNodeWithTag("filterFooter").getUnclippedBoundsInRoot().bottom.value
        assertEquals(before, restored, 1f)
    }

    private fun dispatchIme(bottom: Int) {
        compose.runOnIdle {
            val content = compose.activity.findViewById<ViewGroup>(android.R.id.content)
            val root = content.getChildAt(0)
            val insets = AndroidWindowInsets.Builder()
                .setInsets(AndroidWindowInsets.Type.systemBars(), Insets.of(0, 24, 0, 24))
                .setInsets(AndroidWindowInsets.Type.ime(), Insets.of(0, 0, 0, bottom))
                .setVisible(AndroidWindowInsets.Type.ime(), bottom > 0)
                .build()
            root.dispatchApplyWindowInsets(insets)
            // ModalBottomSheet owns a Dialog window. Deliver the real inset
            // event there too; merely resizing the test's content proves nothing.
            val dialog = ShadowDialog.getLatestDialog()
            val dialogContent = dialog?.window?.decorView?.findViewById<ViewGroup>(android.R.id.content)
            dialogContent?.getChildAt(0)?.dispatchApplyWindowInsets(insets)
        }
    }

    @Test fun actualModalLightPreviewUsesTheSameInteractiveM3Surface() = preview(dark = false)
    @Test fun actualModalDarkPreviewUsesTheSameInteractiveM3Surface() = preview(dark = true)

    private fun preview(dark: Boolean) {
        val calls = Calls()
        compose.setContent {
            DiscoveryTheme(darkTheme = dark) {
                Box(Modifier.fillMaxSize()) { DiscoveryFilterBottomSheet(state(), calls, {}) }
            }
        }
        compose.onNodeWithTag("filterApply").assertIsDisplayed()
        compose.onNodeWithTag("filterReset").assertIsDisplayed()
        compose.runOnIdle {
            val directory = System.getenv("LUMEN_UI_SCREENSHOTS") ?: return@runOnIdle
            val view = checkNotNull(ShadowDialog.getLatestDialog()).window!!.decorView
            assertTrue(view.width > 0 && view.height > 0)
            val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
            view.draw(Canvas(bitmap))
            val name = if (dark) "discovery-compose-filter-dark.png" else "discovery-compose-filter-light.png"
            val file = File(directory, name).also { it.parentFile!!.mkdirs() }
            file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
            bitmap.recycle()
        }
    }
}
