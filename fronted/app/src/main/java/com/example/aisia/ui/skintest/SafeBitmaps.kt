package com.example.aisia.ui.skintest

import android.graphics.Bitmap
import android.graphics.BitmapFactory

/** Bounds-first decoding limits working image memory before allocating pixels. */
object SafeBitmaps {
    fun sampleSize(width: Int, height: Int, maxSide: Int = 2048): Int {
        require(maxSide > 0)
        var sample = 1
        while (width / sample > maxSide || height / sample > maxSide) sample *= 2
        return sample
    }
    fun decodeFile(path: String, maxSide: Int = 2048): Bitmap? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(path, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
        val options = BitmapFactory.Options().apply { inSampleSize = sampleSize(bounds.outWidth, bounds.outHeight, maxSide) }
        return try { BitmapFactory.decodeFile(path, options) } catch (_: OutOfMemoryError) { null }
    }
}
