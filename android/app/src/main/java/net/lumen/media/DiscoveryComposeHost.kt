package net.lumen.media

import android.content.Context
import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.platform.ViewCompositionStrategy
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.receiveAsFlow

/** Thin Java-to-Compose boundary; ImageRequests remains shared with the other Android pages. */
internal class DiscoveryComposeHost(context: Context, api: Api, imageRequests: ImageRequests, callbacks: DiscoveryCallbacks) {
    val view = ComposeView(context)
    private var snapshot by mutableStateOf(DiscoveryUiState.empty())
    private var activeState by mutableStateOf(true)
    private var imageEpoch by mutableIntStateOf(0)
    private val messages = Channel<String>(capacity = 8, onBufferOverflow = BufferOverflow.DROP_OLDEST)
    private val snackbar = SnackbarHostState()
    private val loader = DiscoveryImageLoader(context, api, imageRequests)

    init {
        view.id = R.id.discovery_compose_host
        view.setViewCompositionStrategy(ViewCompositionStrategy.DisposeOnViewTreeLifecycleDestroyed)
        view.setContent {
            DiscoveryTheme {
                LaunchedEffect(activeState) { if (activeState) messages.receiveAsFlow().collect { snackbar.showSnackbar(it) } }
                DiscoveryScreen(snapshot, callbacks, loader, activeState, imageEpoch, snackbar)
            }
        }
    }
    fun update(state: DiscoveryUiState) { snapshot = state }
    fun setActive(value: Boolean) {
        if (value && !activeState) imageEpoch++
        activeState = value
        if (!value) snackbar.currentSnackbarData?.dismiss()
    }
    fun showSnackbar(message: String) { messages.trySend(message) }
    fun dispose() { activeState = false; messages.close(); view.disposeComposition() }
}
