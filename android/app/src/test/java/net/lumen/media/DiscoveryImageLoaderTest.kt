package net.lumen.media

import android.app.Activity
import android.graphics.Bitmap
import android.os.Looper
import android.util.LruCache
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import okio.Buffer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [33])
class DiscoveryImageLoaderTest {
    private fun waitFor(ready: () -> Boolean) {
        val until = System.currentTimeMillis() + 6000
        while (!ready() && System.currentTimeMillis() < until) {
            Thread.sleep(10); Shadows.shadowOf(Looper.getMainLooper()).idle()
        }
        assertTrue(ready())
    }
    private fun image(): Buffer = Buffer().also { output ->
        Bitmap.createBitmap(24, 36, Bitmap.Config.ARGB_8888).apply { eraseColor(android.graphics.Color.BLUE) }
            .compress(Bitmap.CompressFormat.PNG, 100, output.outputStream())
    }

    @Test fun sharedAuthenticatedLoadSurvivesOneConsumerLeavingAndThenUsesTheCache() {
        val started = CountDownLatch(1); val release = CountDownLatch(1); val count = AtomicInteger()
        MockWebServer().use { server ->
            server.dispatcher = object : Dispatcher() {
                override fun dispatch(request: RecordedRequest): MockResponse {
                    assertEquals("Bearer abcdefghijklmnopqrstuvwxyz123456", request.getHeader("Authorization"))
                    count.incrementAndGet(); started.countDown(); release.await(10, TimeUnit.SECONDS)
                    return if (request.path == "/api/works/1/cover") MockResponse().setBody(image()) else MockResponse().setResponseCode(404)
                }
            }
            server.start()
            Robolectric.buildActivity(Activity::class.java).create().use { lifecycle ->
                val images = ImageRequests(LruCache<String, Bitmap>(8))
                val loader = DiscoveryImageLoader(lifecycle.get(), Api(Connection(server.url("/").toString(), "abcdefghijklmnopqrstuvwxyz123456")), images)
                try {
                    val first = mutableListOf<PosterLoadState>(); val second = mutableListOf<PosterLoadState>()
                    val one = loader.load("/api/works/1/cover") { first += it }
                    val two = loader.load("/api/works/1/cover") { second += it }
                    assertTrue(started.await(3, TimeUnit.SECONDS)); assertEquals(1, count.get())
                    assertEquals(PosterLoadState.Loading, first.last()); one.close(); release.countDown()
                    waitFor { second.lastOrNull() is PosterLoadState.Ready }
                    assertTrue(first.none { it is PosterLoadState.Ready }); assertEquals(1, count.get())
                    val cached = mutableListOf<PosterLoadState>()
                    val three = loader.load("/api/works/1/cover") { cached += it }
                    assertTrue(cached.last() is PosterLoadState.Ready); assertEquals(1, count.get())
                    three.close(); two.close()
                    val missing = mutableListOf<PosterLoadState>()
                    val failed = loader.load("/api/works/2/cover") { missing += it }
                    waitFor { missing.lastOrNull() == PosterLoadState.Failed }; failed.close()
                    waitFor { images.idle() }
                } finally { release.countDown(); images.close() }
            }
        }
    }

    @Test fun leavingTheLastQueuedConsumerNeverStartsItsNetworkRequest() {
        val started = CountDownLatch(2); val release = CountDownLatch(1); val count = AtomicInteger()
        MockWebServer().use { server ->
            server.dispatcher = object : Dispatcher() {
                override fun dispatch(request: RecordedRequest): MockResponse {
                    count.incrementAndGet(); started.countDown(); release.await(10, TimeUnit.SECONDS)
                    return MockResponse().setResponseCode(404)
                }
            }
            server.start()
            Robolectric.buildActivity(Activity::class.java).create().use { lifecycle ->
                val images = ImageRequests(LruCache<String, Bitmap>(8))
                val loader = DiscoveryImageLoader(lifecycle.get(), Api(Connection(server.url("/").toString(), "abcdefghijklmnopqrstuvwxyz123456")), images)
                try {
                    val one = loader.load("/api/works/1/cover") {}
                    val two = loader.load("/api/works/2/cover") {}
                    assertTrue(started.await(3, TimeUnit.SECONDS))
                    val queued = loader.load("/api/works/3/cover") {}; queued.close()
                    one.close(); two.close(); release.countDown(); waitFor { images.idle() }
                    assertEquals(2, count.get())
                } finally { release.countDown(); images.close() }
            }
        }
    }
}
