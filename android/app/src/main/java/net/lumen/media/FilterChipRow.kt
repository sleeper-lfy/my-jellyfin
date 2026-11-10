package net.lumen.media

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Icon
import androidx.compose.material3.InputChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.tooling.preview.Preview

/** One horizontal rail; many filters never take several rows away from the movies. */
@Composable
internal fun DiscoveryFilterChipRow(
    chips: List<DiscoveryUiState.Chip>,
    onRemove: (String, String) -> Unit,
    onClear: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (chips.isEmpty()) return
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        LazyRow(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(DiscoveryDimensions.Gap)) {
            items(chips, key = { "${it.id}:${it.value}" }) { chip ->
                InputChip(
                    selected = true,
                    modifier = Modifier.heightIn(min = DiscoveryDimensions.TouchTarget).testTag("discoveryChip:${chip.id}:${chip.value}"),
                    onClick = { onRemove(chip.id, chip.value) },
                    label = { Text(chip.label, style = MaterialTheme.typography.labelLarge, maxLines = 1) },
                    trailingIcon = { Icon(Icons.Default.Close, stringResource(R.string.discovery_remove_filter, chip.label)) },
                )
            }
        }
        TextButton(onClick = onClear) { Text(stringResource(R.string.discovery_clear_filters)) }
    }
}

@Preview(name = "Filter chips · Light", showBackground = true, widthDp = 393)
@Composable
private fun FilterChipsLightPreview() {
    DiscoveryTheme(false) { DiscoveryFilterChipRow(discoveryPreviewState().chips, { _, _ -> }, {}) }
}

@Preview(name = "Filter chips · Dark", showBackground = true, widthDp = 393)
@Composable
private fun FilterChipsDarkPreview() {
    DiscoveryTheme(true) { DiscoveryFilterChipRow(discoveryPreviewState().chips, { _, _ -> }, {}) }
}
