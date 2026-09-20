package com.example.aisia.ui.openvela

import android.os.Handler
import android.os.Looper
import okhttp3.*
import okhttp3.HttpUrl.Companion.toHttpUrl
import java.io.IOException
import java.util.concurrent.TimeUnit
import org.json.JSONObject

/** Isolated origin; never clears or replaces the existing login session. */
object OpenVelaApi {
    class LoginRequired : IOException("请登录 openVela 测肤服务")
    private val base = "http://10.3.3.170:18085/".toHttpUrl()
    private val main = Handler(Looper.getMainLooper())
    private val client = OkHttpClient.Builder().connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS).callTimeout(25, TimeUnit.SECONDS)
        .followRedirects(false).followSslRedirects(false).build()
    fun media(raw: String?): String? {
        if (raw.isNullOrBlank()) return null
        val url = base.resolve(raw) ?: return null
        return url.takeIf { it.scheme == base.scheme && it.host == base.host && it.port == base.port }?.toString()
    }
    fun headers(): Headers = Headers.Builder().apply {
        OpenVelaAuth.getToken()?.takeIf { it.isNotBlank() }?.let { add("Authorization", "Bearer " + it) }
        add("Cache-Control", "no-store")
    }.build()
    fun image(raw: String?): String? {
        media(raw)?.let { return it }
        return raw?.let { runCatching { it.toHttpUrl() }.getOrNull() }
            ?.takeIf { it.scheme == "https" && it.username.isEmpty() && it.password.isEmpty() }?.toString()
    }
    fun get(path: String, query: Map<String, String> = emptyMap(), result: (Result<JSONObject>) -> Unit): Call? {
        val token = OpenVelaAuth.getToken()
        if (token.isNullOrBlank()) { result(Result.failure(LoginRequired())); return null }
        val url = base.newBuilder().encodedPath(path).apply { query.forEach { (k,v) -> addQueryParameter(k,v) } }.build()
        val call = client.newCall(Request.Builder().url(url).headers(headers()).get().build())
        fun deliver(value: Result<JSONObject>) { main.post {
            if (!call.isCanceled() && OpenVelaAuth.getToken() == null) {
                result(Result.failure(LoginRequired()))
            } else if (!call.isCanceled() && OpenVelaAuth.getToken() == token) {
                if (value.exceptionOrNull() is LoginRequired) OpenVelaAuth.clearIfCurrent(token)
                result(value)
            }
        } }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) = deliver(Result.failure(IOException("网络连接失败，请重试")))
            override fun onResponse(call: Call, response: Response) {
                val value = runCatching {
                    response.use {
                        if (it.code == 401) throw LoginRequired()
                        if (it.code == 403) throw IOException("当前账号没有查看权限")
                        if (it.code == 404) throw IOException("暂无访问权限或资料不存在")
                        if (!it.isSuccessful) throw IOException("请求失败（" + it.code + "），请稍后重试")
                        val body = it.body ?: throw IOException("接口返回为空")
                        val bytes = body.byteStream().use { stream ->
                            val buffer = java.io.ByteArrayOutputStream()
                            val chunk = ByteArray(8192)
                            while (true) { val n = stream.read(chunk); if (n < 0) break
                                if (buffer.size() + n > 2 * 1024 * 1024) throw IOException("接口数据过大")
                                buffer.write(chunk, 0, n)
                            }; buffer.toByteArray()
                        }
                        JSONObject(bytes.toString(Charsets.UTF_8)).optJSONObject("data") ?: throw IOException("接口数据格式不正确")
                    }
                }
                deliver(value)
            }
        })
        return call
    }
}
