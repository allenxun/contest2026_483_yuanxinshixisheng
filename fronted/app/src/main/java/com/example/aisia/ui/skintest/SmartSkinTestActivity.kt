package com.example.aisia.ui.skintest

import android.Manifest
import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.animation.AnimatorSet
import android.animation.ObjectAnimator
import android.animation.ValueAnimator
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ImageFormat
import android.graphics.Rect
import android.graphics.YuvImage
import android.net.Uri
import android.os.Bundle
import android.os.CountDownTimer
import android.os.Environment
import android.provider.MediaStore
import android.speech.tts.TextToSpeech
import android.util.Log
import android.view.View
import android.view.animation.AccelerateDecelerateInterpolator
import android.view.animation.LinearInterpolator
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.core.UseCase
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.example.aisia.BuildConfig
import com.example.aisia.R
import com.example.aisia.privacy.PrivacyManager
import com.example.aisia.network.HttpHelper
import com.example.aisia.network.TokenManager
import com.example.aisia.ui.report.SkinReportActivity
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.face.FaceDetection
import com.google.mlkit.vision.face.FaceDetectorOptions
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.Response
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * 智能测肤页面
 * 参考小程序 skin.wxml/skin.wxss/skin.js 实现
 * 流程：拍照预览 -> 确认拍照 -> 上传分析 -> 结果页
 *
 * 新增功能：
 *  - MediaPipe FaceLandmarker 实时人脸检测
 *  - 高精度判断五官关键点是否落在 FaceGuideView 椭圆引导框内
 *  - TTS 语音引导：提示用户调整人脸位置
 */
class SmartSkinTestActivity : AppCompatActivity(), TextToSpeech.OnInitListener {

    companion object {
        private const val TAG = "SmartSkinTest"
        const val STATE_PREVIEW = 0      // 预览阶段
        const val STATE_CAPTURED = 1     // 已拍照
        const val STATE_ANALYZING = 2    // 分析中
        const val STATE_COMPLETE = 3     // 完成

        private const val CAMERA_PERMISSION_CODE = 100
    }

    private var currentState = STATE_PREVIEW
    private var testType: String = "skin" // 测试类型：skin、3d、face
    private var uploadedOssKey: String = "" // 上传图片后服务端返回的 oss_key

    // CameraX
    private lateinit var previewView: PreviewView
    private var imageCapture: ImageCapture? = null
    private var imageAnalysis: ImageAnalysis? = null
    private val photoWorker = Executors.newSingleThreadExecutor()
    private var previewGeneration = 0
    private lateinit var cameraExecutor: ExecutorService
    private var capturedImageFile: File? = null
    private var capturedFromFrontCamera = false
    private var capturedImageNormalized = false

    // Views - 预览层
    private lateinit var ivBack: ImageView
    private lateinit var btnCapture: FrameLayout
    private lateinit var btnGallery: FrameLayout
    private lateinit var btnSettings: FrameLayout
    private lateinit var tvCaptureText: TextView

    // Views - 人脸引导
    private lateinit var faceGuideView: FaceGuideView
    private lateinit var tvFaceAlignHint: TextView

    // Views - 图片预览层
    private lateinit var layoutPreview: FrameLayout
    private lateinit var ivPreview: ImageView
    private lateinit var btnRetake: TextView
    private lateinit var btnConfirm: TextView

    // Views - 分析蒙层
    private lateinit var layoutAnalyzing: FrameLayout
    private lateinit var ivCloseAnalyzing: ImageView
    private lateinit var tvAnalyzingTitle: TextView
    private lateinit var tvAnalyzingSubtitle: TextView
    private lateinit var tvUploadProgress: TextView
    private lateinit var viewProgressFill: View
    private lateinit var viewProgressGlow: View
    private lateinit var layoutScanAnimation: FrameLayout
    private lateinit var viewRing1: View
    private lateinit var viewRing2: View
    private lateinit var viewRing3: View
    private lateinit var viewAnalyzingScanLine: View
    private lateinit var viewGlow1: View
    private lateinit var viewGlow2: View

    // 分析项
    private lateinit var analysisItems: List<LinearLayout>
    private lateinit var itemIcons: List<View>
    private lateinit var itemTexts: List<TextView>
    private lateinit var itemStatuses: List<TextView>

    // 完成动画
    private lateinit var layoutComplete: FrameLayout
    private lateinit var viewCompleteCircle: View
    private lateinit var ivCompleteCheck: ImageView
    private lateinit var tvCompleteText: TextView

    // 粒子
    private lateinit var particles: List<View>

    // 动画
    private var ring1Animator: ObjectAnimator? = null
    private var ring2Animator: ObjectAnimator? = null
    private var ring3Animator: ObjectAnimator? = null
    private var scanLineAnimator: ObjectAnimator? = null
    private var glow1Animator: ObjectAnimator? = null
    private var glow2Animator: ObjectAnimator? = null
    private var particleAnimators: List<ObjectAnimator> = emptyList()

    // 分析项数据
    private val analysisItemNames = listOf(
        "面部图像清晰度校准",
        "面部区域分割",
        "肌肤水分含量检测",
        "皮肤油脂分泌分析",
        "干纹、静态皱纹识别",
        "毛孔粗大程度测算",
        "黑色素、色斑检测",
        "泛红敏感区域识别"
    )

    // ────── 人脸对齐检测 ──────
    private var faceAlignAnalyzer: FaceAlignmentAnalyzer? = null
    private var lastAlignState: FaceAlignState = FaceAlignState.NO_FACE
    private var faceValidationInProgress = false
    private var noFaceDialog: android.app.AlertDialog? = null

    // 稳定对齐计时（连续 2 秒 ALIGNED 才算完成）
    private var alignedStartTimeMs: Long = 0L
    private var hasAnnouncedAligned: Boolean = false

    private var hasAutoCaptured: Boolean = false  // 对齐完成后是否已自动拍照

    // TTS 语音引导
    private var tts: TextToSpeech? = null
    private var ttsReady: Boolean = false
    private var lastTtsState: FaceAlignState? = null
    private var lastTtsTimeMs: Long = 0L
    private val TTS_COOLDOWN_MS = 3000L  // 同一条语音至少间隔 3 秒

    // 相册选择
    private val galleryLauncher = registerForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        uri?.let {
            // 复制图片到临时文件
            val inputStream = contentResolver.openInputStream(it)
            val tempFile = createImageFile()
            inputStream?.use { input ->
                FileOutputStream(tempFile).use { output ->
                    input.copyTo(output)
                }
            }
            capturedFromFrontCamera = false
            capturedImageNormalized = false
            capturedImageFile = tempFile
            showPreview()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_smart_skin_test)

