package com.example.aisia.network

import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.example.aisia.AisiaApp
import com.example.aisia.BuildConfig
import com.example.aisia.ui.login.LoginActivity
import okhttp3.Call
import okhttp3.Callback
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONObject
import java.io.IOException
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * 网络请求工具类
 * - 支持 GET / POST / PUT
 * - 非白名单接口自动注入 Authorization: Bearer ${token}
 * - 受保护接口返回 401：清除 token 并跳转登录页（全局统一处理，2 秒内去重）
 * - 登录白名单接口返回 401：仅回调本次登录失败，不触发页面跳转
 */
object HttpHelper {

    private const val TAG = "HttpHelper"
    private const val REQUEST_ID_HEADER = "X-Aisia-Request-Id"

    /**
     * 接口白名单：在名单中的路径不会附带 Authorization 请求头
     */
    private val WHITE_LIST = setOf(
        "/api/auth/app/sms/send",
        "/api/auth/app/sms/login",
        "/api/auth/app/login"
    )

    /**
     * 同一认证请求在进程内只保留一个真实网络调用。
     * 页面重建后再次提交相同内容时，会接管原请求的回调并复用同一个 requestId。
     */
    private data class AuthRequestCallback(
        val onSuccess: (String) -> Unit,
        val onFailure: (Int, String) -> Unit
    )

    private data class InFlightAuthRequest(
        val requestId: String,
        var callback: AuthRequestCallback
    )

    private val authRequestLock = Any()
    private val inFlightAuthRequests = mutableMapOf<String, InFlightAuthRequest>()

    /**
     * 判断路径是否在白名单内
     */
    private fun isInWhiteList(path: String): Boolean {
        // 只取 path 部分比较（去除可能的 query string）
        val pure = path.substringBefore('?')
        return WHITE_LIST.any { pure.endsWith(it) }
    }

    /**
     * 认证拦截器：非白名单接口自动加上 Bearer Token
     */
    private val authInterceptor = Interceptor { chain ->
        val original = chain.request()
        val path = original.url.encodedPath
        val builder = original.newBuilder()
        if (!isInWhiteList(path)) {
            val token = TokenManager.getToken()
            if (!token.isNullOrEmpty()) {
                builder.header("Authorization", "Bearer $token")
            }
        }
        chain.proceed(builder.build())
    }

    /**
     * 缓存大小：10MB
     */
    private const val CACHE_SIZE = 10L * 1024 * 1024
    
    /**
     * 缓存目录名
     */
    private const val CACHE_DIR = "http_cache"

    private val client: OkHttpClient by lazy {
        // 配置缓存（用于 GET 请求）
        val cacheDir = java.io.File(AisiaApp.instance.cacheDir, CACHE_DIR)
        val cache = okhttp3.Cache(cacheDir, CACHE_SIZE)
        
        OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .writeTimeout(15, TimeUnit.SECONDS)
            .cache(cache)
            .addInterceptor(authInterceptor)
            .build()
    }

    private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()

    /** 401 触发去重时间戳，避免并发请求重复跳转登录页 */
    @Volatile
    private var lastUnauthorizedTime = 0L
    private const val UNAUTHORIZED_DEBOUNCE_MS = 2000L

    /**
     * 发送 POST 请求（异步）
     * @param timeoutSeconds 超时时间（秒），为 null 时使用默认超时
     */
    fun post(
        path: String,
        params: Map<String, String>,
        onSuccess: (responseBody: String) -> Unit,
        onFailure: (code: Int, errorMsg: String) -> Unit,
        timeoutSeconds: Long? = null
    ) {
        val url = ApiConfig.BASE_URL.trimEnd('/') + path
        val jsonBody = JSONObject(params).toString()

        if (isInWhiteList(path)) {
            postDeduplicatedAuthRequest(
                path = path,
                url = url,
                params = params,
                jsonBody = jsonBody,
                onSuccess = onSuccess,
                onFailure = onFailure,
                timeoutSeconds = timeoutSeconds
            )
            return
        }

        logRequest("POST", path, jsonBody.length)
        val request = Request.Builder()
            .url(url)
            .post(jsonBody.toRequestBody(JSON_MEDIA_TYPE))
            .build()
        executeRequest(request, onSuccess, onFailure, timeoutSeconds)
    }

