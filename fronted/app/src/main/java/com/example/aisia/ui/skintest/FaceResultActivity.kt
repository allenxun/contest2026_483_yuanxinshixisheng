package com.example.aisia.ui.skintest

import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.drawable.Drawable
import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import coil.load
import com.example.aisia.MainActivity
import com.example.aisia.R
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.facelandmarker.FaceLandmarker
import com.google.mediapipe.tasks.vision.facelandmarker.FaceLandmarkerResult
import kotlin.concurrent.thread

/**
 * 脸型检测结果页面
 * - 全屏展示人像
 * - 使用 MediaPipe Face Landmarker 检测 468 关键点
 * - 三庭五眼动画划线效果（中轴线、三庭线垂直、五眼线红色延长）
 * - 底部浮动返回按钮
 */
class FaceResultActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "FaceResultActivity"
        const val EXTRA_OSS_KEY = "oss_key"
        const val EXTRA_DEVICE_ID = "deviceId"
        const val EXTRA_IMAGE_PATH = "image_path"
        private const val MODEL_FILE = "face_landmarker.task"
    }

    private lateinit var ivHero: ImageView
    private lateinit var tvPlaceholder: TextView
    private lateinit var btnHome: TextView
    private lateinit var faceMeshOverlay: FaceMeshOverlayView

    private var ossKey: String = ""
    private var deviceId: String = ""

    // MediaPipe Face Landmarker
    private val faceWorker = java.util.concurrent.Executors.newSingleThreadExecutor()
    @Volatile private var closed = false
    private var faceLandmarker: FaceLandmarker? = null
    private var noFaceDialog: android.app.AlertDialog? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_face_result)

        initViews()
        setupListeners()
        faceWorker.execute { if (!closed) initFaceLandmarker() }

        ossKey = intent.getStringExtra(EXTRA_OSS_KEY) ?: ""
        deviceId = intent.getStringExtra(EXTRA_DEVICE_ID) ?: ""
        val imagePath = intent.getStringExtra(EXTRA_IMAGE_PATH) ?: ""

        // 加载本地图片
        if (imagePath.isNotEmpty()) {
            loadLocalImage(imagePath)
        }
    }

    private fun initViews() {
        ivHero = findViewById(R.id.ivHero)
        tvPlaceholder = findViewById(R.id.tvPlaceholder)
        btnHome = findViewById(R.id.btnHome)
        faceMeshOverlay = findViewById(R.id.faceMeshOverlay)
    }

    private fun setupListeners() {
        btnHome.setOnClickListener {
            goHome()
        }
    }

    /**
     * 初始化 MediaPipe Face Landmarker
     */
    private fun initFaceLandmarker() {
        try {
            val baseOptions = BaseOptions.builder()
                .setModelAssetPath(MODEL_FILE)
                .build()

            val options = FaceLandmarker.FaceLandmarkerOptions.builder()
                .setBaseOptions(baseOptions)
                .setRunningMode(RunningMode.IMAGE)
                .setNumFaces(1)
                .setMinFaceDetectionConfidence(0.5f)
                .setMinFacePresenceConfidence(0.5f)
                .setMinTrackingConfidence(0.5f)
                .setOutputFaceBlendshapes(false)
                .setOutputFacialTransformationMatrixes(false)
                .build()

            faceLandmarker = FaceLandmarker.createFromOptions(this, options)
            Log.i(TAG, "FaceLandmarker initialized successfully")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to initialize FaceLandmarker", e)
        }
    }

    /**
     * 加载本地图片
     */
    private fun loadLocalImage(path: String) {
        faceWorker.execute {
            try {
                val bitmap = SafeBitmaps.decodeFile(path)
                if (bitmap != null) {
                    runOnUiThread {
                        if (closed || isFinishing || isDestroyed) { bitmap.recycle(); return@runOnUiThread }
                        ivHero.setImageBitmap(bitmap)
                        tvPlaceholder.visibility = View.GONE
                        faceMeshOverlay.setImageInfo(bitmap.width, bitmap.height)
                        ivHero.post { detectFaceAndAnimate(bitmap) }
                    }
                } else {
                    runOnUiThread { loadFallbackImage(path) }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error loading local image", e)
                runOnUiThread { loadFallbackImage(path) }
            }
        }
    }

    private fun loadFallbackImage(path: String) {
        if (closed || isFinishing || isDestroyed) return
        ivHero.load(path) {
            size(1600)
            allowHardware(false)
            crossfade(true)
            placeholder(R.drawable.ic_default_avatar)
            error(R.drawable.ic_default_avatar)
            listener(
                onSuccess = { _, result ->
                    tvPlaceholder.visibility = View.GONE
                    val bitmap = drawableToBitmap(result.drawable)
                    if (bitmap != null) {
                        faceMeshOverlay.setImageInfo(bitmap.width, bitmap.height)
                        ivHero.post { detectFaceAndAnimate(bitmap) }
                    }
                }
            )
        }
    }

    /**
     * 使用 MediaPipe Face Landmarker 检测人脸关键点
     */
    private fun detectFaceAndAnimate(bitmap: Bitmap) {
        if (closed) return
        val landmarker = faceLandmarker
        if (landmarker == null) {
            Log.w(TAG, "FaceLandmarker not initialized")
            showNoFaceDialog("人脸检测组件初始化失败，请重新拍照后再试")
            return
        }

        faceWorker.execute {
            try {
                if (closed) return@execute
                val mpImage = BitmapImageBuilder(bitmap).build()
                val result: FaceLandmarkerResult = try { landmarker.detect(mpImage) } finally { mpImage.close() }

                if (result.faceLandmarks().isNotEmpty()) {
                    val landmarks = result.faceLandmarks()[0]
                    Log.i(TAG, "Detected ${landmarks.size} face landmarks")

                    runOnUiThread {
                        if (!closed && !isFinishing && !isDestroyed) faceMeshOverlay.setLandmarksAndAnimate(landmarks)
                    }
                } else {
                    Log.w(TAG, "No face detected in the image")
                    runOnUiThread { showNoFaceDialog() }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error detecting face landmarks", e)
                runOnUiThread {
                    showNoFaceDialog("人脸特征识别失败，请重新拍摄清晰、完整的正脸")
                }
            }
        }
    }

    private fun showNoFaceDialog(
        message: String = "照片中未检测到人脸，请重新拍摄清晰、完整的正脸"
    ) {
        if (isFinishing || isDestroyed || noFaceDialog?.isShowing == true) return
        noFaceDialog = android.app.AlertDialog.Builder(this)
            .setTitle("未检测到人脸")
            .setMessage(message)
            .setPositiveButton("重新拍照") { _, _ ->
                startActivity(
                    Intent(this, SmartSkinTestActivity::class.java)
                        .putExtra("type", "face")
                )
                finish()
            }
            .setNegativeButton("返回") { _, _ -> finish() }
            .setCancelable(false)
            .create()
            .also { dialog ->
                dialog.setOnDismissListener { noFaceDialog = null }
                dialog.show()
            }
    }

    private fun drawableToBitmap(drawable: Drawable): Bitmap? {
        return try {
            val bitmap = Bitmap.createBitmap(
                drawable.intrinsicWidth,
                drawable.intrinsicHeight,
                Bitmap.Config.ARGB_8888
            )
            val canvas = android.graphics.Canvas(bitmap)
            drawable.setBounds(0, 0, canvas.width, canvas.height)
            drawable.draw(canvas)
            bitmap
        } catch (e: Exception) {
            Log.e(TAG, "Error converting drawable to bitmap", e)
            null
        }
    }

    /**
     * 返回首页
     */
    private fun goHome() {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        startActivity(intent)
        finish()
    }

    override fun onDestroy() {
        noFaceDialog?.dismiss()
        noFaceDialog = null
        closed = true
        // Close on the same lane, after any active native detection has returned.
        faceWorker.execute { faceLandmarker?.close(); faceLandmarker = null }
        faceWorker.shutdown()
        super.onDestroy()
    }
}