        // 获取测试类型参数（skin、3d、face）
        testType = intent.getStringExtra("type") ?: "skin"

        initViews()
        setupListeners()
        initTts()

        // 合规要求：用户同意隐私政策后才能申请相机权限
        PrivacyManager.ensureAgreed(this) {
            if (checkCameraPermission()) {
                startCamera()
            }
        }

        cameraExecutor = Executors.newSingleThreadExecutor()
    }

    private fun initViews() {
        // 相机预览
        previewView = findViewById(R.id.preview_view)

        // 预览层控件
        ivBack = findViewById(R.id.iv_back)
        btnCapture = findViewById(R.id.btn_capture)
        btnGallery = findViewById(R.id.btn_gallery)
        btnSettings = findViewById(R.id.btn_settings)
        tvCaptureText = findViewById(R.id.tv_capture_text)

        // 人脸引导
        faceGuideView = findViewById(R.id.iv_face_outline)
        tvFaceAlignHint = findViewById(R.id.tv_face_align_hint)

        // 图片预览层
        layoutPreview = findViewById(R.id.layout_preview)
        ivPreview = findViewById(R.id.iv_preview)
        btnRetake = findViewById(R.id.btn_retake)
        btnConfirm = findViewById(R.id.btn_confirm)

        // 分析蒙层
        layoutAnalyzing = findViewById(R.id.layout_analyzing)
        ivCloseAnalyzing = findViewById(R.id.iv_close_analyzing)
        tvAnalyzingTitle = findViewById(R.id.tv_analyzing_title)
        tvAnalyzingSubtitle = findViewById(R.id.tv_analyzing_subtitle)
        tvUploadProgress = findViewById(R.id.tv_upload_progress)
        viewProgressFill = findViewById(R.id.view_progress_fill)
        viewProgressGlow = findViewById(R.id.view_progress_glow)
        layoutScanAnimation = findViewById(R.id.layout_scan_animation)
        viewRing1 = findViewById(R.id.view_ring1)
        viewRing2 = findViewById(R.id.view_ring2)
        viewRing3 = findViewById(R.id.view_ring3)
        viewAnalyzingScanLine = findViewById(R.id.view_analyzing_scan_line)
        viewGlow1 = findViewById(R.id.view_glow1)
        viewGlow2 = findViewById(R.id.view_glow2)

        // 分析项
        analysisItems = listOf(
            findViewById(R.id.item_analysis_1),
            findViewById(R.id.item_analysis_2),
            findViewById(R.id.item_analysis_3),
            findViewById(R.id.item_analysis_4),
            findViewById(R.id.item_analysis_5),
            findViewById(R.id.item_analysis_6),
            findViewById(R.id.item_analysis_7),
            findViewById(R.id.item_analysis_8)
        )
        itemIcons = listOf(
            findViewById(R.id.item_icon_1),
            findViewById(R.id.item_icon_2),
            findViewById(R.id.item_icon_3),
            findViewById(R.id.item_icon_4),
            findViewById(R.id.item_icon_5),
            findViewById(R.id.item_icon_6),
            findViewById(R.id.item_icon_7),
            findViewById(R.id.item_icon_8)
        )
        itemTexts = listOf(
            findViewById(R.id.item_text_1),
            findViewById(R.id.item_text_2),
            findViewById(R.id.item_text_3),
            findViewById(R.id.item_text_4),
            findViewById(R.id.item_text_5),
            findViewById(R.id.item_text_6),
            findViewById(R.id.item_text_7),
            findViewById(R.id.item_text_8)
        )
        itemStatuses = listOf(
            findViewById(R.id.item_status_1),
            findViewById(R.id.item_status_2),
            findViewById(R.id.item_status_3),
            findViewById(R.id.item_status_4),
            findViewById(R.id.item_status_5),
            findViewById(R.id.item_status_6),
            findViewById(R.id.item_status_7),
            findViewById(R.id.item_status_8)
        )

        // 完成动画
        layoutComplete = findViewById(R.id.layout_complete)
        viewCompleteCircle = findViewById(R.id.view_complete_circle)
        ivCompleteCheck = findViewById(R.id.iv_complete_check)
        tvCompleteText = findViewById(R.id.tv_complete_text)

        // 粒子
        particles = listOf(
            findViewById(R.id.particle1),
            findViewById(R.id.particle2),
            findViewById(R.id.particle3),
            findViewById(R.id.particle4),
            findViewById(R.id.particle5),
            findViewById(R.id.particle6)
        )
    }

    private fun setupListeners() {
        ivBack.setOnClickListener {
            onBackPressedDispatcher.onBackPressed()
        }

        btnCapture.setOnClickListener {
            if (lastAlignState == FaceAlignState.NO_FACE) {
                showNoFaceDialog()
                return@setOnClickListener
            }
            takePhoto()
        }

        btnGallery.setOnClickListener {
            galleryLauncher.launch("image/*")
        }

        btnSettings.setOnClickListener {
            Toast.makeText(this, "设置功能开发中", Toast.LENGTH_SHORT).show()
        }

        btnRetake.setOnClickListener {
            retakePhoto()
        }

        btnConfirm.setOnClickListener {
            validateCapturedFaceThen {
                when (testType) {
                    "3d" -> uploadImageFor3D()
                    "face" -> uploadImageForFace()
                    else -> uploadImageForSkin()
                }
            }
        }

        ivCloseAnalyzing.setOnClickListener {
            // 关闭分析，返回预览
            stopAnalyzingAnimations()
            layoutAnalyzing.visibility = View.GONE
            if (capturedImageFile != null) {
                showPreview()
            } else {
                showCameraPreview()
            }
        }
    }

    /**
     * 对最终照片做一次静态人脸校验，覆盖手动拍照、自动拍照和相册选择。
     */
    private fun validateCapturedFaceThen(onFaceFound: () -> Unit) {
        if (faceValidationInProgress) return
        val file = capturedImageFile
        if (file == null || !file.exists()) {
            Toast.makeText(this, "图片文件不存在", Toast.LENGTH_SHORT).show()
            return
        }

        val inputImage = try {
            InputImage.fromFilePath(this, Uri.fromFile(file))
        } catch (e: Exception) {
            Log.e(TAG, "读取待检测照片失败", e)
            showNoFaceDialog("无法识别当前照片，请重新拍摄清晰、完整的正脸")
            return
        }
        val detector = FaceDetection.getClient(
            FaceDetectorOptions.Builder()
                .setPerformanceMode(FaceDetectorOptions.PERFORMANCE_MODE_ACCURATE)
                .setMinFaceSize(0.15f)
                .build()
        )

        faceValidationInProgress = true
        btnConfirm.isEnabled = false
        detector.process(inputImage)
            .addOnSuccessListener { faces ->
                faceValidationInProgress = false
                btnConfirm.isEnabled = true
                if (isFinishing || isDestroyed) return@addOnSuccessListener
                if (faces.isEmpty()) {
                    showNoFaceDialog()
                } else {
                    onFaceFound()
                }
            }
            .addOnFailureListener { error ->
                Log.e(TAG, "最终照片人脸校验失败", error)
                faceValidationInProgress = false
                btnConfirm.isEnabled = true
                if (!isFinishing && !isDestroyed) {
                    showNoFaceDialog("人脸检测失败，请重新拍摄清晰、完整的正脸")
                }
            }
            .addOnCompleteListener {
                detector.close()
            }
    }

    private fun showNoFaceDialog(
        message: String = "照片中未检测到人脸，请将完整正脸放入取景框并保持光线充足"
    ) {
        if (isFinishing || isDestroyed || noFaceDialog?.isShowing == true) return
        noFaceDialog = android.app.AlertDialog.Builder(this)
            .setTitle("未检测到人脸")
            .setMessage(message)
            .setPositiveButton("重新拍照") { _, _ -> retakePhoto() }
            .setNegativeButton("取消", null)
            .setCancelable(true)
            .create()
            .also { dialog ->
                dialog.setOnDismissListener { noFaceDialog = null }
                dialog.show()
            }
    }

    // ────── TTS 初始化 ──────
    private fun initTts() {
        tts = TextToSpeech(this, this)
    }

    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            val result = tts?.setLanguage(Locale.CHINESE)
            if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                Log.w(TAG, "TTS 中文语言不支持")
            }
            tts?.setSpeechRate(0.9f)
            ttsReady = true
            Log.i(TAG, "TTS 初始化完成")
        } else {
            Log.e(TAG, "TTS 初始化失败: $status")
        }
    }

    private fun speak(text: String) {
        if (!ttsReady) return
        tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "face_align_${System.currentTimeMillis()}")
    }

    // ────── 人脸对齐结果处理 + TTS 联动 ──────
    private fun handleFaceAlignResult(result: FaceAlignResult) {
        if (currentState != STATE_PREVIEW) return

        val now = System.currentTimeMillis()
        val state = result.state

        // 更新人脸导向框位置（跟随检测到的人脸移动/缩放）
        runOnUiThread {
            if (state != FaceAlignState.NO_FACE && result.faceWidthPx > 0f) {
                faceGuideView.updateFacePositionPx(
                    result.faceCenterPxX,
                    result.faceCenterPxY,
                    result.faceWidthPx,
                    result.faceHeightPx
                )
            } else {
                faceGuideView.resetToDefault()
            }
        }

        // 更新 UI 提示文字
        runOnUiThread {
            when (state) {
                FaceAlignState.NO_FACE -> {
                    tvFaceAlignHint.text = "请正对镜头，将整张脸放入圆形提示框"
                    tvFaceAlignHint.visibility = View.VISIBLE
                }
                FaceAlignState.TOO_CLOSE -> {
                    tvFaceAlignHint.text = "手机离脸远一点"
                    tvFaceAlignHint.visibility = View.VISIBLE
                }
                FaceAlignState.OFFSET_LEFT -> {
                    tvFaceAlignHint.text = "头部向右移动一点"
                    tvFaceAlignHint.visibility = View.VISIBLE
                }
                FaceAlignState.OFFSET_RIGHT -> {
                    tvFaceAlignHint.text = "头部向左移动一点"
                    tvFaceAlignHint.visibility = View.VISIBLE
                }
                FaceAlignState.OFFSET_UP -> {
                    tvFaceAlignHint.text = "头部向下移动一点"
                    tvFaceAlignHint.visibility = View.VISIBLE
                }
                FaceAlignState.OFFSET_DOWN -> {
                    tvFaceAlignHint.text = "头部向上移动一点"
                    tvFaceAlignHint.visibility = View.VISIBLE
                }
                FaceAlignState.ALIGNED -> {
                    tvFaceAlignHint.text = "人脸对齐完成，即将自动拍摄"
                    tvFaceAlignHint.visibility = View.VISIBLE
                }
            }
        }

        // TTS 语音播报（带冷却时间，避免频繁播报）
        if (state != lastTtsState || (now - lastTtsTimeMs) > TTS_COOLDOWN_MS) {
            when (state) {
                FaceAlignState.NO_FACE -> {
                    if (lastTtsState != FaceAlignState.NO_FACE || (now - lastTtsTimeMs) > TTS_COOLDOWN_MS) {
                        speak("请正对镜头，将整张脸放入圆形提示框")
                        lastTtsState = state
                        lastTtsTimeMs = now
                    }
                }
                FaceAlignState.TOO_CLOSE -> {
                    speak("手机离脸远一点")
                    lastTtsState = state
                    lastTtsTimeMs = now
                }
                FaceAlignState.OFFSET_LEFT -> {
                    speak("头部向右移动一点")
                    lastTtsState = state
                    lastTtsTimeMs = now
                }
                FaceAlignState.OFFSET_RIGHT -> {
                    speak("头部向左移动一点")
                    lastTtsState = state
                    lastTtsTimeMs = now
                }
                FaceAlignState.OFFSET_UP -> {
                    speak("头部向下移动一点")
                    lastTtsState = state
                    lastTtsTimeMs = now
                }
                FaceAlignState.OFFSET_DOWN -> {
                    speak("头部向上移动一点")
                    lastTtsState = state
                    lastTtsTimeMs = now
                }
                FaceAlignState.ALIGNED -> {
                    // 连续 2 秒稳定对齐才播报完成
                    if (alignedStartTimeMs == 0L) {
                        alignedStartTimeMs = now
                    } else if (!hasAnnouncedAligned && (now - alignedStartTimeMs) >= 2000L) {
                        speak("人脸对齐完成，即将自动拍摄")
                        hasAnnouncedAligned = true
                        lastTtsState = state
                        lastTtsTimeMs = now
                        // 自动拍照
                        if (!hasAutoCaptured) {
                            hasAutoCaptured = true
                            runOnUiThread { takePhoto() }
                        }
                    }
                }
            }
        }

        // 如果状态不再是 ALIGNED，重置对齐计时
        if (state != FaceAlignState.ALIGNED) {
            alignedStartTimeMs = 0L
            hasAnnouncedAligned = false
            hasAutoCaptured = false
        }

        lastAlignState = state
    }

    private fun checkCameraPermission(): Boolean {
        return if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED
        ) {
            true
        } else {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.CAMERA),
                CAMERA_PERMISSION_CODE
            )
            false
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == CAMERA_PERMISSION_CODE) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                startCamera()
            } else {
                Toast.makeText(this, "需要相机权限才能进行测肤", Toast.LENGTH_LONG).show()
                finish()
            }
        }
    }

    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)

        cameraProviderFuture.addListener({
            val cameraProvider = cameraProviderFuture.get()

            // 预览：根据窗口方向设置
            val preview = Preview.Builder()
                .setTargetRotation(previewView.display.rotation)
                .build()
                .also {
                    it.setSurfaceProvider(previewView.surfaceProvider)
                }

            // 图片捕获：与预览方向保持一致，保持原始比例不裁剪
            imageCapture = ImageCapture.Builder()
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
                .setTargetRotation(previewView.display.rotation)
                .build()

            // ImageAnalysis：用于 MediaPipe 人脸检测
            // 分辨率限制为 640x480，足够 MediaPipe 用，同时减少帧占用
            val resolutionSelector = ResolutionSelector.Builder()
                .setResolutionStrategy(
                    ResolutionStrategy(
                        android.util.Size(640, 480),
                        ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER
                    )
                )
                .build()

            imageAnalysis = ImageAnalysis.Builder()
                .setTargetRotation(previewView.display.rotation)
                .setResolutionSelector(resolutionSelector)
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_YUV_420_888)
                .build()

            // 等 FaceGuideView 布局完成后再创建分析器
            faceGuideView.post {
                try {
                    val analyzer = FaceAlignmentAnalyzer(
                        faceGuideView = faceGuideView,
                        previewWidth = 640,
                        previewHeight = 480
                    ) { result ->
                        handleFaceAlignResult(result)
                    }
                    faceAlignAnalyzer = analyzer
                    imageAnalysis?.setAnalyzer(cameraExecutor, analyzer)
                    Log.i(TAG, "FaceAlignmentAnalyzer 已设置")
                } catch (e: Exception) {
                    Log.e(TAG, "创建 FaceAlignmentAnalyzer 失败: ${e.message}", e)
                }
            }

            // 选择前置摄像头
            val cameraSelector = CameraSelector.DEFAULT_FRONT_CAMERA

            try {
                cameraProvider.unbindAll()
                cameraProvider.bindToLifecycle(
                    this,
                    cameraSelector,
                    preview,
                    imageCapture,
                    imageAnalysis
                )
            } catch (e: Exception) {
                Log.e(TAG, "相机绑定失败", e)
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun takePhoto() {
        val imageCapture = imageCapture ?: return

        btnCapture.isEnabled = false

        val photoFile = createImageFile()

        val outputOptions = ImageCapture.OutputFileOptions.Builder(photoFile).build()

        imageCapture.takePicture(
            outputOptions,
            ContextCompat.getMainExecutor(this),
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    if (isFinishing || isDestroyed) return
                    capturedFromFrontCamera = true
                    capturedImageNormalized = false
                    capturedImageFile = photoFile
                    showPreview()
                    btnCapture.isEnabled = true
                }

                override fun onError(exception: ImageCaptureException) {
                    Log.e(TAG, "拍照失败: ${exception.message}", exception)
                    Toast.makeText(this@SmartSkinTestActivity, "拍照失败", Toast.LENGTH_SHORT).show()
                    btnCapture.isEnabled = true
                }
            }
        )
    }

    private fun createImageFile(): File {
        val timeStamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(System.currentTimeMillis())
        val imageFileName = "SKIN_${timeStamp}_"
        val storageDir = getExternalFilesDir(Environment.DIRECTORY_PICTURES)
        return File.createTempFile(imageFileName, ".jpg", storageDir)
    }

    private fun showPreview() {
        if (isFinishing || isDestroyed || photoWorker.isShutdown) return
        currentState = STATE_CAPTURED
        layoutPreview.visibility = View.VISIBLE
        layoutAnalyzing.visibility = View.GONE
        tvFaceAlignHint.visibility = View.GONE
        btnConfirm.isEnabled = false
        val file = capturedImageFile ?: return
        val normalized = capturedImageNormalized
        val mirror = capturedFromFrontCamera
        val token = ++previewGeneration
        photoWorker.execute {
            var bitmap: android.graphics.Bitmap? = null
            var success = normalized
            try {
                bitmap = if (normalized) SafeBitmaps.decodeFile(file.absolutePath)
                    else loadCorrectOrientedBitmap(file.absolutePath, mirror)
                if (bitmap != null && !normalized) {
                    val temp = File.createTempFile("normalized_", ".jpg", file.parentFile)
                    try {
                        success = temp.outputStream().use { bitmap.compress(Bitmap.CompressFormat.JPEG, 95, it) }
                        if (success) success = temp.renameTo(file)
                    } finally { temp.delete() }
                }
            } catch (e: Exception) { Log.e(TAG, "图片处理失败", e); success = false }
            runOnUiThread {
                if (token != previewGeneration || isFinishing || isDestroyed || capturedImageFile != file) {
                    bitmap?.recycle(); return@runOnUiThread
                }
                if (bitmap != null && success) {
                    capturedImageNormalized = true; capturedFromFrontCamera = false
                    ivPreview.setImageBitmap(bitmap)
                    btnConfirm.isEnabled = true
                } else {
                    bitmap?.recycle()
                    Toast.makeText(this, "图片处理失败，请重新拍照", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    /**
     * 将图片标准化为正常方向。前摄拍照图额外水平翻转一次，恢复真实左右方向；
     * 相册图片不做镜像纠正，只处理 EXIF 旋转。
     */
    private fun loadCorrectOrientedBitmap(path: String, mirrorHorizontally: Boolean): Bitmap? {
        try {
            val originalBitmap = SafeBitmaps.decodeFile(path) ?: return null

            // 读取 EXIF 旋转角度
            var rotationDegrees = 0
            try {
                val exif = android.media.ExifInterface(path)
                rotationDegrees = when (exif.getAttributeInt(
                    android.media.ExifInterface.TAG_ORIENTATION,
                    android.media.ExifInterface.ORIENTATION_NORMAL
                )) {
                    android.media.ExifInterface.ORIENTATION_ROTATE_90 -> 90
                    android.media.ExifInterface.ORIENTATION_ROTATE_180 -> 180
                    android.media.ExifInterface.ORIENTATION_ROTATE_270 -> 270
                    else -> 0
                }
            } catch (_: Exception) {}

            if (rotationDegrees == 0 && !mirrorHorizontally) {
                Log.i(TAG, "图片无需方向或镜像纠正")
                return originalBitmap
            }

            val matrix = android.graphics.Matrix()
            if (rotationDegrees != 0) {
                matrix.postRotate(rotationDegrees.toFloat())
            }
            if (mirrorHorizontally) {
                // 前摄预览保留自拍镜像；保存和上传时恢复真实左右方向。
                matrix.postScale(-1f, 1f)
            }

            val resultBitmap = Bitmap.createBitmap(
                originalBitmap, 0, 0,
                originalBitmap.width, originalBitmap.height,
                matrix, true
            )

            if (resultBitmap != originalBitmap) {
                originalBitmap.recycle()
            }

            Log.i(
                TAG,
                "图片标准化完成: rotation=$rotationDegrees, mirror=$mirrorHorizontally, " +
                    "size=${resultBitmap.width}x${resultBitmap.height}"
            )
            return resultBitmap
        } catch (_: OutOfMemoryError) {
            return null
        } catch (e: Exception) {
            Log.e(TAG, "加载并修正图片失败: ${e.message}", e)
            return null
        }
    }

    private fun retakePhoto() {
        previewGeneration++
        currentState = STATE_PREVIEW
        layoutPreview.visibility = View.GONE
        tvFaceAlignHint.visibility = View.VISIBLE
        // 重置对齐状态
        lastAlignState = FaceAlignState.NO_FACE
        alignedStartTimeMs = 0L
        hasAnnouncedAligned = false
        hasAutoCaptured = false
        lastTtsState = null
        lastTtsTimeMs = 0L
        capturedImageFile?.delete()
        capturedImageFile = null
        capturedFromFrontCamera = false
        capturedImageNormalized = false
    }

    private fun showCameraPreview() {
        currentState = STATE_PREVIEW
        lastAlignState = FaceAlignState.NO_FACE
        layoutPreview.visibility = View.GONE
        layoutAnalyzing.visibility = View.GONE
        tvFaceAlignHint.visibility = View.VISIBLE
    }

    private fun startAnalyzing() {
        currentState = STATE_ANALYZING
        layoutPreview.visibility = View.GONE
        layoutAnalyzing.visibility = View.VISIBLE
        layoutComplete.visibility = View.GONE
        tvFaceAlignHint.visibility = View.GONE

        when (testType) {
            "skin" -> {
                // skin 类型：显示完整的分析蒙层（扫描动画 + 分析项列表）
                tvAnalyzingTitle.text = "正在深度分析你的肌肤"
                tvAnalyzingSubtitle.text = "请勿退出页面"
                tvUploadProgress.text = "上传 0%"
                viewProgressFill.layoutParams.width = 0
                viewProgressGlow.visibility = View.GONE

                // 重置分析项状态
                for (i in analysisItems.indices) {
                    itemIcons[i].setBackgroundResource(R.drawable.analysis_item_inactive)
                    itemTexts[i].setTextColor(ContextCompat.getColor(this, R.color.white_60))
                    itemStatuses[i].text = ""
                }

                // 启动完整分析动画
                startAnalyzingAnimations()
            }
            "3d" -> {
                // 3D 类型：显示简单的 loading 蒙层
                tvAnalyzingTitle.text = "正在生成 3D 人脸模型"
                tvAnalyzingSubtitle.text = "请勿退出页面"
                tvUploadProgress.text = "上传 0%"
                viewProgressFill.layoutParams.width = 0
                viewProgressGlow.visibility = View.GONE

                // 隐藏分析项列表（只显示简单的进度条和旋转动画）
                for (i in analysisItems.indices) {
                    analysisItems[i].visibility = View.GONE
                }

                // 只启动旋转动画，不启动分析项动画
                startRingAnimationsOnly()
            }
            "face" -> {
                // face 类型：显示简单的 loading 蒙层
                tvAnalyzingTitle.text = "正在分析脸型特征"
                tvAnalyzingSubtitle.text = "请勿退出页面"
                tvUploadProgress.text = "上传 0%"
                viewProgressFill.layoutParams.width = 0
                viewProgressGlow.visibility = View.GONE

                // 隐藏分析项列表
                for (i in analysisItems.indices) {
                    analysisItems[i].visibility = View.GONE
                }

                // 只启动旋转动画
                startRingAnimationsOnly()
            }
        }

        // 上传图片
        uploadImage()
    }

    /**
     * 统一上传入口：所有 type（skin/3d/face）都用同一个两步 OSS 上传流程
     * 与小程序 uploadToOSS() 完全一致：
     *   1. GET /api/oss/upload-params → 获取 host, policy, ossAccessKeyId, signature, dir
     *   2. POST {host} 直传文件到 OSS（formData: name, policy, OSSAccessKeyId, success_action_status, signature, key）
     *   3. 上传成功 → ossKey = dir + filename
     */
    private fun uploadToOSS(file: File, onSuccess: (ossKey: String) -> Unit, onFail: (String) -> Unit) {
        Log.i(TAG, "Step1: GET /api/oss/upload-params 获取 OSS 上传凭证")

        // Step 1: 通过 HttpHelper 获取 OSS 凭证（自动带 Bearer Token，解决 401 问题）
        HttpHelper.get(
            path = "/api/oss/upload-params",
            onSuccess = { bodyStr ->
                try {
                    Log.i(TAG, "OSS 凭证获取成功")
                    val json = JSONObject(bodyStr)
                    val data = if (json.has("data")) json.getJSONObject("data") else json

                    val host = data.getString("host")
                    val policy = data.getString("policy")
                    val ossAccessKeyId = data.getString("ossAccessKeyId")
                    val signature = data.getString("signature")
                    val dir = data.getString("dir")

                    // 生成文件名
                    var filename = file.name
                    if (filename.isEmpty() || !filename.contains(".")) {
                        filename = "img_${System.currentTimeMillis()}.png"
                    }
                    val key = dir + filename

                    Log.i(TAG, "Step2: 上传文件到 OSS")

                    // Step 2: 直传文件到 OSS（使用独立 client，不走 HttpHelper 拦截器）
                    val ossClient = OkHttpClient.Builder()
                        .connectTimeout(30, TimeUnit.SECONDS)
                        .writeTimeout(120, TimeUnit.SECONDS)
                        .readTimeout(60, TimeUnit.SECONDS)
                        .build()

                    val requestBody = MultipartBody.Builder()
                        .setType(MultipartBody.FORM)
                        .addFormDataPart("name", filename)
                        .addFormDataPart("policy", policy)
                        .addFormDataPart("OSSAccessKeyId", ossAccessKeyId)
                        .addFormDataPart("success_action_status", "200")
                        .addFormDataPart("signature", signature)
                        .addFormDataPart("key", key)
                        .addFormDataPart("file", filename, file.asRequestBody("image/jpeg".toMediaType()))
                        .build()

                    val uploadRequest = Request.Builder()
                        .url(host)
                        .post(requestBody)
                        .build()

                    ossClient.newCall(uploadRequest).enqueue(object : Callback {
                        override fun onFailure(call: Call, e: IOException) {
                            Log.e(TAG, "OSS 上传失败", e)
                            runOnUiThread { onFail("文件上传失败: ${e.message}") }
                        }

                        override fun onResponse(call: Call, response: Response) {
                            response.use { result ->
                                if (result.isSuccessful || result.code == 200 || result.code == 204) {
                                    Log.i(TAG, "OSS 上传成功")
                                    runOnUiThread { onSuccess(key) }
                                } else {
                                    Log.e(TAG, "OSS 上传失败: HTTP ${result.code}")
                                    runOnUiThread { onFail("OSS上传失败: HTTP ${result.code}") }
                                }
                            }
                        }
                    })
                } catch (e: Exception) {
                    Log.e(TAG, "解析 OSS 凭证失败", e)
                    runOnUiThread { onFail("解析上传凭证失败: ${e.message}") }
                }
            },
            onFailure = { code, errorMsg ->
                Log.e(TAG, "获取 OSS 凭证失败: HTTP $code, $errorMsg")
                runOnUiThread { onFail("获取上传凭证失败: $errorMsg") }
            }
        )
    }

    // 上传 loading 对话框
    private var uploadDialog: android.app.AlertDialog? = null

    private fun showUploadLoading() {
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = android.view.Gravity.CENTER
            val pad = (24 * resources.displayMetrics.density).toInt()
            setPadding(pad, pad, pad, pad)
        }
        val progressBar = android.widget.ProgressBar(this).apply { isIndeterminate = true }
        container.addView(progressBar)
        val tv = TextView(this).apply {
            text = "正在上传图片..."
            setTextColor(0xFF333333.toInt())
            textSize = 14f
            gravity = android.view.Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = (12 * resources.displayMetrics.density).toInt() }
        }
        container.addView(tv)
        uploadDialog = android.app.AlertDialog.Builder(this)
            .setView(container)
            .setCancelable(false)
            .create()
        uploadDialog?.window?.setBackgroundDrawableResource(android.R.color.transparent)
        uploadDialog?.show()
    }

    private fun dismissUploadLoading() {
        uploadDialog?.dismiss()
        uploadDialog = null
    }

    /**
     * 3D 类型：显示 loading → 上传到 OSS → 成功后跳转 Scan3DActivity
     */
    private fun uploadImageFor3D() {
        val file = capturedImageFile
        if (file == null || !file.exists()) {
            Toast.makeText(this, "图片文件不存在", Toast.LENGTH_SHORT).show()
            return
        }

        showUploadLoading()
        btnConfirm.isEnabled = false

        uploadToOSS(file,
            onSuccess = { ossKey ->
                dismissUploadLoading()
                btnConfirm.isEnabled = true
                uploadedOssKey = ossKey
                Log.i(TAG, "3D 上传完成")
                navigateToResult()
            },
            onFail = { error ->
                dismissUploadLoading()
                btnConfirm.isEnabled = true
                Log.e(TAG, "3D上传失败: $error")
                Toast.makeText(this@SmartSkinTestActivity, error, Toast.LENGTH_SHORT).show()
            }
        )
    }

    /**
     * Face 类型：显示 loading → 上传到 OSS → 成功后直接跳转 FaceResultActivity
     */
    private fun uploadImageForFace() {
        val file = capturedImageFile
        if (file == null || !file.exists()) {
            Toast.makeText(this, "图片文件不存在", Toast.LENGTH_SHORT).show()
            return
        }

        showUploadLoading()
        btnConfirm.isEnabled = false

        uploadToOSS(file,
            onSuccess = { ossKey ->
                dismissUploadLoading()
                btnConfirm.isEnabled = true
                uploadedOssKey = ossKey
                Log.i(TAG, "Face 上传完成")
                navigateToResult()
            },
            onFail = { error ->
                dismissUploadLoading()
                btnConfirm.isEnabled = true
                Log.e(TAG, "Face上传失败: $error")
                Toast.makeText(this@SmartSkinTestActivity, error, Toast.LENGTH_SHORT).show()
            }
        )
    }

    /**
     * Skin 类型：显示上传 loading → 上传到 OSS → 成功后直接跳转 SkinReportActivity
     * 分析蒙层和分析动画已搬到 SkinReportActivity 页面
     */
    private fun uploadImageForSkin() {
        val file = capturedImageFile
        if (file == null || !file.exists()) {
            Toast.makeText(this, "图片文件不存在", Toast.LENGTH_SHORT).show()
            return
        }

        showUploadLoading()
        btnConfirm.isEnabled = false

        uploadToOSS(file,
            onSuccess = { ossKey ->
                dismissUploadLoading()
                btnConfirm.isEnabled = true
                uploadedOssKey = ossKey
                Log.i(TAG, "Skin 上传完成")
                navigateToResult()
            },
            onFail = { error ->
                dismissUploadLoading()
                btnConfirm.isEnabled = true
                Log.e(TAG, "Skin上传失败: $error")
                Toast.makeText(this@SmartSkinTestActivity, error, Toast.LENGTH_SHORT).show()
            }
        )
    }

    /**
     * [已废弃] skin 类型旧逻辑：显示分析蒙层 → 上传到 OSS → 分析动画 → 完成动画
     * 分析蒙层已搬到 SkinReportActivity，此方法保留但不再被 skin 类型调用
     */
    private var analysisProgressTimer: com.example.aisia.ui.common.PausableCountdown? = null
    private var analysisItemTimer: com.example.aisia.ui.common.PausableCountdown? = null
    private var completionAnimator: AnimatorSet? = null
    private val resultHandler = android.os.Handler(android.os.Looper.getMainLooper())
    private var analysisVisible = false
    private var pendingResult = false
    private var resultNavigated = false
    private fun analysisAnimators() = listOfNotNull(ring1Animator, ring2Animator, ring3Animator, scanLineAnimator, glow1Animator, glow2Animator) + particleAnimators
    
    private fun uploadImage() {
        val file = capturedImageFile
        if (file == null || !file.exists()) {
            Toast.makeText(this, "图片文件不存在", Toast.LENGTH_SHORT).show()
            return
        }

        // 初始进度为0
        updateUploadProgress(0)

        uploadToOSS(file,
            onSuccess = { ossKey ->
                runOnUiThread {
                    uploadedOssKey = ossKey
                    Log.i(TAG, "skin 上传完成")
                    // 上传完成，开始分析进度（从20%到100%，与分析列表同步）
                    startAnalysisProgress()
                    startAnalysisItemsAnimation()
                }
            },
            onFail = { error ->
                runOnUiThread {
                    Log.e(TAG, "skin上传失败: $error")
                    // 上传失败也显示分析进度
                    startAnalysisProgress()
                    simulateAnalysis()
                }
            }
        )
    }
    
    /**
     * 开始分析进度动画（从20%到100%，与分析列表同步，总时长8秒）
     */
    private fun startAnalysisProgress() {
        analysisProgressTimer?.cancel()
        val totalDuration = 8000L  // 与分析列表同步
        val startProgress = 20
        val endProgress = 100
        
        analysisProgressTimer = object : com.example.aisia.ui.common.PausableCountdown(totalDuration, 100) {
            override fun onTick(millisUntilFinished: Long) {
                val elapsed = totalDuration - millisUntilFinished
                val progress = startProgress + ((endProgress - startProgress) * elapsed / totalDuration).toInt()
                updateUploadProgress(progress)
            }
            override fun onFinish() {
                updateUploadProgress(100)
            }
        }
        analysisProgressTimer?.start()
        if (!analysisVisible) analysisProgressTimer?.pause()
    }

    /**
     * 更新上传进度条
     */
    private fun updateUploadProgress(progress: Int) {
        tvUploadProgress.text = "分析 ${progress}%"
        val parentWidth = (viewProgressFill.parent as View).width
        val targetWidth = parentWidth * progress / 100
        viewProgressFill.layoutParams.width = targetWidth
        viewProgressFill.requestLayout()

        if (progress > 0) {
            viewProgressGlow.visibility = View.VISIBLE
            viewProgressGlow.translationX = targetWidth.toFloat() - viewProgressGlow.width / 2
        }
    }

    /**
     * 启动完整的分析动画（skin 类型用：旋转光圈 + 扫描线 + 光斑 + 粒子）
     */
    private fun startAnalyzingAnimations() {
        ring1Animator = ObjectAnimator.ofFloat(viewRing1, "rotation", 0f, 360f).apply {
            duration = 3000; repeatCount = ValueAnimator.INFINITE; interpolator = LinearInterpolator(); start()
        }
        ring2Animator = ObjectAnimator.ofFloat(viewRing2, "rotation", 360f, 0f).apply {
            duration = 2500; repeatCount = ValueAnimator.INFINITE; interpolator = LinearInterpolator(); start()
        }
        ring3Animator = ObjectAnimator.ofFloat(viewRing3, "rotation", 0f, 360f).apply {
            duration = 2000; repeatCount = ValueAnimator.INFINITE; interpolator = LinearInterpolator(); start()
        }
        layoutScanAnimation.post {
            val scanHeight = 130f
            scanLineAnimator = ObjectAnimator.ofFloat(viewAnalyzingScanLine, "translationY", 0f, scanHeight).apply {
                duration = 1500; repeatCount = ValueAnimator.INFINITE; repeatMode = ValueAnimator.REVERSE; interpolator = LinearInterpolator(); start()
            }
        }
        glow1Animator = ObjectAnimator.ofFloat(viewGlow1, "alpha", 0.2f, 0.5f, 0.2f).apply {
            duration = 3000; repeatCount = ValueAnimator.INFINITE; start()
        }
        glow2Animator = ObjectAnimator.ofFloat(viewGlow2, "alpha", 0.1f, 0.4f, 0.1f).apply {
            duration = 2500; repeatCount = ValueAnimator.INFINITE; start()
        }
        particleAnimators = particles.mapIndexed { index, particle ->
            val duration = 2000L + (index * 300L)
            ObjectAnimator.ofFloat(particle, "translationY", -10f, 10f, -10f).apply {
                this.duration = duration; repeatCount = ValueAnimator.INFINITE; interpolator = AccelerateDecelerateInterpolator(); start()
            }
        }
    }

    /**
     * 仅启动旋转动画（3D 和 face 类型用）
     */
    private fun startRingAnimationsOnly() {
        ring1Animator = ObjectAnimator.ofFloat(viewRing1, "rotation", 0f, 360f).apply {
            duration = 3000; repeatCount = ValueAnimator.INFINITE; interpolator = LinearInterpolator(); start()
        }
        ring2Animator = ObjectAnimator.ofFloat(viewRing2, "rotation", 360f, 0f).apply {
            duration = 2500; repeatCount = ValueAnimator.INFINITE; interpolator = LinearInterpolator(); start()
        }
        ring3Animator = ObjectAnimator.ofFloat(viewRing3, "rotation", 0f, 360f).apply {
            duration = 2000; repeatCount = ValueAnimator.INFINITE; interpolator = LinearInterpolator(); start()
        }
    }

    /**
     * 停止所有分析动画
     */
    private fun stopAnalyzingAnimations() {
        ring1Animator?.cancel(); ring1Animator = null
        ring2Animator?.cancel(); ring2Animator = null
        ring3Animator?.cancel(); ring3Animator = null
        scanLineAnimator?.cancel(); scanLineAnimator = null
        glow1Animator?.cancel(); glow1Animator = null
        glow2Animator?.cancel(); glow2Animator = null
        particleAnimators.forEach { it.cancel() }
        particleAnimators = emptyList()
    }

    private fun simulateAnalysis() {
        // 模拟分析过程
        startAnalysisItemsAnimation()
    }

    private fun startAnalysisItemsAnimation() {
        tvAnalyzingSubtitle.text = "正在进行智能深度分析..."

        var currentItem = 0
        analysisItemTimer?.cancel()
        val itemTimer = object : com.example.aisia.ui.common.PausableCountdown(8000L, 1000L) {
            override fun onTick(millisUntilFinished: Long) {
                if (currentItem < analysisItems.size) {
                    // 激活当前项
                    itemIcons[currentItem].setBackgroundResource(R.drawable.analysis_item_active)
                    itemTexts[currentItem].setTextColor(ContextCompat.getColor(this@SmartSkinTestActivity, R.color.white))
                    itemStatuses[currentItem].text = "分析中..."

                    // 完成前一项
                    if (currentItem > 0) {
                        itemIcons[currentItem - 1].setBackgroundResource(R.drawable.analysis_item_done)
                        itemStatuses[currentItem - 1].text = "完成"
                        itemStatuses[currentItem - 1].setTextColor(ContextCompat.getColor(this@SmartSkinTestActivity, R.color.cyan_light))
                    }
                    currentItem++
                }
            }

            override fun onFinish() {
                // 完成最后一项
                if (currentItem > 0 && currentItem <= analysisItems.size) {
                    itemIcons[currentItem - 1].setBackgroundResource(R.drawable.analysis_item_done)
                    itemStatuses[currentItem - 1].text = "完成"
                    itemStatuses[currentItem - 1].setTextColor(ContextCompat.getColor(this@SmartSkinTestActivity, R.color.cyan_light))
                }

                // 显示完成动画
                showCompleteAnimation()
            }
        }
        analysisItemTimer = itemTimer
        itemTimer.start()
        if (!analysisVisible) itemTimer.pause()
    }

    private fun showCompleteAnimation() {
        stopAnalyzingAnimations()

        layoutComplete.visibility = View.VISIBLE
        tvAnalyzingTitle.text = "分析完成"
        tvAnalyzingSubtitle.text = "正在生成您的专属报告"

        // 圆形放大动画
        val circleScaleX = ObjectAnimator.ofFloat(viewCompleteCircle, "scaleX", 0f, 1f)
        val circleScaleY = ObjectAnimator.ofFloat(viewCompleteCircle, "scaleY", 0f, 1f)

        // 勾号动画
        val checkScaleX = ObjectAnimator.ofFloat(ivCompleteCheck, "scaleX", 0f, 1f)
        val checkScaleY = ObjectAnimator.ofFloat(ivCompleteCheck, "scaleY", 0f, 1f)

        // 文字淡入
        val textAlpha = ObjectAnimator.ofFloat(tvCompleteText, "alpha", 0f, 1f)

        val animatorSet = AnimatorSet()
        animatorSet.playTogether(circleScaleX, circleScaleY)
        animatorSet.duration = 500
        animatorSet.interpolator = AccelerateDecelerateInterpolator()

        val checkSet = AnimatorSet()
        checkSet.playTogether(checkScaleX, checkScaleY)
        checkSet.duration = 300

        val fullSet = AnimatorSet()
        fullSet.playSequentially(animatorSet, checkSet, textAlpha)
        fullSet.addListener(object : AnimatorListenerAdapter() {
            override fun onAnimationEnd(animation: Animator) {
                // 延迟后跳转到结果页
                resultHandler.postDelayed({
                    navigateToResult()
                }, 1000)
            }
        })
        completionAnimator = fullSet
        fullSet.start()
        if (!analysisVisible) fullSet.pause()
    }

    private fun navigateToResult() {
        if (isFinishing || isDestroyed || resultNavigated) return
        if (!analysisVisible) { pendingResult = true; return }
        pendingResult = false; resultNavigated = true
        currentState = STATE_COMPLETE
        val imagePath = capturedImageFile?.absolutePath ?: ""
        
        val intent = when (testType) {
            "3d" -> {
                // 3D模型页 - 传递 oss_key 和 3dType=img
                Log.i(TAG, "跳转 Scan3DActivity")
                Intent(this, Scan3DActivity::class.java).apply {
                    putExtra(Scan3DActivity.EXTRA_OSS_KEY, uploadedOssKey)
                    putExtra("image_path", imagePath)
                    putExtra("3dType", "img")
                }
            }
            "face" -> {
                // 脸型检测页 - 传递 oss_key 用于调用颜值分析接口
                Log.i(TAG, "跳转 FaceResultActivity")
                Intent(this, FaceResultActivity::class.java).apply {
                    putExtra(FaceResultActivity.EXTRA_OSS_KEY, uploadedOssKey)
                    putExtra(FaceResultActivity.EXTRA_DEVICE_ID, "")
                    putExtra("image_path", imagePath)
                }
            }
            else -> {
                // 默认：肤质检测报告页 - 传递 oss_key 用于调用肤质分析接口
                Log.i(TAG, "跳转 SkinReportActivity")
                Intent(this, SkinReportActivity::class.java).apply {
                    putExtra("oss_key", uploadedOssKey)
                    putExtra("image_path", imagePath)
                }
            }
        }
        
        startActivity(intent)
        finish()
    }

    override fun onPause() {
        super.onPause()
        analysisVisible = false
        analysisProgressTimer?.pause(); analysisItemTimer?.pause()
        analysisAnimators().forEach { it.pause() }
        completionAnimator?.pause()
        // MediaPipe FaceLandmarker 会占用 GPU 内存（尤其是 GPU delegate），
        // 切到后台时主动释放，避免其他应用 GPU 压力
        faceAlignAnalyzer?.close()
        faceAlignAnalyzer = null
    }

    override fun onResume() {
        super.onResume()
        analysisVisible = true
        analysisProgressTimer?.resume(); analysisItemTimer?.resume()
        analysisAnimators().forEach { it.resume() }
        completionAnimator?.resume()
        if (pendingResult) navigateToResult()
        // 如果相机已启动但分析器被释放，重新创建
        if (currentState == STATE_PREVIEW && faceAlignAnalyzer == null) {
            faceGuideView.post {
                try {
                    val analyzer = FaceAlignmentAnalyzer(
                        faceGuideView = faceGuideView,
                        previewWidth = 640,
                        previewHeight = 480
                    ) { result ->
                        handleFaceAlignResult(result)
                    }
                    faceAlignAnalyzer = analyzer
                    imageAnalysis?.setAnalyzer(cameraExecutor, analyzer)
                } catch (e: Exception) {
                    Log.w(TAG, "onResume 重建 FaceAlignmentAnalyzer 失败: ${e.message}")
                }
            }
        }
    }

    override fun onDestroy() {
        analysisProgressTimer?.cancel(); analysisItemTimer?.cancel()
        stopAnalyzingAnimations()
        completionAnimator?.removeAllListeners(); completionAnimator?.cancel()
        resultHandler.removeCallbacksAndMessages(null)
        previewGeneration++
        photoWorker.shutdownNow()
        noFaceDialog?.dismiss()
        noFaceDialog = null
        cameraExecutor.shutdown()
        super.onDestroy()
    }
}
