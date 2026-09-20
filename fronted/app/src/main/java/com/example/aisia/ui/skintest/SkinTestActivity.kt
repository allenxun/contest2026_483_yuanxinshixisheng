package com.example.aisia.ui.skintest

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.View
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import android.util.Size
import android.os.Handler
import android.os.Looper
import android.widget.LinearLayout
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.example.aisia.BuildConfig
import com.example.aisia.R
import com.example.aisia.privacy.PrivacyManager
import com.example.aisia.ui.ai.AiAnalysisActivity
import java.io.File
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import kotlin.math.abs

/**
 * 测肤拍照页（多角度拍照 → 上传生成 3D 模型 → 模型效果改造）
 *
 * 工作流：
 *  1) CameraX 预览 + MediaPipe FaceLandmarker 实时检测人脸偏航角，屏幕提示当前角度
 *     - 正面：yaw 在 ±10° 内
 *     - 左脸：yaw > +25°（脸朝左）
 *     - 右脸：yaw < -25°（脸朝右）
 *  2) 当检测到的角度连续多帧都在目标范围内，拍照按钮亮起可点，点击拍一张
 *  3) 拍完 3 张后自动上传到 https://eveaisia.com/upload
 *  4) 服务端返回 GLB URL 后，加载 GlbModelView
 *  5) 下方水平列表选择效果（双眼皮/童话等），选中后调 /model/modify 重新生成并刷新模型
 */
class SkinTestActivity : AppCompatActivity() {

    // ────── 视图 ──────
    private lateinit var layoutCapture: View
    private lateinit var layoutModel3D: View
    private lateinit var layoutLoading: View
    private lateinit var previewView: PreviewView
    private lateinit var tvAngleHint: TextView
    private lateinit var tvAngleSubHint: TextView
    private lateinit var tvCaptureProgress: TextView
    private lateinit var tvLoadingText: TextView
    private lateinit var dots: Array<View>
    private lateinit var glbView: GlbModelView
    private lateinit var rvEffects: RecyclerView
    private lateinit var btnCapture: View
    private lateinit var btnGoAnalysis: View
    // preview / analyzing overlays
    private lateinit var previewOverlay: View
    private lateinit var ivPreview: android.widget.ImageView
    private lateinit var btnRetake: View
    private lateinit var btnConfirm: View
    private lateinit var analyzingOverlay: View
    private lateinit var tvUploadProgressLabel: TextView
    private lateinit var viewUploadFill: View
    private lateinit var layoutAnalysisItems: LinearLayout

    // ────── 相机 ──────
    private var imageCapture: ImageCapture? = null
    private lateinit var cameraExecutor: ExecutorService

    // ────── 业务状态 ──────
    private val captureSteps = listOf(
        Step(R.string.skin_test_step_front,    R.string.skin_test_step_front_sub,    "front"),
        Step(R.string.skin_test_step_left,     R.string.skin_test_step_left_sub,     "left"),
        Step(R.string.skin_test_step_right,    R.string.skin_test_step_right_sub,    "right"),
    )
    private var currentStep = 0
    private val capturedFiles = arrayOfNulls<File>(3)

    private var currentGlbUrl: String? = null
    private var selectedEffectId: String? = null

    // ────── 人脸角度检测（MediaPipe） ──────
    private var faceAnalyzer: FaceAngleAnalyzer? = null
    private var imageAnalysis: ImageAnalysis? = null
    private var stableFrames: Int = 0        // 连续帧数（当前角度在目标范围内）
    private val requiredStableFrames = 8    // 需连续 8 帧（约 0.3s）才允许拍照

    // 角度阈值
    private val frontYawTolerance = 15f     // 正面允许 ±15°
    private val sideTargetYaw = 35f          // 侧脸目标 yaw（±35°）
    private val sideYawTolerance = 15f        // 侧脸容差
    private val pitchTolerance = 15f         // 俯仰角容差

    // 人脸距离阈值（两眼外眼角距离占画面宽度的比例，归一化 0~1）
    private val minFaceSize = 0.22f
    private val maxFaceSize = 0.45f

