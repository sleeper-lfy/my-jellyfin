package net.lumen.media

import android.content.Context
import android.graphics.Bitmap
import android.graphics.drawable.BitmapDrawable
import android.widget.ImageView

/** Reuses the existing authenticated image queue and cache without rendering View cards. */
internal class DiscoveryImageLoader(
    private val context: Context,
    private val api: Api,
    private val requests: ImageRequests,
) {
    fun load(path: String, onState: (PosterLoadState) -> Unit): AutoCloseable {
        val target = object : ImageView(context), ImageRequests.TargetState {
            override fun onImageLoading() = onState(PosterLoadState.Loading)
            override fun onImageLoaded() {
                val bitmap = (drawable as? BitmapDrawable)?.bitmap
                onState(if (bitmap != null) PosterLoadState.Ready(bitmap) else PosterLoadState.Failed)
            }
            override fun onImageFailed() = onState(PosterLoadState.Failed)
        }
        requests.load(api, target, path)
        return AutoCloseable { requests.release(target) }
    }
}

internal sealed interface PosterLoadState {
    data object Loading : PosterLoadState
    data object Failed : PosterLoadState
    data class Ready(val bitmap: Bitmap) : PosterLoadState
}
