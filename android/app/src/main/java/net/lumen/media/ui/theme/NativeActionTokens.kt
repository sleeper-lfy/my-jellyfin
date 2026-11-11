package net.lumen.media.ui.theme

import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.unit.Density

/** Read-only Java bridge to the same roles and dimensions used by LumenTheme. */
object NativeActionTokens {
    private fun scheme(dark: Boolean) = if (dark) DarkColors else LightColors
    @JvmStatic fun touchDp() = AppDimensions.TouchTarget.value
    @JvmStatic fun visualDp() = AppDimensions.ButtonVisualHeight.value
    @JvmStatic fun iconDp() = AppDimensions.ButtonIcon.value
    @JvmStatic fun posterIconDp() = AppDimensions.SmallIcon.value
    @JvmStatic fun insetDp() = (touchDp() - visualDp()) / 2
    @JvmStatic fun horizontalPaddingDp() = AppSpacing().sm.value
    @JvmStatic fun verticalPaddingDp() = AppSpacing().xs.value
    @JvmStatic fun iconGapDp() = AppSpacing().xs.value
    @JvmStatic fun actionGapDp() = AppSpacing().md.value
    @JvmStatic fun cornerDp() = AppShapes.small.topStart.toPx(Size.Zero, Density(1f))
    @JvmStatic fun sheetCornerDp() = AppShapes.large.topStart.toPx(Size.Zero, Density(1f))
    @JvmStatic fun primary(dark: Boolean) = scheme(dark).primary.toArgb()
    @JvmStatic fun onSurfaceVariant(dark: Boolean) = scheme(dark).onSurfaceVariant.toArgb()
    @JvmStatic fun surfaceContainer(dark: Boolean) = scheme(dark).surfaceContainer.toArgb()
    @JvmStatic fun labelSp() = AppTypography.labelLarge.fontSize.value
    @JvmStatic fun background(dark: Boolean) = scheme(dark).background.toArgb()
    @JvmStatic fun surface(dark: Boolean) = scheme(dark).surface.toArgb()
    @JvmStatic fun onSurface(dark: Boolean) = scheme(dark).onSurface.toArgb()
    @JvmStatic fun outlineVariant(dark: Boolean) = scheme(dark).outlineVariant.toArgb()
    @JvmStatic fun error(dark: Boolean) = scheme(dark).error.toArgb()
    @JvmStatic fun onError(dark: Boolean) = scheme(dark).onError.toArgb()
    @JvmStatic fun primaryContainer(dark: Boolean) = scheme(dark).primaryContainer.toArgb()
    @JvmStatic fun onPrimaryContainer(dark: Boolean) = scheme(dark).onPrimaryContainer.toArgb()
    @JvmStatic fun surfaceContainerLow(dark: Boolean) = scheme(dark).surfaceContainerLow.toArgb()
    @JvmStatic fun surfaceContainerHigh(dark: Boolean) = scheme(dark).surfaceContainerHigh.toArgb()
    @JvmStatic fun surfaceContainerHighest(dark: Boolean) = scheme(dark).surfaceContainerHighest.toArgb()
    @JvmStatic fun scrim(dark: Boolean) = scheme(dark).scrim.toArgb()
    @JvmStatic fun onPhotoScrim(selected: Boolean) =
        (if (selected) DarkColors.primary else DarkColors.onSurface).toArgb()
    @JvmStatic fun cardCornerDp() = AppShapes.medium.topStart.toPx(Size.Zero, Density(1f))
    @JvmStatic fun buttonCornerDp() = cornerDp()
    @JvmStatic fun titleLargeSp() = AppTypography.titleLarge.fontSize.value
    @JvmStatic fun titleMediumSp() = AppTypography.titleMedium.fontSize.value
    @JvmStatic fun bodyLargeSp() = AppTypography.bodyLarge.fontSize.value
    @JvmStatic fun bodyMediumSp() = AppTypography.bodyMedium.fontSize.value
    @JvmStatic fun labelLargeSp() = AppTypography.labelLarge.fontSize.value
    @JvmStatic fun labelMediumSp() = AppTypography.labelMedium.fontSize.value
    @JvmStatic fun labelSmallSp() = AppTypography.labelSmall.fontSize.value
    @JvmStatic fun titleSp() = titleLargeSp()
    @JvmStatic fun bodySp() = bodyMediumSp()
    @JvmStatic fun supportingSp() = labelMediumSp()
    @JvmStatic fun spaceXsDp() = AppSpacing().xs.value
    @JvmStatic fun spaceSmDp() = AppSpacing().sm.value
    @JvmStatic fun spaceMdDp() = AppSpacing().md.value
    @JvmStatic fun spaceLgDp() = AppSpacing().lg.value
    @JvmStatic fun pageDp() = AppSpacing().page.value
    @JvmStatic fun sectionDp() = AppSpacing().xl.value

    // role: 0 tonal, 1 primary, 2 destructive, 3 text/icon-only.
    @JvmStatic fun container(dark: Boolean, role: Int, selected: Boolean): Int {
        val colors = scheme(dark)
        return when (role) {
            1 -> colors.primary
            2 -> colors.error
            3 -> Color.Transparent
            else -> if (selected) colors.primaryContainer else colors.secondaryContainer
        }.toArgb()
    }
    @JvmStatic fun content(dark: Boolean, role: Int, selected: Boolean): Int {
        val colors = scheme(dark)
        return when (role) {
            1 -> colors.onPrimary
            2 -> colors.onError
            3 -> if (selected) colors.primary else colors.onSurfaceVariant
            else -> if (selected) colors.onPrimaryContainer else colors.onSecondaryContainer
        }.toArgb()
    }
    @JvmStatic fun disabledContainer(dark: Boolean, role: Int) =
        (if (role == 3) Color.Transparent else scheme(dark).onSurface.copy(alpha = .12f)).toArgb()
    @JvmStatic fun disabledContent(dark: Boolean) = scheme(dark).onSurface.copy(alpha = .38f).toArgb()
}