    /** 获取当前步骤期望的 yaw 目标值 */
    private fun targetYaw(): Float = when (captureSteps[currentStep].key) {
        "front" -> 0f
        "left"  -> sideTargetYaw
        "right" -> -sideTargetYaw
        else    -> 0f
    }

    /** 当前步骤对 yaw 的允许范围 */
    private fun yawAllowedRange(): ClosedFloatingPointRange<Float> {
        return when (captureSteps[currentStep].key) {
            "front" -> -frontYawTolerance..frontYawTolerance
            "left"  -> (sideTargetYaw - sideYawTolerance)..(sideTargetYaw + sideYawTolerance)
            "right" -> (-sideTargetYaw - sideYawTolerance)..(-sideTargetYaw + sideYawTolerance)
            else    -> -frontYawTolerance..frontYawTolerance
        }
    }

    /**
     * 当前帧是否“合格”（角度 + 距离都 OK）。
     * 为了防止越拍越接近，要求 yaw 与目标方向一致且不超越另一侧。
     */
    private fun isFrameAcceptable(result: FaceAngleAnalyzer.FaceAngleResult): Boolean {
        val range = yawAllowedRange()
        if (result.yawDeg !in range) return false
        if (abs(result.pitchDeg) > pitchTolerance) return false
        if (result.faceSizeRatio < minFaceSize || result.faceSizeRatio > maxFaceSize) return false
        return true
    }

    private data class Step(val titleRes: Int, val subRes: Int, val key: String)

    data class Effect(val id: String, val name: String, val emoji: String)

    // 效果列表
    private val effects = listOf(
        Effect("double_eyelid", "双眼皮", "👁"),
        Effect("fairy",         "童话效果", "✨"),
        Effect("slim_face",     "瘦脸", "🌸"),
        Effect("smooth_skin",   "磨皮", "💧"),
        Effect("bright_eye",    "亮眼", "⭐"),
        Effect("plump_lip",     "丰唇", "💋"),
    )

    private lateinit var effectAdapter: EffectAdapter

