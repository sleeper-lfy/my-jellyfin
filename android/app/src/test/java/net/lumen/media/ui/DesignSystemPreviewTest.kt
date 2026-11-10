package net.lumen.media.ui

import android.graphics.Bitmap
import android.graphics.Canvas
import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onLast
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import net.lumen.media.R
import net.lumen.media.ui.preview.DesignSystemPreview
import net.lumen.media.ui.theme.LumenTheme
import net.lumen.media.ui.theme.enableLumenEdgeToEdge
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.shadows.ShadowDialog
import java.io.File

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [33], qualifiers = "w1280dp-h1120dp-mdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class DesignSystemPreviewTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Test fun darkAtlasShowsEveryComponentInOneViewport() = atlas(true)
    @Test fun lightAtlasShowsEveryComponentInOneViewport() = atlas(false)

    private fun atlas(dark: Boolean) {
        compose.setContent { LumenTheme(dark) { DesignSystemPreview() } }
        listOf(R.string.design_system_theme_section, R.string.design_system_buttons_section,
            R.string.design_system_chips_section, R.string.design_system_input_section,
            R.string.design_system_settings_group, R.string.design_system_poster_section,
            R.string.design_system_empty_section, R.string.design_system_icons_section,
            R.string.design_system_sheet_open).forEach {
            compose.onNodeWithText(compose.activity.getString(it)).assertIsDisplayed()
        }
        screenshot("design-system-stage1-${if (dark) "dark" else "light"}.png")
    }

    @Test @Config(sdk = [33], qualifiers = "w393dp-h852dp-night-mdpi")
    fun phoneGalleryScrollsToAllControlsAndOpensTheRealDarkSheet() = phone(true)

    @Test @Config(sdk = [33], qualifiers = "w393dp-h852dp-notnight-mdpi")
    fun phoneGalleryScrollsToAllControlsAndOpensTheRealLightSheet() = phone(false)

    private fun phone(dark: Boolean) {
        compose.activity.enableLumenEdgeToEdge()
        compose.setContent { LumenTheme(dark) { DesignSystemPreview() } }
        val mode = if (dark) "dark" else "light"
        screenshot("design-system-phone-$mode.png")
        val open = compose.onNodeWithText(compose.activity.getString(R.string.design_system_sheet_open))
        open.performScrollTo().assertIsDisplayed()
        screenshot("design-system-phone-$mode-bottom.png")
        open.performClick()
        compose.onAllNodesWithText(compose.activity.getString(R.string.design_system_sheet_apply)).onLast().assertIsDisplayed()
        screenshot("design-system-sheet-$mode.png", dialog = true)
    }

    private fun screenshot(name: String, dialog: Boolean = false) {
        val directory = System.getenv("LUMEN_DESIGN_SYSTEM_SCREENSHOTS") ?: return
        compose.runOnIdle {
            val root = if (dialog) requireNotNull(ShadowDialog.getLatestDialog()).window!!.decorView
                else compose.activity.window.decorView
            assertTrue(root.width > 0 && root.height > 0)
            val bitmap = Bitmap.createBitmap(root.width, root.height, Bitmap.Config.ARGB_8888)
            root.draw(Canvas(bitmap))
            val colors = HashSet<Int>()
            for (y in 0 until bitmap.height step maxOf(1, bitmap.height / 60))
                for (x in 0 until bitmap.width step maxOf(1, bitmap.width / 60)) colors += bitmap.getPixel(x, y)
            assertTrue("Native preview must contain actual controls", colors.size > 8)
            File(directory, name).apply { parentFile?.mkdirs(); outputStream().use {
                bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
            } }
            bitmap.recycle()
        }
    }
}
