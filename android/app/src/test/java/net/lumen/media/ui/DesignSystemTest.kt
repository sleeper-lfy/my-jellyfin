@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package net.lumen.media.ui

import android.graphics.Insets
import android.content.res.Configuration
import android.util.DisplayMetrics
import android.view.ViewGroup
import android.view.WindowInsets as AndroidWindowInsets
import androidx.activity.ComponentActivity
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CornerBasedShape
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Text
import androidx.compose.material3.Typography
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.compositeOver
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.VectorGroup
import androidx.compose.ui.graphics.vector.VectorPath
import androidx.compose.ui.graphics.painter.ColorPainter
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.max
import kotlin.math.min
import net.lumen.media.ui.components.*
import net.lumen.media.ui.theme.AppDimensions
import net.lumen.media.ui.theme.LocalAppSpacing
import net.lumen.media.ui.theme.LocalAppPosterColors
import net.lumen.media.ui.theme.LumenTheme
import net.lumen.media.ui.theme.enableLumenEdgeToEdge
import net.lumen.media.R
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.shadows.ShadowDialog

/** Stage 1 contracts only. No production screen, API client, or navigation state is instantiated. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [33], qualifiers = "w393dp-h852dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class DesignSystemTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Test fun darkThemeProvidesAccessibleRolesAndTheSharedTypeAndSpacingScale() = verifyTheme(true)
    @Test fun lightThemeProvidesAccessibleRolesAndNeutralOutlines() = verifyTheme(false)

    @Test fun compactButtonVisualsKeepExpandedPointerTargetsWithoutBubblingOrDisabledActions() {
        val primary = AtomicInteger(); val tonal = AtomicInteger(); val danger = AtomicInteger(); val text = AtomicInteger()
        val parent = AtomicInteger()
        compose.setContent {
            LumenTheme(true) {
                Column(Modifier.fillMaxSize().clickable { parent.incrementAndGet() }.padding(16.dp)) {
                    PrimaryButton("继续播放", { primary.incrementAndGet() }, Modifier.testTag("primary"), leadingIcon = AppIcons.More)
                    TonalButton("加入想看", { tonal.incrementAndGet() }, Modifier.testTag("tonal"))
                    DangerButton("关闭电脑", { danger.incrementAndGet() }, Modifier.testTag("danger"))
                    AppTextButton("清除条件", { text.incrementAndGet() }, Modifier.testTag("text"))
                    PrimaryButton("不可用", { primary.incrementAndGet() }, Modifier.testTag("disabled"), enabled = false)
                }
            }
        }
        for ((tag, label) in listOf("primary" to "继续播放", "tonal" to "加入想看", "danger" to "关闭电脑", "text" to "清除条件")) {
            val slot = compose.onNodeWithTag(tag, useUnmergedTree = true).getUnclippedBoundsInRoot()
            val visual = compose.onNode(hasText(label) and hasClickAction()).getUnclippedBoundsInRoot()
            val labelBounds = compose.onNodeWithText(label, useUnmergedTree = true).getUnclippedBoundsInRoot()
            assertTrue("$tag must reserve at least a 48dp touch slot", slot.bottom - slot.top >= 48.dp && slot.right - slot.left >= 48.dp)
            assertEquals("$tag visible surface must remain 32dp at the normal font size", 32f, (visual.bottom - visual.top).value, .1f)
            assertTrue(visual.top > slot.top && visual.bottom < slot.bottom)
            assertEquals("Horizontal content padding must be compact", 8f, (visual.right - labelBounds.right).value, .5f)
            assertEquals("Only an 18dp icon and 4dp gap precede the primary label", if (tag == "primary") 30f else 8f,
                (labelBounds.left - visual.left).value, .5f)
            assertTrue(labelBounds.top >= visual.top + 4.dp && labelBounds.bottom <= visual.bottom - 4.dp)
            // Pointer input six dp above and below the painted control must hit it, not the parent.
            for (edge in listOf(visual.top - 6.dp, visual.bottom + 6.dp)) {
                compose.onRoot().performTouchInput {
                    val x = with(compose.density) { ((visual.left + visual.right) / 2).toPx() }
                    val y = with(compose.density) { edge.toPx() }
                    click(Offset(x, y))
                }
            }
        }
        compose.onNodeWithText("不可用").assertIsNotEnabled().performTouchInput { click() }
        compose.runOnIdle {
            assertEquals(2, primary.get()); assertEquals(2, tonal.get())
            assertEquals(2, danger.get()); assertEquals(2, text.get()); assertEquals(0, parent.get())
        }
    }

    @Test @Config(qualifiers = "w320dp-h640dp-mdpi")
    fun compactActionRowSeparatesPagingTargetsAndContainsEnlargedButtonLabels() {
        val resources = compose.activity.resources
        resources.updateConfiguration(Configuration(resources.configuration).apply { fontScale = 1.5f },
            DisplayMetrics().apply { setTo(resources.displayMetrics); scaledDensity = density * 1.5f })
        val previous = AtomicInteger(); val next = AtomicInteger(); val played = AtomicInteger(); val shutdown = AtomicInteger(); val reset = AtomicInteger()
        var renderedScale = 0f
        compose.setContent { LumenTheme(true) {
            renderedScale = LocalDensity.current.fontScale
            Box(Modifier.fillMaxWidth().padding(LocalAppSpacing.current.page)) {
                Column {
                    AppActionRow(Modifier.testTag("pagingActions")) {
                        TonalButton("上一页任务", { previous.incrementAndGet() }, Modifier.testTag("previousAction"))
                        TonalButton("下一页任务", { next.incrementAndGet() }, Modifier.testTag("nextAction"))
                    }
                    PrimaryButton("继续播放", { played.incrementAndGet() }, Modifier.testTag("largePlay"), leadingIcon = AppIcons.More)
                    DangerButton("关闭电脑", { shutdown.incrementAndGet() }, Modifier.testTag("largeDanger"))
                    AppTextButton("清除条件", { reset.incrementAndGet() }, Modifier.testTag("largeText"))
                }
            }
        } }
        compose.runOnIdle { assertEquals(1.5f, renderedScale, .01f) }
        val row = compose.onNodeWithTag("pagingActions").getUnclippedBoundsInRoot()
        val first = compose.onNodeWithTag("previousAction").getUnclippedBoundsInRoot()
        val second = compose.onNodeWithTag("nextAction").getUnclippedBoundsInRoot()
        assertTrue("Adjacent clickable targets need external space", second.left - first.right >= 12.dp)
        for (bounds in listOf(first, second)) {
            assertTrue(bounds.right - bounds.left >= 48.dp && bounds.bottom - bounds.top >= 48.dp)
            assertTrue("Buttons must remain inside their row", bounds.top >= row.top && bounds.bottom <= row.bottom)
            assertTrue(bounds.left >= 0.dp && bounds.right <= 320.dp)
        }
        for ((tag, label) in listOf("previousAction" to "上一页任务", "nextAction" to "下一页任务",
            "largePlay" to "继续播放", "largeDanger" to "关闭电脑", "largeText" to "清除条件")) {
            val visual = compose.onNode(hasText(label) and hasClickAction()).getUnclippedBoundsInRoot()
            val slot = compose.onNodeWithTag(tag, useUnmergedTree = true).getUnclippedBoundsInRoot()
            val labelNode = compose.onNodeWithText(label, useUnmergedTree = true)
            val labelBounds = labelNode.getUnclippedBoundsInRoot()
            val layouts = mutableListOf<TextLayoutResult>()
            labelNode.performSemanticsAction(SemanticsActions.GetTextLayoutResult) { action -> action(layouts) }
            val textLayout = layouts.single()
            val diagnostic = "tag=$tag label=$label fontScale=$renderedScale textWidth=${textLayout.size.width} textHeight=${textLayout.size.height} " +
                "didOverflowWidth=${textLayout.didOverflowWidth} didOverflowHeight=${textLayout.didOverflowHeight} " +
                "lineCount=${textLayout.lineCount} constraints=${textLayout.layoutInput.constraints} " +
                "paragraphWidth=${textLayout.multiParagraph.width} paragraphHeight=${textLayout.multiParagraph.height} " +
                "paragraphWidthMinusSize=${textLayout.multiParagraph.width - textLayout.size.width} " +
                "paragraphHeightMinusSize=${textLayout.multiParagraph.height - textLayout.size.height} " +
                "lineLeft=${textLayout.getLineLeft(0)} lineRight=${textLayout.getLineRight(0)} " +
                "lineVisibleEnd=${textLayout.getLineEnd(0, visibleEnd = true)} lineEnd=${textLayout.getLineEnd(0)} " +
                "isLineEllipsized=${textLayout.isLineEllipsized(0)} " +
                "visual=$visual labelBounds=$labelBounds slot=$slot"
            assertEquals("Each action label must fit a single line on a 320dp display; $diagnostic", 1, textLayout.lineCount)
            // Text can retain a paragraph as wide as its available constraint while reporting its
            // wrapped content size. Verify the actual characters and line rather than that box width.
            assertTrue("Large action labels must retain their full line height; $diagnostic", !textLayout.didOverflowHeight)
            assertTrue("Large action labels must not be ellipsized; $diagnostic", !textLayout.isLineEllipsized(0))
            assertEquals("Every character of the action must remain visible; $diagnostic", label.length, textLayout.getLineEnd(0, visibleEnd = true))
            assertTrue("The rendered line must fit inside the measured text width; $diagnostic",
                textLayout.getLineLeft(0) >= 0f && textLayout.getLineRight(0) <= textLayout.size.width)
            label.indices.forEach { offset ->
                val character = textLayout.getBoundingBox(offset)
                assertTrue("Character $offset must remain inside the measured text bounds: $character; $diagnostic",
                    character.left >= 0f && character.right <= textLayout.size.width &&
                        character.top >= 0f && character.bottom <= textLayout.size.height)
            }
            assertTrue("The visual must grow with 1.5x text instead of clipping it at 32dp", visual.bottom - visual.top > 32.dp)
            assertTrue(labelBounds.top >= visual.top + 4.dp && labelBounds.bottom <= visual.bottom - 4.dp)
            assertTrue(labelBounds.left >= visual.left + 8.dp && labelBounds.right <= visual.right - 8.dp)
            assertTrue(visual.left >= slot.left && visual.right <= slot.right && visual.top >= slot.top && visual.bottom <= slot.bottom)
            compose.onRoot().performTouchInput {
                click(Offset(with(compose.density) { ((visual.left + visual.right) / 2).toPx() },
                    with(compose.density) { ((visual.top + visual.bottom) / 2).toPx() }))
            }
        }
        compose.runOnIdle { assertEquals(1, previous.get()); assertEquals(1, next.get()); assertEquals(1, played.get()); assertEquals(1, shutdown.get()); assertEquals(1, reset.get()) }
    }

    @Test fun actualModalKeepsResetAndApplyFixedWhileItsLongContentScrollsAndImeMoves() {
        val reset = AtomicInteger(); val apply = AtomicInteger()
        compose.setContent {
            LumenTheme(true) {
                AppBottomSheet("筛选", {}, { reset.incrementAndGet() }, { apply.incrementAndGet() },
                    applyLabel = "应用条件", resetLabel = "清空条件") {
                    items(40) { index -> Text("测试条件 $index", Modifier.fillMaxWidth().height(48.dp)) }
                }
            }
        }
        dispatchIme(0)
        compose.waitForIdle()
        val before = compose.onNodeWithText("应用条件").getUnclippedBoundsInRoot()
        compose.onNode(SemanticsMatcher.keyIsDefined(SemanticsActions.ScrollToIndex)).performScrollToIndex(39)
        compose.onNodeWithText("测试条件 39").assertIsDisplayed()
        val after = compose.onNodeWithText("应用条件").getUnclippedBoundsInRoot()
        assertEquals("Scrolling the form must not move its actions", before.bottom.value, after.bottom.value, 1f)
        compose.onNodeWithText("清空条件").performClick()
        compose.onNodeWithText("应用条件").performClick()
        compose.runOnIdle { assertEquals(1, reset.get()); assertEquals(1, apply.get()) }
        dispatchIme(300)
        compose.waitForIdle()
        val keyboard = compose.onNodeWithText("应用条件").getUnclippedBoundsInRoot()
        assertTrue("The actual dialog footer must move above a 300px IME", keyboard.bottom < before.bottom - 200.dp)
        compose.onNodeWithText("应用条件").assertIsDisplayed()
        dispatchIme(0)
        compose.waitForIdle()
        val restored = compose.onNodeWithText("应用条件").getUnclippedBoundsInRoot()
        assertEquals(before.bottom.value, restored.bottom.value, 1f)
    }

    @Test fun dismissingTheRealModalNeverRunsItsApplyCallback() {
        val open = mutableStateOf(true); val dismissed = AtomicInteger(); val applied = AtomicInteger()
        compose.setContent {
            LumenTheme(false) {
                if (open.value) AppBottomSheet("筛选", { open.value = false; dismissed.incrementAndGet() }, {},
                    { applied.incrementAndGet() }, applyLabel = "应用条件", resetLabel = "清空条件",
                    resetPlacement = SheetResetPlacement.Header) {
                    item { Text("尚未应用的内容") }
                }
            }
        }
        compose.onNodeWithText("尚未应用的内容").assertIsDisplayed()
        compose.onAllNodesWithText("清空条件").assertCountEquals(1)
        compose.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsActions.Dismiss)).onFirst()
            .performSemanticsAction(SemanticsActions.Dismiss) { dismiss -> dismiss() }
        compose.waitUntil { !open.value }
        compose.runOnIdle { assertEquals(1, dismissed.get()); assertEquals(0, applied.get()) }
        compose.onNodeWithText("应用条件").assertDoesNotExist()
    }

    @Test fun chipVisualsStayThirtyTwoDpWhileTheirOuterTouchEdgesRemainIndependent() {
        val selected = AtomicInteger(); val removed = AtomicInteger(); val parent = AtomicInteger()
        compose.setContent {
            LumenTheme(true) {
                Column(Modifier.fillMaxSize().clickable { parent.incrementAndGet() }.padding(16.dp)) {
                    AppChip("海岸", true, { selected.incrementAndGet() }, Modifier.testTag("filterSlot"))
                    AppInputChip("旅行", { removed.incrementAndGet() }, "移除旅行", Modifier.testTag("inputSlot"))
                    AppChip("不可选", false, { selected.incrementAndGet() }, enabled = false)
                }
            }
        }
        for ((slot, label) in listOf("filterSlot" to "海岸", "inputSlot" to "旅行")) {
            val outer = compose.onNodeWithTag(slot, useUnmergedTree = true).getUnclippedBoundsInRoot()
            val visual = compose.onNodeWithText(label).assertIsSelected().assertHasClickAction().getUnclippedBoundsInRoot()
            assertEquals("The visible Material chip must remain compact", 32f, (visual.bottom - visual.top).value, .1f)
            assertTrue(outer.bottom - outer.top >= 48.dp && outer.right - outer.left >= 48.dp)
            assertTrue(visual.top > outer.top && visual.bottom < outer.bottom)
            // Real pointer input outside the 32dp visual is stronger than invoking onClick semantics.
            compose.onRoot().performTouchInput {
                val x = with(compose.density) { ((outer.left + outer.right) / 2).toPx() }
                val y = with(compose.density) { (outer.top + 1.dp).toPx() }
                click(Offset(x, y))
            }
        }
        compose.onNodeWithText("不可选").assertIsNotEnabled()
        compose.runOnIdle { assertEquals(1, selected.get()); assertEquals(1, removed.get()); assertEquals(0, parent.get()) }
    }

    @Test fun groupedSettingsKeepEachActionIndependentAndSwitchTogglesOnlyOnce() {
        val navigation = AtomicInteger(); val toggle = AtomicInteger(); val checked = mutableStateOf(false)
        compose.setContent {
            LumenTheme(true) {
                SettingsGroup(listOf(
                    { SettingsItem("连接管理", AppIcons.Connections, subtitle = "管理家庭电脑", onClick = { navigation.incrementAndGet() }) },
                    { SettingsItem("自动连播", AppIcons.PhoneQueue, checked = checked.value,
                        onCheckedChange = { checked.value = it; toggle.incrementAndGet() }) },
                    { SettingsItem("应用版本", AppIcons.Tasks, value = "0.4.17") },
                ), Modifier.testTag("settingsGroup"))
            }
        }
        compose.onNodeWithText("连接管理").assertHasClickAction().performClick()
        compose.onNodeWithText("自动连播").assertIsOff().performClick().assertIsOn()
        compose.onNodeWithText("应用版本").assertHasNoClickAction()
        val group = compose.onNodeWithTag("settingsGroup").getUnclippedBoundsInRoot()
        val first = compose.onNodeWithText("连接管理").getUnclippedBoundsInRoot()
        val second = compose.onNodeWithText("自动连播").getUnclippedBoundsInRoot()
        assertTrue(first.top >= group.top && first.bottom <= second.top)
        assertTrue(second.bottom <= group.bottom)
        compose.runOnIdle { assertEquals(1, navigation.get()); assertEquals(1, toggle.get()) }
    }

    @Test fun emptyStateAddsAnActionOnlyWhenTheCallerProvidesOne() {
        val withAction = mutableStateOf(false); val acted = AtomicInteger()
        compose.setContent {
            LumenTheme(false) {
                EmptyState(AppIcons.Search, "暂时没有影片", supportingText = "更换条件后再试",
                    actionLabel = if (withAction.value) "清除条件" else null,
                    onAction = if (withAction.value) ({ acted.incrementAndGet(); Unit }) else null)
            }
        }
        compose.onNodeWithText("暂时没有影片").assertIsDisplayed()
        compose.onNodeWithText("更换条件后再试").assertIsDisplayed()
        compose.onNodeWithText("清除条件").assertDoesNotExist()
        compose.runOnIdle { withAction.value = true }
        compose.onNodeWithText("清除条件").performClick()
        compose.runOnIdle { assertEquals(1, acted.get()) }
    }

    @Test fun posterLoadingFailureAndReadyKeepTheSameTwoByThreeImageAndSeparateFavoriteAction() {
        val state = mutableStateOf<PosterState>(PosterState.Loading)
        val favorite = mutableStateOf(false); val available = mutableStateOf(true)
        val opened = AtomicInteger(); val changed = AtomicInteger()
        compose.setContent {
            LumenTheme(false) {
                PosterCard("海岸纪行：一段足够长的影片标题", "2025 · 电影", state.value,
                    { opened.incrementAndGet() }, favorite.value,
                    { favorite.value = it; changed.incrementAndGet() }, Modifier.width(180.dp).testTag("posterCard"),
                    favoriteEnabled = available.value, posterContentDescription = "测试影片封面", favoriteContentDescription = "收藏测试影片")
            }
        }
        val poster = compose.onNodeWithContentDescription("测试影片封面", useUnmergedTree = true)
        poster.assert(SemanticsMatcher.expectValue(androidx.compose.ui.semantics.SemanticsProperties.StateDescription,
            compose.activity.getString(R.string.design_system_card_loading)))
        val initial = poster.getUnclippedBoundsInRoot()
        val card = compose.onNodeWithTag("posterCard").getUnclippedBoundsInRoot()
        assertEquals((initial.right - initial.left).value * 1.5f, (initial.bottom - initial.top).value, .1f)
        compose.runOnIdle { state.value = PosterState.Failure }
        poster.assert(SemanticsMatcher.expectValue(androidx.compose.ui.semantics.SemanticsProperties.StateDescription,
            compose.activity.getString(R.string.design_system_card_failed)))
        assertEquals(initial, poster.getUnclippedBoundsInRoot())
        compose.runOnIdle { state.value = PosterState.ReadyPainter(ColorPainter(Color.White)) }
        poster.assert(SemanticsMatcher.expectValue(androidx.compose.ui.semantics.SemanticsProperties.StateDescription,
            compose.activity.getString(R.string.design_system_card_loaded)))
        assertEquals(initial, poster.getUnclippedBoundsInRoot())
        assertEquals(card, compose.onNodeWithTag("posterCard").getUnclippedBoundsInRoot())
        val action = compose.onNodeWithContentDescription("收藏测试影片")
        val hit = action.getUnclippedBoundsInRoot()
        assertTrue(hit.right - hit.left >= 48.dp && hit.bottom - hit.top >= 48.dp)
        assertTrue(hit.top >= initial.top && hit.right <= initial.right)
        action.performClick().assertIsOn()
        compose.runOnIdle { assertEquals(1, changed.get()); assertEquals(0, opened.get()) }
        compose.runOnIdle { available.value = false }
        action.assertIsNotEnabled()
        compose.onNodeWithTag("posterCard").performClick()
        compose.runOnIdle { assertEquals(1, opened.get()); assertEquals(1, changed.get()) }
    }

    @Test fun searchKeepsCallerPlaceholdersGroupedSelectionAndDisabledClearBehavior() {
        val value = mutableStateOf(""); val enabled = mutableStateOf(true)
        val chosen = mutableListOf<Pair<String, String>>()
        compose.setContent {
            LumenTheme(true) {
                AppSearchInput(value.value, { value.value = it }, label = "标签", placeholder = "搜索指定标签",
                    enabled = enabled.value,
                    suggestionGroups = if (value.value == "旅") listOf(AppSearchSuggestionGroup("tags", "标签建议",
                        listOf(AppSearchSuggestion("travel", "旅行")))) else emptyList(),
                    onSuggestionSelected = { group, item -> chosen += group to item.id; value.value = item.label })
            }
        }
        compose.onNode(hasSetTextAction()).performClick()
        compose.onNodeWithText("搜索指定标签").assertIsDisplayed()
        compose.onNode(hasSetTextAction()).performTextInput("旅")
        compose.onNodeWithText("标签建议").assertIsDisplayed()
        compose.onNodeWithText("旅行").performClick()
        compose.runOnIdle { assertEquals(listOf("tags" to "travel"), chosen); assertEquals("旅行", value.value) }
        val clear = compose.onNodeWithContentDescription(compose.activity.getString(R.string.design_system_input_clear))
        val bounds = clear.getUnclippedBoundsInRoot()
        assertTrue(bounds.right - bounds.left >= 48.dp && bounds.bottom - bounds.top >= 48.dp)
        clear.performClick()
        compose.runOnIdle { assertEquals("", value.value); value.value = "保留标签"; enabled.value = false }
        clear.assertIsNotEnabled().performTouchInput { click() }
        compose.runOnIdle { assertEquals("保留标签", value.value); assertEquals(1, chosen.size) }
    }

    @Test fun allSixteenIconsHaveDistinctGeometryAndNavigationEmitsOnlyTheChosenDestination() {
        var icons: List<ImageVector> = emptyList()
        val selected = mutableStateOf(AppDestination.Home); val emitted = mutableListOf<AppDestination>()
        compose.setContent {
            LumenTheme(false) {
                icons = listOf(AppIcons.Home, AppIcons.Library, AppIcons.Discover, AppIcons.Mine,
                    AppIcons.Favorite, AppIcons.Watchlist, AppIcons.SmartPlaylist, AppIcons.Statistics,
                    AppIcons.PhoneQueue, AppIcons.Remote, AppIcons.Tasks, AppIcons.Connections,
                    AppIcons.Sort, AppIcons.Filter, AppIcons.Search, AppIcons.More)
                AppBottomNavigation(selected.value, { selected.value = it; emitted += it })
            }
        }
        compose.runOnIdle {
            assertEquals(16, icons.size)
            assertEquals("Renaming a reused vector must not conceal duplicate icon geometry", 16, icons.map(::vectorPaths).toSet().size)
            assertTrue(icons.all { it.defaultWidth == 24.dp && it.defaultHeight == 24.dp })
            assertEquals(setOf("home", "library", "discover", "mine"), AppDestination.entries.map { it.id }.toSet())
        }
        for (destination in AppDestination.entries) {
            compose.onNodeWithText(compose.activity.getString(destination.labelRes)).performClick().assertIsSelected()
        }
        compose.runOnIdle { assertEquals(AppDestination.entries.toList(), emitted) }
    }

    @Test @Config(qualifiers = "w320dp-h640dp-mdpi")
    fun narrowLargeTextScaffoldConsumesMeasuredBarsOnceAndKeepsComponentActionsUsable() {
        val resources = compose.activity.resources
        resources.updateConfiguration(Configuration(resources.configuration).apply { fontScale = 1.5f },
            DisplayMetrics().apply { setTo(resources.displayMetrics); scaledDensity = density * 1.5f })
        compose.activity.enableLumenEdgeToEdge()
        val back = AtomicInteger(); val all = AtomicInteger(); val navigated = AtomicInteger()
        var actualScale = 0f
        compose.setContent {
            LumenTheme(true) {
                actualScale = LocalDensity.current.fontScale
                AppScreenScaffold(
                    topBar = { AppTopBar("统一页面标题", Modifier.testTag("topBar"), onBack = { back.incrementAndGet() }) },
                    bottomBar = { AppBottomNavigation(AppDestination.Home, { navigated.incrementAndGet() }, Modifier.testTag("bottomBar")) },
                    imePadding = true,
                ) {
                    Column(Modifier.fillMaxSize().testTag("viewport").padding(16.dp)) {
                        SectionHeader("分区标题和辅助操作", onViewAll = { all.incrementAndGet() }, viewAllLabel = "查看全部")
                        AppChip("已收藏", true, {}, leadingIcon = AppIcons.Favorite)
                        AppSearchInput("", {}, "年份", "起始年份")
                    }
                }
            }
        }
        dispatchIme(0)
        compose.waitForIdle()
        compose.runOnIdle { assertEquals(1.5f, actualScale, .01f) }
        val viewport = compose.onNodeWithTag("viewport").getUnclippedBoundsInRoot()
        val top = compose.onNodeWithTag("topBar").getUnclippedBoundsInRoot()
        val bottom = compose.onNodeWithTag("bottomBar").getUnclippedBoundsInRoot()
        assertEquals("Top inset must be consumed with the measured app bar", top.bottom.value, viewport.top.value, 1f)
        assertEquals("Bottom navigation padding must not be added twice", bottom.top.value, viewport.bottom.value, 1f)
        assertTrue(viewport.left >= 0.dp && viewport.right <= 320.dp)
        compose.onNodeWithContentDescription(compose.activity.getString(R.string.design_system_navigation_back)).performClick()
        compose.onNodeWithText("查看全部").performClick()
        compose.onNodeWithText(compose.activity.getString(AppDestination.Library.labelRes)).performClick()
        val section = compose.onNodeWithText("分区标题和辅助操作").getUnclippedBoundsInRoot()
        val viewAll = compose.onNodeWithText("查看全部").getUnclippedBoundsInRoot()
        assertTrue("Enlarged text must not overlap the section action", section.right <= viewAll.left)
        compose.runOnIdle { assertEquals(1, back.get()); assertEquals(1, all.get()); assertEquals(1, navigated.get()) }
        dispatchIme(300)
        compose.waitForIdle()
        val keyboardViewport = compose.onNodeWithTag("viewport").getUnclippedBoundsInRoot()
        assertTrue("The scaffold content must stay above the IME", keyboardViewport.bottom <= 340.dp)
    }

    private fun verifyTheme(dark: Boolean) {
        var colors: ColorScheme? = null
        var typography: Typography? = null
        var shapes: Shapes? = null
        var onPosterScrim = Color.Unspecified
        var spacing: List<Float> = emptyList()
        compose.setContent {
            LumenTheme(darkTheme = dark) {
                colors = MaterialTheme.colorScheme
                typography = MaterialTheme.typography
                shapes = MaterialTheme.shapes
                onPosterScrim = LocalAppPosterColors.current.onScrim
                val token = LocalAppSpacing.current
                spacing = listOf(token.xs, token.sm, token.md, token.lg, token.xl, token.page).map { it.value }
                Text("主题契约", style = MaterialTheme.typography.bodyLarge)
            }
        }
        compose.runOnIdle {
            val scheme = requireNotNull(colors)
            listOf(
                scheme.onSurface to scheme.surface,
                scheme.onSurface to scheme.surfaceContainer,
                scheme.onSurfaceVariant to scheme.surface,
                scheme.onSurfaceVariant to scheme.surfaceContainer,
                scheme.onPrimary to scheme.primary,
                scheme.onSecondaryContainer to scheme.secondaryContainer,
                scheme.onError to scheme.error,
            ).forEach { (foreground, background) ->
                assertTrue("Text role contrast must meet WCAG AA: $foreground on $background", contrast(foreground, background) >= 4.5f)
            }
            for (outline in listOf(scheme.outline, scheme.outlineVariant)) {
                val channels = listOf(outline.red, outline.green, outline.blue)
                assertTrue("Outlines must be neutral gray rather than an accent", channels.max() - channels.min() <= .005f)
            }
            for (photo in listOf(Color.Black, Color.White)) {
                val scrim = scheme.scrim.copy(alpha = AppDimensions.FavoriteScrimAlpha).compositeOver(photo)
                assertTrue("Favorite icon must contrast against extreme photo backgrounds", contrast(onPosterScrim, scrim) >= 3f)
            }
            val type = requireNotNull(typography)
            assertEquals(22.sp, type.titleLarge.fontSize)
            assertEquals(16.sp, type.titleMedium.fontSize)
            assertEquals(FontWeight.SemiBold, type.titleMedium.fontWeight)
            assertEquals(16.sp, type.bodyLarge.fontSize)
            assertEquals(14.sp, type.bodyMedium.fontSize)
            assertEquals(12.sp, type.labelMedium.fontSize)
            assertEquals(listOf(4f, 8f, 12f, 16f, 24f, 16f), spacing)
            val themedShapes = requireNotNull(shapes)
            listOf(themedShapes.small to 8f, themedShapes.medium to 12f, themedShapes.large to 16f).forEach { (shape, expected) ->
                val corner = (shape as CornerBasedShape).topStart.toPx(Size(100f, 100f), Density(1f))
                assertEquals(expected, corner, .01f)
            }
            assertEquals(48.dp, AppDimensions.TouchTarget)
            assertEquals(32.dp, AppDimensions.ChipHeight)
            assertEquals(48.dp, AppDimensions.ButtonHeight)
            assertEquals(24.dp, AppDimensions.Icon)
            assertEquals(2f / 3f, AppDimensions.PosterRatio, .0001f)
        }
    }

    private fun contrast(first: Color, second: Color): Float {
        val one = first.luminance(); val two = second.luminance()
        return (max(one, two) + .05f) / (min(one, two) + .05f)
    }

    private fun dispatchIme(bottom: Int) {
        compose.runOnIdle {
            val insets = AndroidWindowInsets.Builder()
                .setInsets(AndroidWindowInsets.Type.systemBars(), Insets.of(0, 24, 0, 24))
                .setInsets(AndroidWindowInsets.Type.ime(), Insets.of(0, 0, 0, bottom))
                .setVisible(AndroidWindowInsets.Type.ime(), bottom > 0)
                .build()
            val content = compose.activity.findViewById<ViewGroup>(android.R.id.content)
            content.getChildAt(0).dispatchApplyWindowInsets(insets)
            val modal = ShadowDialog.getLatestDialog()
            modal?.window?.decorView?.findViewById<ViewGroup>(android.R.id.content)?.getChildAt(0)?.dispatchApplyWindowInsets(insets)
        }
    }

    private fun vectorPaths(vector: ImageVector): String {
        fun paths(group: VectorGroup): String = group.joinToString("|") { node ->
            when (node) {
                is VectorGroup -> paths(node)
                is VectorPath -> node.pathData.toString()
                else -> error("Unexpected vector node")
            }
        }
        return paths(vector.root)
    }
}