    // 权限请求
    private val cameraPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) startCamera() else toast("需要相机权限")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_skin_test)

        bindViews()
        setupEffectsList()

        // 返回按钮
        findViewById<View>(R.id.btnBack).setOnClickListener { finish() }

        cameraExecutor = Executors.newSingleThreadExecutor()

        // 初始显示拍照阶段
        showCaptureStep()

        // 拍照按钮（角度稳定后才会启用）
        btnCapture.setOnClickListener { captureCurrentStep() }
        btnCapture.isEnabled = false
        btnCapture.alpha = 0.45f

        // 重置视角
        findViewById<View>(R.id.btnResetView).setOnClickListener {
            glbView.resetCamera()
        }

        btnGoAnalysis.setOnClickListener {
            startActivity(Intent(this, AiAnalysisActivity::class.java))
        }

        ensureCameraPermission()
    }

    private fun bindViews() {
        layoutCapture = findViewById(R.id.layoutCapture)
        layoutModel3D = findViewById(R.id.layoutModel3D)
        layoutLoading = findViewById(R.id.layoutLoading)
        previewView = findViewById(R.id.previewView)
        tvAngleHint = findViewById(R.id.tvAngleHint)
        tvAngleSubHint = findViewById(R.id.tvAngleSubHint)
        tvCaptureProgress = findViewById(R.id.tvCaptureProgress)
        tvLoadingText = findViewById(R.id.tvLoadingText)
        glbView = findViewById(R.id.glbView)
        rvEffects = findViewById(R.id.rvEffects)
        btnCapture = findViewById(R.id.btnCapture)
        btnGoAnalysis = findViewById(R.id.btnGoAnalysis)
        previewOverlay = findViewById(R.id.previewOverlay)
        ivPreview = findViewById(R.id.ivPreview)
        btnRetake = findViewById(R.id.btnRetake)
        btnConfirm = findViewById(R.id.btnConfirm)
        analyzingOverlay = findViewById(R.id.analyzingOverlay)
        tvUploadProgressLabel = findViewById(R.id.tvUploadProgressLabel)
        viewUploadFill = findViewById(R.id.viewUploadFill)
        layoutAnalysisItems = findViewById(R.id.layoutAnalysisItems)
        dots = arrayOf(
            findViewById(R.id.dotFront),
            findViewById(R.id.dotLeft),
            findViewById(R.id.dotRight)
        )
    }

    private fun setupEffectsList() {
        effectAdapter = EffectAdapter(effects) { effect ->
            onEffectSelected(effect)
        }
        rvEffects.layoutManager = LinearLayoutManager(this, RecyclerView.HORIZONTAL, false)
        rvEffects.adapter = effectAdapter
    }

    private fun ensureCameraPermission() {
        // 合规要求：用户同意隐私政策后才能申请相机权限
        PrivacyManager.ensureAgreed(this) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
                == PackageManager.PERMISSION_GRANTED
            ) {
                startCamera()
            } else {
                cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
            }
        }
    }

    private fun startCamera() {
        val providerFuture = ProcessCameraProvider.getInstance(this)
        providerFuture.addListener({
            try {
                val provider = providerFuture.get()
                val preview = Preview.Builder().build().also {
                    it.setSurfaceProvider(previewView.surfaceProvider)
                }
                imageCapture = ImageCapture.Builder()
                    .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
                    .build()

                // 人脸角度分析（MediaPipe FaceLandmarker）
                val analyzer = FaceAngleAnalyzer(this) { result ->
                    runOnUiThread { onFaceAnalyzed(result) }
                }
                faceAnalyzer = analyzer
                // 分辨率限制为 640x480，足够 MediaPipe 用，同时大幅减少帧占用
                val resolutionSelector = ResolutionSelector.Builder()
                    .setResolutionStrategy(ResolutionStrategy(Size(640, 480), ResolutionStrategy.FALLBACK_RULE_CLOSEST_LOWER_THEN_HIGHER))
                    .build()
                val newImageAnalysis = ImageAnalysis.Builder()
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .setResolutionSelector(resolutionSelector)
                    .build()
                    .also { it.setAnalyzer(cameraExecutor, analyzer) }
                imageAnalysis = newImageAnalysis

                provider.unbindAll()
                provider.bindToLifecycle(
                    this,
                    CameraSelector.DEFAULT_FRONT_CAMERA,
                    preview,
                    imageCapture,
                    newImageAnalysis
                )
            } catch (e: Exception) {
                toast("相机启动失败：${e.message}")
            }
        }, ContextCompat.getMainExecutor(this))
    }

    /**
     * 每帧人脸检测回调
     * - 更新副标题为实时角度（提示用户调整头部方向）
     * - 累计连续帧，达到稳定阈值后拍照按钮亮起
     *
     * 重要约定（需与 FaceAngleAnalyzer 输出对齐）：
     *  - yawDeg > 0 表示脸朝用户左边
     *  - pitchDeg > 0 表示抬头
     */
    private fun onFaceAnalyzed(result: FaceAngleAnalyzer.FaceAngleResult) {
        if (layoutCapture.visibility != View.VISIBLE) return
        val target = targetYaw()

        if (!result.detected) {
            stableFrames = 0
            tvAngleSubHint.text = "未检测到人脸，请将脸部对准镜头"
            updateCaptureButton(enabled = false, hint = "未检测到人脸")
            return
        }

        val range = yawAllowedRange()
        val diff = result.yawDeg - target  // 0 表示刚好达到目标

        // 距离检查（根据 faceSizeRatio 判断远近）
        val distanceHint = when {
            result.faceSizeRatio < minFaceSize -> "请靠近一点"
            result.faceSizeRatio > maxFaceSize -> "请离远一点"
            else -> null
        }

        // 角度提示（yaw 与 target 的符号关系决定“应该转向哪边”）
        // 约定：yaw>0 表示脸偏左，yaw<0 表示脸偏右；diff=yaw-target
        //  - diff > 0：当前 yaw 偏大（脸偏左），需要让脸向右回一点
        //  - diff < 0：当前 yaw 偏小（脸偏右），需要让脸向左回一点
        val angleHint: String = when {
            distanceHint != null -> distanceHint  // 距离优先
            abs(diff) <= 1f && abs(result.pitchDeg) <= pitchTolerance -> "角度合适，请保持稳定"
            diff > 0f -> "脸偏左了，请向右回一点（当前 yaw=${result.yawDeg.toInt()}°，目标 ${target.toInt()}°）"
            diff < 0f -> "脸偏右了，请向左回一点（当前 yaw=${result.yawDeg.toInt()}°，目标 ${target.toInt()}°）"
            abs(result.pitchDeg) > pitchTolerance ->
                if (result.pitchDeg > 0) "请低头一点" else "请抬头一点"
            else -> "请保持稳定"
        }
        tvAngleSubHint.text = "yaw=${result.yawDeg.toInt()}° pitch=${result.pitchDeg.toInt()}° · $angleHint"

        if (isFrameAcceptable(result)) {
            stableFrames++
            if (stableFrames >= requiredStableFrames) {
                updateCaptureButton(enabled = true, hint = "✓ 角度稳定，可以拍照")
            } else {
                updateCaptureButton(enabled = false, hint = "保持稳定中 ${stableFrames}/${requiredStableFrames}")
            }
        } else {
            stableFrames = 0
            updateCaptureButton(enabled = false, hint = "调整中…")
        }
    }

    private fun updateCaptureButton(enabled: Boolean, hint: String) {
        btnCapture.isEnabled = enabled
        btnCapture.alpha = if (enabled) 1.0f else 0.45f
        // 把提示接到现有 tvAngleSubHint 已经显示
        if (hint.isNotEmpty() && enabled) {
            tvAngleSubHint.text = hint
        }
    }

    private fun showCaptureStep() {
        val step = captureSteps[currentStep]
        tvAngleHint.setText(step.titleRes)
        tvAngleSubHint.setText(step.subRes)
        tvCaptureProgress.text = "${currentStep} / 3"
        btnGoAnalysis.visibility = View.GONE
        // 重置人脸检测计数器
        stableFrames = 0
        updateCaptureButton(enabled = false, hint = "")
        // 更新指示器
        for (i in dots.indices) {
            dots[i].setBackgroundResource(
                if (i == currentStep) R.drawable.indicator_selected
                else R.drawable.indicator_unselected
            )
        }
    }

    private fun captureCurrentStep() {
        val capture = imageCapture ?: run {
            toast("相机未就绪")
            return
        }
        val step = captureSteps[currentStep]
        val file = File(cacheDir, "face_${step.key}_${System.currentTimeMillis()}.jpg")
        val output = ImageCapture.OutputFileOptions.Builder(file).build()

        capture.takePicture(
            output,
            ContextCompat.getMainExecutor(this),
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(result: ImageCapture.OutputFileResults) {
                    capturedFiles[currentStep] = file
                    // 标记该步骤完成：指示器显示已拍摄
                    dots[currentStep].setBackgroundResource(R.drawable.indicator_selected)
                    currentStep++
                    if (currentStep >= captureSteps.size) {
                        // 最后一张拍完，显示预览，等待用户确认上传
                        showPreview(file)
                    } else {
                        showCaptureStep()
                    }
                }
                override fun onError(exception: ImageCaptureException) {
                    toast("拍照失败：${exception.message}")
                }
            }
        )
    }

    private fun showPreview(file: File) {
        previewOverlay.visibility = View.VISIBLE
        ivPreview.setImageURI(android.net.Uri.fromFile(file))
        btnRetake.setOnClickListener {
            try { file.delete() } catch (_: Exception) {}
            previewOverlay.visibility = View.GONE
            currentStep = (currentStep - 1).coerceAtLeast(0)
            showCaptureStep()
        }
        btnConfirm.setOnClickListener {
            previewOverlay.visibility = View.GONE
            startAnalyzingAndUpload()
        }
    }

    // analysis / upload simplified flow
    private val analysisLabels = listOf(
        "面部图像清晰度校准",
        "面部区域分割（额头、T区、左右脸颊、眼周、下颌）",
        "肌肤水分含量检测",
        "皮肤油脂分泌（水油平衡分析）",
        "干纹、静态皱纹深度识别",
        "毛孔粗大程度分级测算",
        "黑色素、色斑、暗沉色素检测",
        "泛红敏感、红血丝区域识别"
    )

    private var analysisIndex = 0
    private var analysisHandler: Handler? = null
    private var uploadDone = false

    private fun startAnalyzingAndUpload() {
        analyzingOverlay.visibility = View.VISIBLE
        layoutAnalysisItems.removeAllViews()
        analysisLabels.forEach { label ->
            val t = TextView(this).apply {
                text = label
                setTextColor(0xFFFFFFFF.toInt())
                textSize = 14f
                alpha = 0.6f
                setPadding(0, 8, 0, 8)
            }
            layoutAnalysisItems.addView(t)
        }
        tvUploadProgressLabel.text = "图片上传 0%"
        viewUploadFill.layoutParams.width = 0
        viewUploadFill.requestLayout()

        analysisIndex = 0
        analysisHandler = Handler(Looper.getMainLooper())
        val runnable = object : Runnable {
            override fun run() {
                if (analysisIndex >= layoutAnalysisItems.childCount) {
                    if (uploadDone) finishAnalysisAndNavigate()
                    return
                }
                val v = layoutAnalysisItems.getChildAt(analysisIndex) as TextView
                v.alpha = 1f
                v.text = "${v.text}  ·  分析中…"
                analysisIndex++
                analysisHandler?.postDelayed(this, 1500)
            }
        }
        analysisHandler?.post(runnable)

        uploadAllPhotosForReport()
    }

    private fun finishAnalysisAndNavigate() {
        analyzingOverlay.visibility = View.GONE
        val intent = Intent(this, com.example.aisia.ui.report.SkinReportActivity::class.java)
        startActivity(intent)
    }

    private fun updateUploadProgress(percent: Int) {
        tvUploadProgressLabel.text = "图片上传 ${percent}%"
        val parentWidth = (viewUploadFill.parent as View).width
        val w = (parentWidth * (percent / 100.0)).toInt()
        viewUploadFill.layoutParams.width = w
        viewUploadFill.requestLayout()
    }

    private fun uploadAllPhotosForReport() {
        val front = capturedFiles[0] ?: return runOnUiThread { toast("正面照片缺失") }
        val left  = capturedFiles[1] ?: return runOnUiThread { toast("左侧照片缺失") }
        val right = capturedFiles[2] ?: return runOnUiThread { toast("右侧照片缺失") }

        showLoading(R.string.skin_test_uploading)
        UploadHelper.uploadThreeAngles(front, left, right, BuildConfig.BASE_URL) { url, err ->
            runOnUiThread {
                hideLoading()
                if (url != null) {
                    currentGlbUrl = url
                    uploadDone = true
                    updateUploadProgress(100)
                    if (analysisIndex >= layoutAnalysisItems.childCount) {
                        finishAnalysisAndNavigate()
                    }
                } else {
                    toast(getString(R.string.skin_test_upload_fail) + (err?.let { ": $it" } ?: ""))
                    analyzingOverlay.visibility = View.GONE
                    previewOverlay.visibility = View.VISIBLE
                }
            }
        }

        val h = Handler(Looper.getMainLooper())
        var p = 0
        val progRunnable = object : Runnable {
            override fun run() {
                if (p >= 95 || uploadDone) return
                p += 8
                updateUploadProgress(p)
                h.postDelayed(this, 500)
            }
        }
        h.post(progRunnable)
    }

    private fun uploadAllPhotos() {
        val front = capturedFiles[0] ?: return toast("正面照片缺失")
        val left  = capturedFiles[1] ?: return toast("左侧照片缺失")
        val right = capturedFiles[2] ?: return toast("右侧照片缺失")

        showLoading(R.string.skin_test_uploading)
        UploadHelper.uploadThreeAngles(front, left, right, BuildConfig.BASE_URL) { url, err ->
            runOnUiThread {
                hideLoading()
                if (url != null) {
                    currentGlbUrl = url
                    showModel3D(url)
                    toast(getString(R.string.skin_test_upload_ok))
                } else {
                    toast(getString(R.string.skin_test_upload_fail) + (err?.let { ": $it" } ?: ""))
                }
            }
        }
    }

    private fun showModel3D(url: String) {
        layoutCapture.visibility = View.GONE
        layoutModel3D.visibility = View.VISIBLE
        btnGoAnalysis.visibility = View.VISIBLE
        // 下载并加载 GLB（Filament 在子线程中下载 + 解码，UI 线程加载）
        glbView.loadGlbUrl(url)
    }

    private fun onEffectSelected(effect: Effect) {
        selectedEffectId = effect.id
        effectAdapter.setSelected(effect.id)
        val src = currentGlbUrl
        if (src == null) {
            toast(getString(R.string.skin_test_no_model))
            return
        }
        showLoading(R.string.skin_test_modifying)
        UploadHelper.modifyModel(src, effect.id, BuildConfig.BASE_URL) { newUrl, err ->
            runOnUiThread {
                hideLoading()
                if (newUrl != null) {
                    currentGlbUrl = newUrl
                    glbView.loadGlbUrl(newUrl)
                    toast(getString(R.string.skin_test_modify_ok))
                } else {
                    toast(getString(R.string.skin_test_modify_fail) + (err?.let { ": $it" } ?: ""))
                }
            }
        }
    }

    private fun showLoading(textRes: Int) {
        tvLoadingText.setText(textRes)
        layoutLoading.visibility = View.VISIBLE
    }

    private fun hideLoading() {
        layoutLoading.visibility = View.GONE
    }

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()

    override fun onDestroy() {
        super.onDestroy()
        cameraExecutor.shutdown()
        faceAnalyzer?.close()
        faceAnalyzer = null
    }

    override fun onPause() {
        super.onPause()
        // MediaPipe FaceLandmarker 会占用 GPU 内存（尤其是 GPU delegate），
        // 切到后台时主动释放，避免其他应用 GPU 压力
        faceAnalyzer?.close()
        faceAnalyzer = null
        // 置空 imageAnalysis 避免下次误用
        imageAnalysis = null
    }

    override fun onResume() {
        super.onResume()
        // 如果拍照阶段可见且权限已授需，重新启动相机
        if (layoutCapture.visibility == View.VISIBLE
            && ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED
            && faceAnalyzer == null
        ) {
            startCamera()
        }
    }

    /** XML onClick 回调：模型阶段返回按钮 */
    fun onBackClick(view: View) {
        finish()
    }

    // ──────────── 效果列表适配器 ────────────

    inner class EffectAdapter(
        private val items: List<Effect>,
        private val onClick: (Effect) -> Unit
    ) : RecyclerView.Adapter<EffectAdapter.VH>() {

        private var selectedId: String? = null

        fun setSelected(id: String) {
            selectedId = id
            notifyDataSetChanged()
        }

        override fun onCreateViewHolder(parent: android.view.ViewGroup, viewType: Int): VH {
            val v = layoutInflater.inflate(R.layout.item_skin_effect, parent, false)
            return VH(v)
        }

        override fun getItemCount() = items.size

        override fun onBindViewHolder(holder: VH, position: Int) {
            val item = items[position]
            holder.tvName.text = item.name
            holder.ivIcon.text = item.emoji
            holder.itemView.isSelected = (item.id == selectedId)
            holder.itemView.setOnClickListener { onClick(item) }
        }

        inner class VH(view: View) : RecyclerView.ViewHolder(view) {
            val ivIcon: TextView = view.findViewById(R.id.ivEffectIcon)
            val tvName: TextView = view.findViewById(R.id.tvEffectName)
        }
    }
}
