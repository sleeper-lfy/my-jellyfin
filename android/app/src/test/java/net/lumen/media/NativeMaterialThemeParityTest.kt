package net.lumen.media

import android.content.Context
import android.view.ContextThemeWrapper
import androidx.compose.ui.graphics.toArgb
import com.google.android.material.color.MaterialColors
import com.google.android.material.textfield.MaterialAutoCompleteTextView
import com.google.android.material.textfield.TextInputLayout
import com.google.android.material.chip.Chip
import net.lumen.media.ui.theme.DarkColors
import net.lumen.media.ui.theme.LightColors
import net.lumen.media.ui.theme.NativeActionTokens
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import com.google.android.material.R as MaterialR

/** Official View components and Compose must resolve the same semantic palette. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [33])
class NativeMaterialThemeParityTest {
    private fun themed(dark: Boolean): Context = ContextThemeWrapper(
        RuntimeEnvironment.getApplication(),
        if (dark) R.style.LumenNativeActionsDark else R.style.LumenNativeActionsLight,
    )

    private fun assertRoles(dark: Boolean, context: Context = themed(dark)) {
        val scheme = if (dark) DarkColors else LightColors
        val expected = mapOf(
            MaterialR.attr.colorPrimary to NativeActionTokens.primary(dark),
            MaterialR.attr.colorOnPrimary to NativeActionTokens.content(dark, 1, false),
            MaterialR.attr.colorPrimaryContainer to NativeActionTokens.primaryContainer(dark),
            MaterialR.attr.colorOnPrimaryContainer to NativeActionTokens.onPrimaryContainer(dark),
            MaterialR.attr.colorPrimaryInverse to scheme.inversePrimary.toArgb(),
            MaterialR.attr.colorSecondary to scheme.secondary.toArgb(),
            MaterialR.attr.colorOnSecondary to scheme.onSecondary.toArgb(),
            MaterialR.attr.colorSecondaryContainer to NativeActionTokens.container(dark, 0, false),
            MaterialR.attr.colorOnSecondaryContainer to NativeActionTokens.content(dark, 0, false),
            MaterialR.attr.colorTertiary to scheme.tertiary.toArgb(),
            MaterialR.attr.colorOnTertiary to scheme.onTertiary.toArgb(),
            MaterialR.attr.colorTertiaryContainer to scheme.tertiaryContainer.toArgb(),
            MaterialR.attr.colorOnTertiaryContainer to scheme.onTertiaryContainer.toArgb(),
            android.R.attr.colorBackground to NativeActionTokens.background(dark),
            MaterialR.attr.colorOnBackground to scheme.onBackground.toArgb(),
            MaterialR.attr.colorSurface to NativeActionTokens.surface(dark),
            MaterialR.attr.colorOnSurface to NativeActionTokens.onSurface(dark),
            MaterialR.attr.colorSurfaceVariant to scheme.surfaceVariant.toArgb(),
            MaterialR.attr.colorOnSurfaceVariant to NativeActionTokens.onSurfaceVariant(dark),
            MaterialR.attr.colorOutline to scheme.outline.toArgb(),
            MaterialR.attr.colorOutlineVariant to NativeActionTokens.outlineVariant(dark),
            MaterialR.attr.colorSurfaceDim to scheme.surfaceDim.toArgb(),
            MaterialR.attr.colorSurfaceBright to scheme.surfaceBright.toArgb(),
            MaterialR.attr.colorSurfaceContainerLowest to scheme.surfaceContainerLowest.toArgb(),
            MaterialR.attr.colorSurfaceContainerLow to NativeActionTokens.surfaceContainerLow(dark),
            MaterialR.attr.colorSurfaceContainer to NativeActionTokens.surfaceContainer(dark),
            MaterialR.attr.colorSurfaceContainerHigh to NativeActionTokens.surfaceContainerHigh(dark),
            MaterialR.attr.colorSurfaceContainerHighest to NativeActionTokens.surfaceContainerHighest(dark),
            MaterialR.attr.colorError to NativeActionTokens.error(dark),
            MaterialR.attr.colorOnError to NativeActionTokens.onError(dark),
            MaterialR.attr.colorErrorContainer to scheme.errorContainer.toArgb(),
            MaterialR.attr.colorOnErrorContainer to scheme.onErrorContainer.toArgb(),
        )
        expected.forEach { (attribute, color) ->
            assertEquals(context.resources.getResourceEntryName(attribute), color,
                MaterialColors.getColor(context, attribute, "Lumen native theme"))
        }
    }

    @Test fun darkNativeThemeMatchesComposeRoles() = assertRoles(true)
    @Test fun lightNativeThemeMatchesComposeRoles() = assertRoles(false)
    @Test fun productionThemeUsesTheSameDarkSemanticPalette() = assertRoles(true,
        ContextThemeWrapper(RuntimeEnvironment.getApplication(), R.style.AppTheme))

    @Test fun officialInputsAndChipsKeepTheLumenPaletteInBothThemes() {
        listOf(true, false).forEach { dark ->
            val context = themed(dark)
            val field = TextInputLayout(context)
            val input = MaterialAutoCompleteTextView(context)
            field.addView(input)
            val chip = Chip(context)
            listOf(field.context, input.context, chip.context).forEach { componentContext ->
                assertEquals(NativeActionTokens.primary(dark), MaterialColors.getColor(
                    componentContext, MaterialR.attr.colorPrimary, "Lumen official component"))
                assertEquals(NativeActionTokens.surfaceContainer(dark), MaterialColors.getColor(
                    componentContext, MaterialR.attr.colorSurfaceContainer, "Lumen official component"))
                assertEquals(NativeActionTokens.error(dark), MaterialColors.getColor(
                    componentContext, MaterialR.attr.colorError, "Lumen official component"))
            }
        }
    }
}
