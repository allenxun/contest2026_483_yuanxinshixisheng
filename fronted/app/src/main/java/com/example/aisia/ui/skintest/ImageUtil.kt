package com.example.aisia.ui.skintest

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.graphics.Rect
import android.graphics.YuvImage
import androidx.camera.core.ImageProxy
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer

/**
 * 把 CameraX 的 ImageProxy（YUV_420_888）转 Bitmap，并做旋转修正。
 * 正确处理 pixelStride/rowStride，兼容各种设备（包括平板）。
 */
object ImageUtil {

    fun toBitmap(imageProxy: ImageProxy, mirrorH: Boolean = false): Bitmap? {
        return try {
            val nv21 = yuv420ToNv21(imageProxy)

            val yuvImage = YuvImage(
                nv21,
                android.graphics.ImageFormat.NV21,
                imageProxy.width,
                imageProxy.height,
                null
            )
            val out = ByteArrayOutputStream()
            yuvImage.compressToJpeg(Rect(0, 0, imageProxy.width, imageProxy.height), 90, out)
            val jpeg = out.toByteArray()
            var bitmap = BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size) ?: return null

            // 根据 rotation 旋转（前置摄像头典型 270°）
            val rotation = imageProxy.imageInfo.rotationDegrees
            if (rotation != 0 || mirrorH) {
                val matrix = Matrix().apply {
                    if (rotation != 0) postRotate(rotation.toFloat())
                    if (mirrorH) postScale(-1f, 1f)
                }
                bitmap = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
            }

            bitmap
        } catch (e: Exception) {
            null
        }
    }

    /**
     * 将 YUV_420_888 转为 NV21 字节数组，正确处理 pixelStride 和 rowStride。
     * 某些设备（如平板）U/V 平面的 pixelStride=2，直接 .remaining() 读取会包含无效数据导致花屏。
     */
    private fun yuv420ToNv21(image: ImageProxy): ByteArray {
        val width = image.width
        val height = image.height
        val ySize = width * height
        val uvSize = width * height / 4
        val nv21 = ByteArray(ySize + uvSize * 2)

        val yPlane = image.planes[0]
        val uPlane = image.planes[1]
        val vPlane = image.planes[2]

        // Y 平面：pixelStride 一定为 1
        val yBuffer = yPlane.buffer
        val yRowStride = yPlane.rowStride
        var position = 0
        for (row in 0 until height) {
            yBuffer.position(row * yRowStride)
            yBuffer.get(nv21, position, width)
            position += width
        }

        // U/V 平面：处理 pixelStride（可能为 1 或 2）
        val uBuffer = uPlane.buffer
        val vBuffer = vPlane.buffer
        val uRowStride = uPlane.rowStride
        val vRowStride = vPlane.rowStride
        val uPixelStride = uPlane.pixelStride
        val vPixelStride = vPlane.pixelStride

        val uvHeight = height / 2
        val uvWidth = width / 2

        for (row in 0 until uvHeight) {
            for (col in 0 until uvWidth) {
                // NV21 = Y + VU 交错
                nv21[position++] = vBuffer.get(row * vRowStride + col * vPixelStride)
                nv21[position++] = uBuffer.get(row * uRowStride + col * uPixelStride)
            }
        }

        return nv21
    }
}