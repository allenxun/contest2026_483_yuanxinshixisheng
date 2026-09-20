package com.example.aisia.ui.openvela

import android.content.Context
import android.view.Gravity
import android.widget.ImageView
import android.widget.LinearLayout
import coil.load
import com.example.aisia.R

/** Three independent slots: a missing/failed image never hides the other angles. */
internal object OpenVelaFacePhotos {
    fun create(context: Context, report: OpenVelaData.Report): LinearLayout {
        val titles = listOf("左侧脸", "正脸", "右侧脸")
        val urls = listOf(report.leftFaceImageUrl, report.frontFaceImageUrl, report.rightFaceImageUrl)
        return LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, OpenVelaBlue.dp(context, 10), 0, OpenVelaBlue.dp(context, 16))
            val photos = object : LinearLayout(context) {
                override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
                    val height = MeasureSpec.getSize(widthMeasureSpec) / 3
                    super.onMeasure(widthMeasureSpec, MeasureSpec.makeMeasureSpec(height, MeasureSpec.EXACTLY))
                }
            }.apply {
                orientation = LinearLayout.HORIZONTAL
                background = OpenVelaBlue.surface(context, radius = 12)
                clipToOutline = true
            }
            val captions = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL }
            addView(photos, LinearLayout.LayoutParams(-1, -2))
            addView(captions, LinearLayout.LayoutParams(-1, -2))
            titles.forEachIndexed { index, title ->
                val caption = OpenVelaBlue.text(context, "$title · 示例图", 12, color = OpenVelaBlue.muted).apply {
                    gravity = Gravity.CENTER
                    setPadding(0, OpenVelaBlue.dp(context, 8), 0, 0)
                }
                val photo = ImageView(context).apply {
                    scaleType = ImageView.ScaleType.CENTER_CROP
                    contentDescription = "$title，示例图"
                    fun loadDefault() {
                        load("file:///android_asset/openvela_face_angles.png") {
                            size(720, 240)
                            transformations(AtlasCellTransformation(3, 1, index))
                            placeholder(R.drawable.ic_default_avatar)
                            error(R.drawable.ic_default_avatar)
                        }
                        setOnClickListener {
                            com.example.aisia.ui.common.PhotoPreview.show(context, "file:///android_asset/openvela_face_angles.png", "$title · 示例图",
                                listOf(AtlasCellTransformation(3, 1, index)))
                        }
                        caption.text = "$title · 示例图"
                        contentDescription = "$title，示例图"
                    }
                    val url = OpenVelaApi.media(urls[index])
                    if (url == null) loadDefault()
                    else {
                        setOnClickListener { OpenVelaImages.preview(context, url, title) }
                        OpenVelaImages.bind(this, url,
                            success = { caption.text = title; contentDescription = title },
                            failure = {
                                caption.text = title + " · 加载失败，点击重试"
                                setOnClickListener { OpenVelaImages.preview(context, url, title) }
                            })
                    }
                }
                photos.addView(photo, LinearLayout.LayoutParams(0, -1, 1f))
                captions.addView(caption, LinearLayout.LayoutParams(0, -2, 1f))
            }
        }
    }
}
