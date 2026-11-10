package net.lumen.media.ui.theme

import androidx.activity.ComponentActivity
import androidx.activity.enableEdgeToEdge

/** Opt-in window setup for each approved page host; never mutates a window from composition. */
fun ComponentActivity.enableLumenEdgeToEdge() = enableEdgeToEdge()
