package com.example.aisia.ui.common

import android.app.Dialog
import android.content.Context
import android.graphics.Color
import android.view.Gravity
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.TextView
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import coil.load
import coil.imageLoader
import coil.transform.Transformation
import com.example.aisia.R

object PhotoPreview {
    fun show(context: Context, source: Any, title: String = "图片预览", transformations: List<Transformation> = emptyList(), imageLoader: coil.ImageLoader? = null) {
        val activity = context as? FragmentActivity ?: return
        if (activity.isFinishing || activity.isDestroyed) return
        val dialog = Dialog(activity, android.R.style.Theme_Black_NoTitleBar_Fullscreen)
        val root = FrameLayout(activity).apply { setBackgroundColor(Color.BLACK); clipChildren = true }
        val hint = TextView(activity).apply {
            text = "图片加载中…"; textSize = 14f
            setTextColor(Color.WHITE); gravity = Gravity.CENTER; setPadding(16, 16, 16, 32)
        }
        var failed = false
        val photo = ZoomPhoto(activity).apply {
            scaleType = ImageView.ScaleType.FIT_CENTER
            contentDescription = title
        }
        fun loadPhoto() {
            failed = false
            hint.text = "图片加载中…"
            photo.load(source, imageLoader ?: context.imageLoader) {
                size(2048)
                if (transformations.isNotEmpty()) transformations(transformations)
                error(R.drawable.ic_default_avatar)
                listener(
                    onSuccess = { _, _ -> hint.text = "$title · 双指缩放，双击还原" },
                    onError = { _, _ -> failed = true; hint.text = "图片加载失败，点击图片重试" }
                )
            }
        }
        photo.setOnClickListener { if (failed) loadPhoto() }
        loadPhoto()
        root.addView(photo, FrameLayout.LayoutParams(-1, -1))
        root.addView(TextView(activity).apply {
            text = "关闭"; textSize = 16f; setTextColor(Color.WHITE); gravity = Gravity.CENTER
            setOnClickListener { dialog.dismiss() }
        }, FrameLayout.LayoutParams((72 * activity.resources.displayMetrics.density).toInt(), (56 * activity.resources.displayMetrics.density).toInt(), Gravity.TOP or Gravity.END))
        root.addView(hint, FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM))
        val observer = object : DefaultLifecycleObserver {
            override fun onDestroy(owner: LifecycleOwner) { dialog.dismiss() }
        }
        activity.lifecycle.addObserver(observer)
        dialog.setOnDismissListener { activity.lifecycle.removeObserver(observer) }
        dialog.setContentView(root)
        dialog.show()
    }

    private class ZoomPhoto(context: Context) : androidx.appcompat.widget.AppCompatImageView(context) {
        private val scaleDetector = ScaleGestureDetector(context, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
            override fun onScale(detector: ScaleGestureDetector): Boolean {
                val zoom = (scaleX * detector.scaleFactor).coerceIn(1f, 5f)
                scaleX = zoom; scaleY = zoom; clampPan(); return true
            }
        })
        private val gestures = GestureDetector(context, object : GestureDetector.SimpleOnGestureListener() {
            override fun onDown(e: MotionEvent) = true
            override fun onDoubleTap(e: MotionEvent): Boolean {
                scaleX = 1f; scaleY = 1f; translationX = 0f; translationY = 0f; return true
            }
            override fun onScroll(e1: MotionEvent?, e2: MotionEvent, distanceX: Float, distanceY: Float): Boolean {
                if (!scaleDetector.isInProgress && scaleX > 1f) {
                    translationX -= distanceX; translationY -= distanceY; clampPan()
                }
                return true
            }
        })
        private fun clampPan() {
            val x = width * (scaleX - 1) / 2
            val y = height * (scaleY - 1) / 2
            translationX = translationX.coerceIn(-x, x); translationY = translationY.coerceIn(-y, y)
        }
        override fun onTouchEvent(event: MotionEvent): Boolean {
            scaleDetector.onTouchEvent(event); gestures.onTouchEvent(event)
            if (event.actionMasked == MotionEvent.ACTION_UP) performClick()
            return true
        }
        override fun performClick(): Boolean { super.performClick(); return true }
    }
}