    private fun postDeduplicatedAuthRequest(
        path: String,
        url: String,
        params: Map<String, String>,
        jsonBody: String,
        onSuccess: (String) -> Unit,
        onFailure: (Int, String) -> Unit,
        timeoutSeconds: Long?
    ) {
        val requestKey = buildAuthRequestKey(path, params)
        val callback = AuthRequestCallback(onSuccess, onFailure)
        val requestId: String

        synchronized(authRequestLock) {
            val existing = inFlightAuthRequests[requestKey]
            if (existing != null) {
                // 新页面接管结果，避免已销毁的登录页和新页面各处理一次回调。
                existing.callback = callback
                Log.i(
                    TAG,
                    "AUTH DEDUP POST ${path.substringBefore('?')}, requestId=${existing.requestId}"
                )
                return
            }

            requestId = UUID.randomUUID().toString()
            inFlightAuthRequests[requestKey] = InFlightAuthRequest(requestId, callback)
        }

        Log.i(
            TAG,
            "AUTH ==> POST ${path.substringBefore('?')}, requestId=$requestId, bodyLength=${jsonBody.length}"
        )
        val request = Request.Builder()
            .url(url)
            .header(REQUEST_ID_HEADER, requestId)
            .post(jsonBody.toRequestBody(JSON_MEDIA_TYPE))
            .build()

        try {
            executeRequest(
                request = request,
                onSuccess = { body -> completeAuthRequest(requestKey, body = body) },
                onFailure = { code, message ->
                    completeAuthRequest(requestKey, code = code, errorMessage = message)
                },
                timeoutSeconds = timeoutSeconds
            )
        } catch (e: Exception) {
            completeAuthRequest(
                requestKey,
                code = -1,
                errorMessage = e.message ?: "认证请求创建失败"
            )
        }
    }

    /** 路径和排序后的参数只做内存哈希，不记录手机号、验证码或密码明文。 */
    private fun buildAuthRequestKey(path: String, params: Map<String, String>): String {
        val canonical = buildString {
            append(path.substringBefore('?'))
            params.toSortedMap().forEach { (key, value) ->
                append('|').append(key.length).append(':').append(key)
                append('=').append(value.length).append(':').append(value)
            }
        }
        return MessageDigest.getInstance("SHA-256")
            .digest(canonical.toByteArray(Charsets.UTF_8))
            .joinToString("") { byte -> "%02x".format(byte) }
    }

    private fun completeAuthRequest(
        requestKey: String,
        body: String? = null,
        code: Int? = null,
        errorMessage: String? = null
    ) {
        val callback = synchronized(authRequestLock) {
            inFlightAuthRequests.remove(requestKey)?.callback
        } ?: return

        try {
            if (code == null) {
                callback.onSuccess(body.orEmpty())
            } else {
                callback.onFailure(code, errorMessage.orEmpty())
            }
        } catch (e: Exception) {
            Log.e(TAG, "认证请求回调执行失败", e)
        }
    }

    /**
     * 发送无请求体的 POST 请求（异步）。
     * 适用于 OpenAPI 明确声明无 requestBody 的登出、注销等接口。
     */
    fun postEmpty(
        path: String,
        onSuccess: (responseBody: String) -> Unit,
        onFailure: (code: Int, errorMsg: String) -> Unit,
        timeoutSeconds: Long? = null
    ) {
        val url = ApiConfig.BASE_URL.trimEnd('/') + path
        logRequest("POST", path, 0)
        val request = Request.Builder()
            .url(url)
            .post(ByteArray(0).toRequestBody(null))
            .build()
        executeRequest(request, onSuccess, onFailure, timeoutSeconds)
    }

    /**
     * 发送 POST 请求（异步）- 直接传 JSON 字符串
     * 用于需要发送数组等复杂结构的场景
     * @param timeoutSeconds 超时时间（秒），为 null 时使用默认超时
     */
    fun postJson(
        path: String,
        jsonBody: String,
        onSuccess: (responseBody: String) -> Unit,
        onFailure: (code: Int, errorMsg: String) -> Unit,
        timeoutSeconds: Long? = null
    ) {
        val url = ApiConfig.BASE_URL.trimEnd('/') + path
        logRequest("POST", path, jsonBody.length)
        val request = Request.Builder()
            .url(url)
            .post(jsonBody.toRequestBody(JSON_MEDIA_TYPE))
            .build()
        executeRequest(request, onSuccess, onFailure, timeoutSeconds)
    }

