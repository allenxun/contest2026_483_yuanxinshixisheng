package com.example.aisia.ui.skintest

import android.content.Intent
import android.os.Bundle
import android.widget.ImageView
import androidx.appcompat.app.AppCompatActivity
import coil.load
import com.example.aisia.R

import com.google.android.material.card.MaterialCardView

/**
 * 肌肤智能检测列表页面 —— 展示三张功能卡片：肤质检测、3D人脸模型生成、人脸检测
 * 内容来自原 ScanFragment（activity_skin_analysis.xml）
 */
class SkinListActivity : AppCompatActivity() {

    // 卡片右侧图片（与小程序一致）
    private val skinDetectImgUrl = "https://eveaisia.com/face/img/a_face.png"
    private val faceModelImgUrl = "https://eveaisia.com/face/img/a_3d.png"
    private val beautyDetectImgUrl = "https://eveaisia.com/face/img/a_skin.png"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_skin_analysis)

        // 返回按钮
        findViewById<ImageView>(R.id.iv_back).setOnClickListener { finish() }

        // 加载卡片右侧图片
        findViewById<ImageView>(R.id.img_skin_detect).load(skinDetectImgUrl) { crossfade(true) }
        findViewById<ImageView>(R.id.img_face_model).load(faceModelImgUrl) { crossfade(true) }
        findViewById<ImageView>(R.id.img_beauty_detect).load(beautyDetectImgUrl) { crossfade(true) }

        // 卡片点击事件
        findViewById<MaterialCardView>(R.id.card_skin_detect).setOnClickListener {
            // 肤质检测 → type=skin
            goToSmartSkinTest("skin")
        }

        findViewById<MaterialCardView>(R.id.card_face_model).setOnClickListener {
            // 3D人脸模型生成 → type=3d
            goToSmartSkinTest("3d")
        }

        findViewById<MaterialCardView>(R.id.card_beauty_detect).setOnClickListener {
            // 人脸检测 → type=face
            goToSmartSkinTest("face")
        }
    }

    private fun goToSmartSkinTest(type: String) {
        val intent = Intent(this, SmartSkinTestActivity::class.java).apply {
            putExtra("type", type)
        }
        startActivity(intent)
    }
}