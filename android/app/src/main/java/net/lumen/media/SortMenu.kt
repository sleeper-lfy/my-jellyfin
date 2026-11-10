package net.lumen.media

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.AssistChip
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.tooling.preview.Preview

@Composable
internal fun DiscoverySortMenu(field: String, descending: Boolean, onSelect: (String) -> Unit, modifier: Modifier = Modifier) {
    var expanded by rememberSaveable { mutableStateOf(false) }
    val options = listOf("discovered", "site_added", "title", "year", "community_rating")
    val direction = stringResource(if (descending) R.string.discovery_sort_descending else R.string.discovery_sort_ascending)
    val arrow = stringResource(if (descending) R.string.discovery_sort_descending_arrow else R.string.discovery_sort_ascending_arrow)
    Box(modifier) {
        val label = stringResource(R.string.discovery_sort_label, discoverySortName(field), arrow)
        AssistChip(
            onClick = { expanded = true },
            modifier = Modifier.heightIn(min = DiscoveryDimensions.TouchTarget).testTag("discoverySort"),
            label = { Text(label, style = MaterialTheme.typography.labelLarge) },
        )
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { option ->
                val selected = option == field
                val name = discoverySortName(option)
                val description = if (selected) stringResource(R.string.discovery_sort_selected, name, direction) else name
                DropdownMenuItem(
                    text = { Text(if (selected) stringResource(R.string.discovery_sort_label, name, arrow) else name) },
                    onClick = { expanded = false; onSelect(option) },
                    leadingIcon = if (selected) ({ Icon(Icons.Default.Check, null) }) else null,
                    modifier = Modifier.semantics { contentDescription = description },
                )
            }
        }
    }
}

@Composable
internal fun discoverySortName(field: String): String = stringResource(when (field) {
    "site_added" -> R.string.discovery_sort_site_added
    "title" -> R.string.discovery_sort_title
    "year" -> R.string.discovery_sort_year
    "community_rating" -> R.string.discovery_sort_community_rating
    else -> R.string.discovery_sort_discovered
})

@Preview(name = "Sort menu · Light", showBackground = true)
@Composable
private fun SortLightPreview() { DiscoveryTheme(false) { DiscoverySortMenu("discovered", true, {}) } }

@Preview(name = "Sort menu · Dark", showBackground = true)
@Composable
private fun SortDarkPreview() { DiscoveryTheme(true) { DiscoverySortMenu("title", false, {}) } }