    /**
     * 发送 SSE 流式 POST 请求。
     *
     * [idleTimeoutSeconds] 是相邻网络数据之间的空闲超时，不是整次请求的总超时。
     * OkHttp 每次成功读取到数据后都会重新计算 read timeout，因此长时间持续输出不会误超时。
     * 回调运行在 OkHttp 工作线程；调用方如需更新 UI，应切换到主线程。
     */
    fun postSse(
        path: String,
        jsonBody: String,
        idleTimeoutSeconds: Long = 30,
        onEvent: (data: String) -> Unit,
        onClosed: () -> Unit,
        onFailure: (code: Int, errorMsg: String) -> Unit
    ): Call {
        require(idleTimeoutSeconds > 0) { "idleTimeoutSeconds must be positive" }

        val url = ApiConfig.BASE_URL.trimEnd('/') + path
        logRequest("POST-SSE", path, jsonBody.length)
        val request = Request.Builder()
            .url(url)
            .header("Accept", "text/event-stream")
            .header("Cache-Control", "no-cache")
            .post(jsonBody.toRequestBody(JSON_MEDIA_TYPE))
            .build()

        val streamClient = client.newBuilder()
            .callTimeout(0, TimeUnit.MILLISECONDS)
            .readTimeout(idleTimeoutSeconds, TimeUnit.SECONDS)
            .build()
        val call = streamClient.newCall(request)

        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                val message = if (e is java.net.SocketTimeoutException) {
                    "回复等待超时，请重试"
                } else {
                    e.message ?: "流式请求失败"
                }
                Log.e(TAG, "<== SSE FAIL ${request.url.encodedPath}: ${e.javaClass.simpleName}")
                onFailure(-1, message)
            }

