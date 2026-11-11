package net.lumen.media

import android.content.Context
import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.os.Looper
import android.util.DisplayMetrics
import android.view.View
import android.view.ViewGroup
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performSemanticsAction
import androidx.core.view.WindowInsetsControllerCompat
import net.lumen.media.ui.theme.DarkColors
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.annotation.Implementation
import org.robolectric.annotation.Implements
import org.robolectric.shadows.ShadowDialog
import java.io.File
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.TimeUnit

/** Only credential persistence is substituted; every API, Activity, Host and theme is production code. */
@Implements(value = Connection::class, isInAndroidSdk = false)
internal class ThemeTestConnectionStore {
    companion object {
        @JvmField var saved: Connection? = null
        @JvmField val reads = AtomicInteger()
        @JvmStatic @Implementation fun load(context: Context): Connection? {
            reads.incrementAndGet()
            return saved
        }
    }
}

/** A light device must not override this dark application's production Compose entry point. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [33], qualifiers = "w393dp-h852dp-notnight-mdpi", shadows = [ThemeTestConnectionStore::class])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class DiscoveryAppThemeTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private val server = MockWebServer()

    @Before fun connectThroughTheNormalNavigationState() {
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val path = request.path.orEmpty()
                val body = when {
                    path.startsWith("/api/filters") -> """{"tags":["海岸","旅行"],"actors":[],"years":[2025]}"""
                    path.startsWith("/api/discovery/providers") -> """{"items":[]}"""
                    path.startsWith("/api/continue") -> """{"items":[]}"""
                    path == "/api/works/7" -> """{"id":7,"title":"海岸纪行","kind":"movie","year":2025,"file_count":1,"favorite":0,"files":[],"tags":[],"actors":[]}"""
                    else -> """{"items":[{"id":7,"title":"海岸纪行","kind":"movie","year":2025,"favorite":0},{"id":8,"title":"星夜环游","kind":"vr","year":2024,"favorite":1}],"total":2}"""
                }
                return MockResponse().setHeader("Content-Type", "application/json").setBody(body)
            }
        }
        server.start()
        val connection = Connection(server.url("/").toString(), "abcdefghijklmnopqrstuvwxyz123456")
        ThemeTestConnectionStore.saved = connection
        compose.runOnUiThread {
            // Equivalent to a successful connection; use actual navigation to leave its utility route.
            compose.activity.api = Api(connection)
            compose.activity.navigatePrimary("home")
        }
        assertNativeDark()
    }

    @After fun clearConnectionFixture() {
        ThemeTestConnectionStore.saved = null
        ThemeTestConnectionStore.reads.set(0)
        server.shutdown()
    }

    @Test fun realDayModeNavigationAndFilterDialogKeepTheAppDarkAcrossAllDestinations() {
        enterDiscovery()
        assertDiscoveryDark()
        snapshot("app-daymode-discovery-dark.png")
        compose.onNodeWithTag("discoveryFilter").performClick()
        compose.onNodeWithTag("filterForm").assertIsDisplayed()
        val form = compose.onNodeWithTag("filterForm").getUnclippedBoundsInRoot()
        compose.runOnIdle {
            val decor = requireNotNull(ShadowDialog.getLatestDialog()).window!!.decorView
            val bitmap = draw(decor)
            // The full-width sheet's left edge, midway through the form, avoids text and controls.
            val y = with(compose.density) { ((form.top + form.bottom) / 2).roundToPx() }
                .coerceIn(1, bitmap.height - 2)
            assertEquals("The real modal must inherit the application's dark container",
                DarkColors.surfaceContainer.toArgb(), bitmap.getPixel(1, y))
            bitmap.recycle()
            assertDeviceStillDay()
        }
        snapshot("app-daymode-discovery-sheet-dark.png", dialog = true)
        compose.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsActions.Dismiss)).onFirst()
            .performSemanticsAction(SemanticsActions.Dismiss) { dismiss -> dismiss() }
        compose.onNodeWithTag("filterForm").assertDoesNotExist()
        for (destination in listOf(R.string.design_system_nav_home, R.string.design_system_nav_library,
            R.string.design_system_nav_mine)) {
            compose.onNodeWithText(compose.activity.getString(destination)).performClick()
            assertNativeDark()
            enterDiscovery()
            assertDiscoveryDark()
        }
    }

    @Test fun cachedDetailReturnConfigurationAndActualActivityRecreationKeepTheAppDark() {
        enterDiscovery()
        val originalActivity = compose.activity
        val originalCoordinator = originalActivity.discoveryCoordinator
        compose.onNodeWithTag("discoveryMovie:7").performClick()
        compose.waitUntil(6000) { compose.activity.renderedDetailId == 7L }
        assertNativeDark()
        compose.runOnUiThread { compose.activity.onBackPressedDispatcher.onBackPressed() }
        compose.onNodeWithTag("discoveryGrid").assertIsDisplayed()
        compose.runOnIdle { assertSame("Back must reattach the cached discovery Host", originalCoordinator,
            compose.activity.discoveryCoordinator) }
        assertDiscoveryDark()
        compose.runOnUiThread {
            val resources = compose.activity.resources
            val changed = Configuration(resources.configuration).apply {
                fontScale = 1.2f
                uiMode = (uiMode and Configuration.UI_MODE_NIGHT_MASK.inv()) or Configuration.UI_MODE_NIGHT_NO
            }
            resources.updateConfiguration(changed, DisplayMetrics().apply {
                setTo(resources.displayMetrics); scaledDensity = density * changed.fontScale
            })
            compose.activity.onConfigurationChanged(changed)
            compose.activity.window.decorView.dispatchConfigurationChanged(changed)
        }
        compose.waitForIdle()
        assertDiscoveryDark()
        compose.runOnIdle { assertSame(originalCoordinator, compose.activity.discoveryCoordinator) }
        val reads = ThemeTestConnectionStore.reads.get()
        compose.activityRule.scenario.recreate()
        compose.onNodeWithTag("discoveryGrid").assertIsDisplayed()
        compose.waitUntil(6000) { compose.activity.discoveryCoordinator?.snapshot()?.items?.isNotEmpty() == true }
        compose.runOnIdle {
            assertNotSame(originalActivity, compose.activity)
            assertTrue("Recreation must run MainActivity's normal persisted-connection entry",
                ThemeTestConnectionStore.reads.get() > reads)
        }
        assertDiscoveryDark()
        snapshot("app-daymode-discovery-recreated-dark.png")
    }

    private fun enterDiscovery() {
        compose.runOnUiThread {
            val root = compose.activity.findViewById<ViewGroup>(android.R.id.content)
            requireNotNull(root.findViewWithTag<View>("nav:discover")).performClick()
        }
        compose.onNodeWithTag("discoverySearch").assertIsDisplayed()
        compose.waitUntil(6000) { compose.activity.discoveryCoordinator?.snapshot()?.items?.isNotEmpty() == true }
    }

    private fun assertDiscoveryDark() {
        compose.onNodeWithTag("discoveryGrid").assertIsDisplayed()
        compose.runOnIdle {
            assertDeviceStillDay()
            val bitmap = draw(contentRoot())
            // The grid's outer page gutter is painted by the actual Scaffold, clear of poster content.
            assertEquals("Production discovery must use DarkColors.surface even on a light device",
                DarkColors.surface.toArgb(), bitmap.getPixel(1, bitmap.height / 2))
            bitmap.recycle()
            assertLightSystemIcons()
            assertEquals(Color.TRANSPARENT, compose.activity.window.statusBarColor)
            assertEquals(Color.TRANSPARENT, compose.activity.window.navigationBarColor)
        }
    }

    private fun assertNativeDark() {
        idleNativeWindow()
        // Legacy destinations contain no Compose root; do not wait for a nonexistent composition here.
        compose.runOnUiThread {
            assertDeviceStillDay()
            val bitmap = draw(contentRoot())
            assertEquals(MediaStyle.BG, bitmap.getPixel(1, bitmap.height / 2))
            bitmap.recycle()
            assertLightSystemIcons()
            assertEquals(MediaStyle.BG, compose.activity.window.statusBarColor)
            assertEquals(MediaStyle.BG, compose.activity.window.navigationBarColor)
        }
    }

    private fun assertDeviceStillDay() {
        assertEquals("The app must not rewrite the device's uiMode to force its own palette",
            Configuration.UI_MODE_NIGHT_NO, compose.activity.resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK)
    }

    private fun assertLightSystemIcons() {
        val window = compose.activity.window
        val controller = WindowInsetsControllerCompat(window, window.decorView)
        assertFalse(controller.isAppearanceLightStatusBars)
        assertFalse(controller.isAppearanceLightNavigationBars)
    }

    private fun contentRoot(): View = compose.activity.findViewById<ViewGroup>(android.R.id.content).getChildAt(0)
    private fun idleNativeWindow() {
        repeat(100) {
            Shadows.shadowOf(Looper.getMainLooper()).idleFor(16, TimeUnit.MILLISECONDS)
            var measured = false
            compose.runOnUiThread { measured = contentRoot().width > 0 && contentRoot().height > 0 }
            if (measured) return
            Thread.sleep(10)
        }
        fail("The production native destination did not lay out")
    }
    private fun draw(view: View): Bitmap {
        assertTrue("A real native window must be laid out", view.width > 0 && view.height > 0)
        return Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888).also { view.draw(Canvas(it)) }
    }

    private fun snapshot(name: String, dialog: Boolean = false) {
        val directory = System.getenv("LUMEN_UI_SCREENSHOTS") ?: return
        compose.runOnIdle {
            val view = if (dialog) requireNotNull(ShadowDialog.getLatestDialog()).window!!.decorView
                else compose.activity.window.decorView
            val bitmap = draw(view)
            File(directory, name).apply { parentFile!!.mkdirs(); outputStream().use {
                bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
            } }
            bitmap.recycle()
        }
    }
}
