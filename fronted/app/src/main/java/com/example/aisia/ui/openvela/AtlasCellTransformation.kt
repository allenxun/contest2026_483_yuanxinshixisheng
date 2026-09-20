package com.example.aisia.ui.openvela

import android.graphics.Bitmap
import coil.size.Size
import coil.transform.Transformation

/** Applied by Coil's background image pipeline, after sampled decoding. */
class AtlasCellTransformation(private val columns: Int, private val rows: Int, private val index: Int) : Transformation {
    init { require(columns > 0 && rows > 0 && index in 0 until columns * rows) }
    override val cacheKey = "openvela-atlas-v1:$columns:$rows:$index"
    override suspend fun transform(input: Bitmap, size: Size): Bitmap {
        val width = input.width / columns
        val height = input.height / rows
        if (width < 1 || height < 1) return input
        return Bitmap.createBitmap(input, index % columns * width, index / columns * height, width, height)
    }
}