            override fun onResponse(call: Call, response: Response) {
                response.use { result ->
                    if (result.code == 401) {
                        handleUnauthorized()
                        onFailure(401, "登录已失效")
                        return
                    }

                    if (!result.isSuccessful) {
                        val errorBody = result.body?.string().orEmpty()
                        onFailure(result.code, errorBody.ifBlank { "请求失败: ${result.code}" })
                        return
                    }

                    val source = result.body?.source()
                    if (source == null) {
                        onFailure(-1, "服务未返回流式内容")
                        return
                    }

                    try {
                        val dataLines = mutableListOf<String>()

                        fun dispatchEvent() {
                            if (dataLines.isEmpty()) return
                            val data = dataLines.joinToString("\n")
                            dataLines.clear()
                            onEvent(data)
                        }

                        while (true) {
                            val line = source.readUtf8Line() ?: break
                            when {
                                line.isEmpty() -> dispatchEvent()
                                line.startsWith("data:") -> {
                                    dataLines += line.removePrefix("data:").trimStart()
                                }
                                // event/id/retry 字段和以冒号开头的 SSE 心跳注释无需传给业务层。
                            }
                        }

                        dispatchEvent()
                        onClosed()
                    } catch (e: IOException) {
                        val message = if (e is java.net.SocketTimeoutException) {
                            "回复等待超时，请重试"
                        } else {
                            e.message ?: "流式连接中断"
                        }
                        onFailure(-1, message)
                    } catch (e: Exception) {
                        onFailure(-1, e.message ?: "流式数据解析失败")
                    }
                }
            }
        })

        return call
    }

    /**
     * 发送 GET 请求（异步）
     * @param timeoutSeconds 超时时间（秒），为 null 时使用默认超时
     */
    fun get(
        path: String,
        onSuccess: (responseBody: String) -> Unit,
        onFailure: (code: Int, errorMsg: String) -> Unit,
        timeoutSeconds: Long? = null
    ) {
        val url = ApiConfig.BASE_URL.trimEnd('/') + path
        logRequest("GET", path)
        val request = Request.Builder()
            .url(url)
            .get()
            .build()
        executeRequest(request, onSuccess, onFailure, timeoutSeconds)
    }

    /**
     * 发送 PUT 请求（异步）
     * @param timeoutSeconds 超时时间（秒），为 null 时使用默认超时
     */
    fun put(
        path: String,
        params: Map<String, String>,
        onSuccess: (responseBody: String) -> Unit,
        onFailure: (code: Int, errorMsg: String) -> Unit,
        timeoutSeconds: Long? = null
    ) {
        val url = ApiConfig.BASE_URL.trimEnd('/') + path
        val jsonBody = JSONObject(params).toString()
        logRequest("PUT", path, jsonBody.length)
        val request = Request.Builder()
            .url(url)
            .put(jsonBody.toRequestBody(JSON_MEDIA_TYPE))
            .build()
        executeRequest(request, onSuccess, onFailure, timeoutSeconds)
    }

    /**
     * 统一执行请求并处理响应/异常
     * 受保护接口的 HTTP 401 会触发全局登录态失效处理
     * @param timeoutSeconds 超时时间（秒），为 null 时使用默认超时
     */
    private fun executeRequest(
        request: Request,
        onSuccess: (responseBody: String) -> Unit,
        onFailure: (code: Int, errorMsg: String) -> Unit,
        timeoutSeconds: Long? = null
    ) {
        val requestId = request.header(REQUEST_ID_HEADER)
        val call = if (timeoutSeconds != null) {
            // 创建带有自定义超时的 client 副本
            val customClient = client.newBuilder()
                .connectTimeout(timeoutSeconds, TimeUnit.SECONDS)
                .readTimeout(timeoutSeconds, TimeUnit.SECONDS)
                .writeTimeout(timeoutSeconds, TimeUnit.SECONDS)
                .build()
            customClient.newCall(request)
        } else {
            client.newCall(request)
        }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                val idSuffix = requestId?.let { ", requestId=$it" }.orEmpty()
                Log.e(
                    TAG,
                    "<== FAIL ${request.method} ${request.url.encodedPath}: ${e.javaClass.simpleName}$idSuffix"
                )
                onFailure(-1, e.message ?: "网络请求失败")
            }

            override fun onResponse(call: Call, response: Response) {
                val body = try {
                    response.body?.string() ?: ""
                } catch (e: IOException) {
                    response.close()
                    onFailure(-1, e.message ?: "响应读取失败，请重试")
                    return
                }
                response.close()
                if (requestId != null) {
                    // 认证链路始终记录请求号，正式包也可与后端日志一一核对；不记录请求内容。
                    Log.i(
                        TAG,
                        "AUTH <== ${response.code} ${request.method} ${request.url.encodedPath}, " +
                            "requestId=$requestId, bodyLength=${body.length}"
                    )
                } else if (BuildConfig.DEBUG) {
                    Log.d(
                        TAG,
                        "<== ${response.code} ${request.method} ${request.url.encodedPath}, bodyLength=${body.length}"
                    )
                }

                if (response.code == 401) {
                    if (isInWhiteList(request.url.encodedPath)) {
                        // 登录类接口的 401 是本次登录失败，不应触发全局登录态失效跳转。
                        onFailure(401, body.ifEmpty { "登录失败" })
                    } else {
                        // 全局处理：清 token + 跳登录页
                        handleUnauthorized()
                        onFailure(401, "登录已失效")
                    }
                    return
                }

                if (response.isSuccessful) {
                    onSuccess(body)
                } else {
                    onFailure(response.code, body.ifEmpty { "请求失败: ${response.code}" })
                }
            }
        })
    }

    private fun logRequest(method: String, path: String, bodyLength: Int? = null) {
        if (!BuildConfig.DEBUG) return
        val safePath = path.substringBefore('?')
        val sizeSuffix = bodyLength?.let { ", bodyLength=$it" }.orEmpty()
        Log.d(TAG, "==> $method $safePath$sizeSuffix")
    }

    /**
     * 全局处理 401：清除 token 并跳转登录页
     * 通过时间戳去重，避免并发请求触发多次跳转
     */
    private fun handleUnauthorized() {
        val now = System.currentTimeMillis()
        if (now - lastUnauthorizedTime < UNAUTHORIZED_DEBOUNCE_MS) return
        lastUnauthorizedTime = now

        TokenManager.clearToken()

        Handler(Looper.getMainLooper()).post {
            val app = AisiaApp.instance
            val intent = Intent(app, LoginActivity::class.java).apply {
                // 从 Application Context 启动必须 NEW_TASK；CLEAR_TASK 清空已有任务栈
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            }
            app.startActivity(intent)
        }
    }
}
