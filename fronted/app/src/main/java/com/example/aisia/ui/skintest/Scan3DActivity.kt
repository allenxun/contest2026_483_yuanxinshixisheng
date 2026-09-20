package com.example.aisia.ui.skintest

import android.annotation.SuppressLint
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.util.Log
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import com.example.aisia.BuildConfig
import com.example.aisia.R
import com.example.aisia.network.TokenManager
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/**
 * 3D 扫描页面 - 完全模仿小程序实现
 * 使用 WebView 加载本地 HTML（Three.js 渲染 + CSS 蒙层动画）
 * 网络请求通过 JS Bridge 走原生 OkHttp，避免 WebView file:// 协议 CORS 问题
 */
class Scan3DActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "Scan3DActivity"
        private const val LOCAL_ORIGIN = "https://appassets.androidplatform.net"
        private const val LOCAL_PAGE_URL = "$LOCAL_ORIGIN/assets/scan3d.html"
        private const val RESULT_RETRY_DELAY_MS = 2_000L
        private const val MAX_EMPTY_RESULT_RETRIES = 5
        const val EXTRA_OSS_KEY = "oss_key"
    }

    @Volatile private var viewClosed = false
    @Volatile private var modelFile: java.io.File? = null
    private val downloads = java.util.concurrent.ConcurrentHashMap.newKeySet<okhttp3.Call>()
    private val modelDownloadGeneration = AtomicInteger()
    @Volatile private var modelCall: okhttp3.Call? = null
    private fun trackedCall(client: OkHttpClient, request: Request): okhttp3.Call =
        client.newCall(request).also { if (viewClosed) it.cancel() else downloads.add(it) }
    private fun postUi(action: () -> Unit) {
        runOnUiThread { if (!viewClosed && !isFinishing && !isDestroyed) action() }
    }
    private lateinit var webView: WebView
    private var ossKey: String = ""
    @Volatile private var taskId: String = ""
    @Volatile private var pendingGlbUrl: String = ""
    private var threeDType: String = "img"
    private val mainHandler = Handler(Looper.getMainLooper())
    private val resultFetchGeneration = AtomicInteger(0)
    private var resultRetryRunnable: Runnable? = null
    private var generationErrorDialog: AlertDialog? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_scan_3d)

        ossKey = intent.getStringExtra(EXTRA_OSS_KEY) ?: ""
        threeDType = intent.getStringExtra("3dType") ?: "img"
        taskId = intent.getStringExtra("task_id") ?: ""
        Log.i(TAG, "打开 3D 页面, 3dType=$threeDType")

        webView = findViewById(R.id.webView)
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = true
            allowContentAccess = false
            mediaPlaybackRequiresUserGesture = false
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            blockNetworkLoads = true
            javaScriptCanOpenWindowsAutomatically = false
            setSupportMultipleWindows(false)
        }

        webView.addJavascriptInterface(AndroidBridge(), "AndroidBridge")

        webView.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(view: WebView?, request: WebResourceRequest?): android.webkit.WebResourceResponse? {
                val url = request?.url ?: return null
                if (url.scheme != "https" || url.host != "appassets.androidplatform.net") return null
                return try {
                    val path = url.path.orEmpty()
                    if (path == "/model/current.glb") {
                        val file = modelFile ?: return null
                        android.webkit.WebResourceResponse("model/gltf-binary", null, file.inputStream())
                    } else if (path.startsWith("/assets/") && !path.split('/').contains("..")) {
                        val name = path.removePrefix("/assets/")
                        val mime = when (name.substringAfterLast('.')) {
                            "html" -> "text/html"
                            "js" -> "application/javascript"
                            "css" -> "text/css"
                            "png" -> "image/png"
                            "jpg", "jpeg" -> "image/jpeg"
                            else -> "application/octet-stream"
                        }
                        android.webkit.WebResourceResponse(mime, "UTF-8", assets.open(name))
                    } else null
                } catch (_: Exception) { null }
            }
            @Suppress("DEPRECATION")
            override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean {
                return !isTrustedPage(url)
            }

            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                if (request?.isForMainFrame != true) return false
                return !isTrustedPage(request.url?.toString())
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                if (!isTrustedPage(url)) {
                    Log.w(TAG, "阻止非本地页面启动原生 3D 流程")
                    return
                }
                Log.i(TAG, "WebView 页面加载完成，启动 3D 生成流程")
                startGeneration()
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(consoleMessage: android.webkit.ConsoleMessage?): Boolean {
                if (BuildConfig.DEBUG) {
                    consoleMessage?.let {
                        Log.d(TAG, "[JS] ${it.message()} (${it.sourceId()}:${it.lineNumber()})")
                    }
                }
                return true
            }
        }

        webView.loadUrl(LOCAL_PAGE_URL)

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) {
                    webView.goBack()
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })
    }

    private fun isTrustedPage(url: String?): Boolean =
        url == LOCAL_PAGE_URL || url?.startsWith("$LOCAL_PAGE_URL#") == true

    private fun startGeneration() {
        cancelResultRetry()
        pendingGlbUrl = ""
        val js = "nativeStart(${JSONObject.quote(threeDType)}, ${JSONObject.quote(taskId)})"
        Log.i(TAG, "启动本地 3D 流程, 3dType=$threeDType")
        webView.evaluateJavascript(js, null)
    }

    private fun cancelResultRetry() {
        resultFetchGeneration.incrementAndGet()
        resultRetryRunnable?.let(mainHandler::removeCallbacks)
        resultRetryRunnable = null
    }

    private fun resultContainers(root: JSONObject): List<JSONObject> {
        val wrapperKeys = listOf("data", "result", "payload")
        val firstLevel = wrapperKeys.mapNotNull(root::optJSONObject)
        val secondLevel = firstLevel.flatMap { parent ->
            wrapperKeys.mapNotNull(parent::optJSONObject)
        }
        return listOf(root) + firstLevel + secondLevel
    }

    private fun extractGlbUrl(root: JSONObject): String? {
        val urlKeys = listOf("glb_url", "model_url", "url")
        val containers = resultContainers(root)
        for (key in urlKeys) {
            for (container in containers) {
                val rawValue = container.opt(key)
                if (rawValue == null || rawValue === JSONObject.NULL) continue

                val candidate = rawValue.toString().trim()
                if (candidate.isBlank() || candidate.equals("null", ignoreCase = true)) continue

                candidate.toHttpUrlOrNull()?.let { return it.toString() }
            }
        }
        return null
    }

    private fun extractResultError(root: JSONObject): String {
        val errorKeys = listOf("error_message", "error", "detail", "message", "code")
        for (container in resultContainers(root)) {
            for (key in errorKeys) {
                val rawValue = container.opt(key)
                if (rawValue == null || rawValue === JSONObject.NULL) continue
                val message = rawValue.toString().trim()
                if (message.isNotBlank() && !message.equals("null", ignoreCase = true)) {
                    return message
                }
            }
        }
        return ""
    }

    private fun isNoFaceError(message: String): Boolean {
        val normalized = message.lowercase(java.util.Locale.ROOT)
        return listOf(
            "no face",
            "no_face",
            "face_not_detected",
            "face not detected",
            "未检测到人脸",
            "没有检测到人脸",
            "未识别到人脸",
            "未发现人脸",
            "找不到人脸",
            "无人脸",
            "人脸检测失败"
        ).any(normalized::contains)
    }

    private fun createAuthClient(
        connectTimeout: Long = 15,
        readTimeout: Long = 30,
        writeTimeout: Long = 30
    ): OkHttpClient {
        return OkHttpClient.Builder()
            .connectTimeout(connectTimeout, TimeUnit.SECONDS)
            .readTimeout(readTimeout, TimeUnit.SECONDS)
            .writeTimeout(writeTimeout, TimeUnit.SECONDS)
            .addInterceptor { chain ->
                val original = chain.request()
                val builder = original.newBuilder()
                val token = TokenManager.getToken()
                if (!token.isNullOrEmpty()) {
                    builder.header("Authorization", "Bearer $token")
                }
                chain.proceed(builder.build())
            }
            .build()
    }

    /**
     * JS Bridge - 供 HTML/JS 调用原生方法
     */
    inner class AndroidBridge {

        @JavascriptInterface
        fun onBack() {
            postUi { finish() }
        }

        @JavascriptInterface
        fun onCancel() {
            postUi { finish() }
        }

        @JavascriptInterface
        fun onError(message: String) {
            postUi {
                if (generationErrorDialog?.isShowing == true || isFinishing || isDestroyed) {
                    return@postUi
                }
                val noFace = isNoFaceError(message)
                val builder = AlertDialog.Builder(this@Scan3DActivity)
                    .setTitle(if (noFace) "未检测到人脸" else "生成失败")
                    .setMessage(
                        if (noFace) {
                            "照片中未检测到人脸，请重新拍摄清晰、完整的正脸"
                        } else {
                            "$message，建议重新采集人脸图像后再试"
                        }
                    )
                    .setNegativeButton("返回") { _, _ -> finish() }
                    .setCancelable(false)

                if (noFace) {
                    builder.setPositiveButton("重新拍照") { _, _ ->
                        startActivity(
                            Intent(this@Scan3DActivity, SmartSkinTestActivity::class.java)
                                .putExtra("type", "3d")
                        )
                        finish()
                    }
                } else {
                    builder.setPositiveButton("重新生成") { _, _ -> webView.reload() }
                }

                generationErrorDialog = builder.create().also { dialog ->
                    dialog.setOnDismissListener { generationErrorDialog = null }
                    dialog.show()
                }
            }
        }

        // ==================== 网络请求（原生 OkHttp） ====================

        @JavascriptInterface
        fun createTask() {
            Thread {
                try {
                    val baseUrl = BuildConfig.BASE_URL.trimEnd('/')
                    val url = "$baseUrl/api/3d/tasks"
                    Log.i(TAG, "创建 3D 任务: POST $url")
                    val client = createAuthClient(connectTimeout = 30, readTimeout = 60)
                    val jsonBody = JSONObject().apply { put("oss_key", ossKey) }
                    val requestBody = jsonBody.toString().toRequestBody("application/json".toMediaType())
                    val request = Request.Builder().url(url).post(requestBody).build()
                    val response = trackedCall(client, request).execute()
                    val bodyStr = response.body?.string() ?: ""
                    Log.i(TAG, "创建任务响应: code=${response.code}")

                    if (response.isSuccessful) {
                        val json = JSONObject(bodyStr)
                        val tid = json.optString("task_id", "")
                        if (tid.isNotEmpty()) {
                            taskId = tid
                            postUi { webView.evaluateJavascript("javascript:onTaskCreated('$tid')", null) }
                        } else {
                            postUi { webView.evaluateJavascript("javascript:onTaskCreateError('未返回 task_id')", null) }
                        }
                    } else {
                        val backendError = runCatching {
                            extractResultError(JSONObject(bodyStr))
                        }.getOrDefault("")
                        val errorMessage = backendError.ifBlank { "HTTP ${response.code}" }
                        postUi {
                            webView.evaluateJavascript(
                                "javascript:onTaskCreateError(${JSONObject.quote(errorMessage)})",
                                null
                            )
                        }
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "创建任务异常", e)
                    postUi {
                        webView.evaluateJavascript(
                            "javascript:onTaskCreateError(${JSONObject.quote(e.message ?: "创建任务失败")})",
                            null
                        )
                    }
                }
            }.start()
        }

        @JavascriptInterface
        fun pollStatus() {
            Thread {
                try {
                    val activeTaskId = taskId
                    if (activeTaskId.isBlank()) throw IllegalStateException("task_id 为空")
                    val baseUrl = BuildConfig.BASE_URL.trimEnd('/')
                    val url = "$baseUrl/api/3d/tasks/$activeTaskId/status"
                    val client = createAuthClient()
                    val request = Request.Builder().url(url).get().build()
                    val response = trackedCall(client, request).execute()
                    val bodyStr = response.body?.string() ?: ""

                    if (response.isSuccessful) {
                        val json = JSONObject(bodyStr)
                        val status = json.optString("status", "")
                        val error = json.optString("error", "")
                        postUi {
                            webView.evaluateJavascript("javascript:onPollStatus('$status', '${error.replace("'", "\\'")}')", null)
                        }
                    } else {
                        postUi { webView.evaluateJavascript("javascript:onPollError('HTTP ${response.code}')", null) }
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "轮询状态异常", e)
                    postUi { webView.evaluateJavascript("javascript:onPollError('${e.message?.replace("'", "\\'")}')", null) }
                }
            }.start()
        }

        @JavascriptInterface
        fun fetchResult() {
            val generation = resultFetchGeneration.incrementAndGet()
            resultRetryRunnable?.let(mainHandler::removeCallbacks)
            resultRetryRunnable = null
            fetchResultAttempt(generation, emptyRetryCount = 0)
        }

        private fun fetchResultAttempt(generation: Int, emptyRetryCount: Int) {
            Thread {
                try {
                    if (generation != resultFetchGeneration.get() || isFinishing || isDestroyed) return@Thread
                    val activeTaskId = taskId
                    if (activeTaskId.isBlank()) throw IllegalStateException("task_id 为空")
                    val baseUrl = BuildConfig.BASE_URL.trimEnd('/')
                    val url = "$baseUrl/api/3d/tasks/$activeTaskId/result"
                    Log.i(TAG, "获取任务结果: attempt=${emptyRetryCount + 1}")
                    val client = createAuthClient()
                    val request = Request.Builder().url(url).get().build()
                    trackedCall(client, request).execute().use { response ->
                        val bodyStr = response.body?.string() ?: ""
                        Log.i(TAG, "任务结果响应: code=${response.code}")

                        if (response.isSuccessful) {
                            val trimmedBody = bodyStr.trim()
                            val json = if (trimmedBody.isEmpty() || trimmedBody.equals("null", ignoreCase = true)) {
                                JSONObject()
                            } else {
                                JSONObject(bodyStr)
                            }
                            val glbUrl = extractGlbUrl(json)

                            if (glbUrl != null) {
                                pendingGlbUrl = glbUrl
                                postUi {
                                    if (generation == resultFetchGeneration.get() && !isFinishing && !isDestroyed) {
                                        resultRetryRunnable = null
                                        webView.evaluateJavascript("javascript:onFetchResult()", null)
                                    }
                                }
                            } else if (emptyRetryCount < MAX_EMPTY_RESULT_RETRIES) {
                                scheduleResultRetry(generation, emptyRetryCount + 1)
                            } else {
                                val backendError = extractResultError(json)
                                val errMsg = backendError.ifBlank {
                                    "模型已生成，但模型文件地址暂不可用，请稍后重试"
                                }
                                notifyResultError(generation, errMsg)
                            }
                        } else {
                            notifyResultError(generation, "HTTP ${response.code}")
                        }
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "获取结果异常", e)
                    notifyResultError(generation, e.message ?: "获取模型结果失败")
                }
            }.start()
        }

        private fun scheduleResultRetry(generation: Int, nextRetryCount: Int) {
            mainHandler.post {
                if (generation != resultFetchGeneration.get() || isFinishing || isDestroyed) return@post

                Log.i(TAG, "模型地址未就绪，${RESULT_RETRY_DELAY_MS / 1000} 秒后重试 ($nextRetryCount/$MAX_EMPTY_RESULT_RETRIES)")
                val retry = Runnable {
                    resultRetryRunnable = null
                    if (generation == resultFetchGeneration.get() && !isFinishing && !isDestroyed) {
                        fetchResultAttempt(generation, nextRetryCount)
                    }
                }
                resultRetryRunnable = retry
                mainHandler.postDelayed(retry, RESULT_RETRY_DELAY_MS)
            }
        }

        private fun notifyResultError(generation: Int, message: String) {
            postUi {
                if (generation == resultFetchGeneration.get() && !isFinishing && !isDestroyed) {
                    resultRetryRunnable = null
                    webView.evaluateJavascript(
                        "javascript:onFetchResultError(${JSONObject.quote(message)})",
                        null
                    )
                }
            }
        }

        @JavascriptInterface
        fun downloadGLB() {
            val token = modelDownloadGeneration.incrementAndGet()
            modelCall?.cancel()
            Thread {
                var temp: java.io.File? = null
                try {
                    if (viewClosed) return@Thread
                    val url = pendingGlbUrl
                    if (url.isBlank()) error("模型地址为空")
                    val client = OkHttpClient.Builder().connectTimeout(30, TimeUnit.SECONDS)
                        .readTimeout(180, TimeUnit.SECONDS).build()
                    val call = trackedCall(client, Request.Builder().url(url).build())
                    modelCall = call
                    temp = java.io.File.createTempFile("skin_model_", ".glb", cacheDir)
                    call.execute().use { response ->
                        if (!response.isSuccessful) error("HTTP ${response.code}")
                        val body = response.body ?: error("模型内容为空")
                        body.byteStream().use { input ->
                            temp!!.outputStream().use { output ->
                                val buffer = ByteArray(64 * 1024)
                                var total = 0L
                                while (true) {
                                    if (viewClosed || token != modelDownloadGeneration.get()) throw java.io.IOException("下载已取消")
                                    val count = input.read(buffer)
                                    if (count < 0) break
                                    total += count
                                    if (total > 128L * 1024 * 1024) throw java.io.IOException("模型过大，请使用较小模型")
                                    output.write(buffer, 0, count)
                                }
                            }
                        }
                    }
                    val ready = temp!!
                    temp = null
                    runOnUiThread {
                        if (viewClosed || isFinishing || token != modelDownloadGeneration.get()) { ready.delete(); return@runOnUiThread }
                        modelFile?.delete()
                        modelFile = ready
                        webView.evaluateJavascript("onGLBReady('$LOCAL_ORIGIN/model/current.glb?v=$token')", null)
                    }
                } catch (e: Exception) {
                    if (token == modelDownloadGeneration.get()) postUi {
                        webView.evaluateJavascript("onGLBDownloadError(${JSONObject.quote(e.message ?: "下载失败")})", null)
                    }
                } finally { temp?.delete() }
            }.start()
        }
    }

    override fun onDestroy() {
        viewClosed = true
        modelDownloadGeneration.incrementAndGet()
        downloads.forEach { it.cancel() }
        downloads.clear()
        modelFile?.delete(); modelFile = null
        cancelResultRetry()
        generationErrorDialog?.dismiss()
        generationErrorDialog = null
        webView.removeJavascriptInterface("AndroidBridge")
        webView.stopLoading()
        webView.destroy()
        super.onDestroy()
    }
}
