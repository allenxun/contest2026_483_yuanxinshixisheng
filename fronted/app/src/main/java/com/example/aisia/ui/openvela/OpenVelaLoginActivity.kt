package com.example.aisia.ui.openvela

import android.os.Handler
import android.os.Looper
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

internal object OpenVelaLoginApi {
    class RateLimited(val seconds: Long) : IOException("操作频繁，请稍后重试")
    private val client = OkHttpClient.Builder().connectTimeout(15, TimeUnit.SECONDS)
        .callTimeout(25, TimeUnit.SECONDS).followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).build()
    private val main = Handler(Looper.getMainLooper())
    fun post(endpoint: String, body: JSONObject, callback: (Result<JSONObject>) -> Unit): Call {
        require(endpoint in setOf("sms-challenges", "sessions"))
        val call = client.newCall(Request.Builder()
            .url("http://10.3.3.170:18085/api/v1/auth/" + endpoint)
            .post(body.toString().toRequestBody("application/json; charset=utf-8".toMediaType())).build())
        fun deliver(result: Result<JSONObject>) { main.post { if (!call.isCanceled()) callback(result) } }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) = deliver(Result.failure(IOException("网络连接失败，请重试")))
            override fun onResponse(call: Call, response: Response) {
                deliver(runCatching { response.use {
                    if (it.code == 429) throw RateLimited(it.header("Retry-After")?.toLongOrNull()?.coerceIn(1,3600) ?: 60)
                    if (it.code == 401) throw IOException("验证码错误或已失效，请重新获取")
                    if (!it.isSuccessful) throw IOException("登录服务请求失败（" + it.code + "），请重试")
                    val source = it.body?.source() ?: throw IOException("登录服务返回为空")
                    source.request(65537)
                    if (source.buffer.size > 65536) throw IOException("登录响应过大")
                    JSONObject(source.readUtf8()).optJSONObject("data") ?: throw IOException("登录响应格式错误")
                } })
            }
        })
        return call
    }
}
class OpenVelaLoginActivity : OpenVelaPage() {
    private var call: Call? = null
    private var challenge: String? = null
    private var challengePhone: String? = null
    private var busy = false
    private var retryAt = 0L
    private lateinit var phone: android.widget.EditText
    private lateinit var code: android.widget.EditText
    private lateinit var hint: android.widget.TextView
    private lateinit var send: android.widget.Button
    private lateinit var submit: android.widget.Button
    private val timer = Handler(Looper.getMainLooper())
    private val tick = object : Runnable {
        override fun run() {
            if (isFinishing || isDestroyed) return
            val seconds = ((retryAt - android.os.SystemClock.elapsedRealtime() + 999) / 1000).coerceAtLeast(0)
            send.text = if (seconds > 0) seconds.toString() + " 秒后重新获取" else "获取验证码"
            send.isEnabled = !busy && seconds == 0L
            if (seconds > 0) timer.postDelayed(this, 1000)
        }
    }
    override fun onCreate(savedInstanceState: android.os.Bundle?) {
        super.onCreate(savedInstanceState)
        page("openVela 登录", false, true)
        label("使用手机号登录测肤报告服务", 20, true)
        phone = android.widget.EditText(this).apply {
            hint = "手机号"; inputType = android.text.InputType.TYPE_CLASS_PHONE
            isSaveEnabled = false
        }
        code = android.widget.EditText(this).apply {
            hint = "短信验证码"; inputType = android.text.InputType.TYPE_CLASS_NUMBER
            isSaveEnabled = false
            filters = arrayOf(android.text.InputFilter.LengthFilter(32))
        }
        content.addView(phone); content.addView(code)
        hint = label("请先获取验证码，再登录", 14)
        send = button("获取验证码") { requestCode() }
        submit = button("登录") { login() }
    }
    private fun normalizedPhone(): String {
        val raw = phone.text.toString().trim()
        return if (Regex("^1[3-9][0-9]{9}$").matches(raw)) "+86" + raw else raw
    }
    private fun setBusy(value: Boolean) {
        busy = value; phone.isEnabled = !value; code.isEnabled = !value; submit.isEnabled = !value
        timer.removeCallbacks(tick)
        tick.run()
    }
    private fun failed(error: Throwable) {
        if (error is OpenVelaLoginApi.RateLimited) {
            retryAt = android.os.SystemClock.elapsedRealtime() + error.seconds * 1000
            timer.removeCallbacks(tick); tick.run()
        }
        hint.text = error.message
    }
    private fun requestCode() {
        if (busy || android.os.SystemClock.elapsedRealtime() < retryAt) return
        val number = normalizedPhone()
        if (!Regex("^\\+[1-9][0-9]{6,14}$").matches(number)) { hint.text = "请输入正确的手机号"; return }
        challenge = null; challengePhone = null; code.text.clear()
        setBusy(true); hint.text = "正在获取验证码…"
        call = OpenVelaLoginApi.post("sms-challenges", JSONObject().put("phone", number).put("purpose","login")) { result ->
            setBusy(false)
            result.fold(onSuccess = {
                val id = OpenVelaData.text(it, "challengeId")
                if (id == null) { hint.text = "接口未返回验证码挑战，请重试"; return@fold }
                challenge = id; challengePhone = number
                retryAt = android.os.SystemClock.elapsedRealtime() + it.optLong("retryAfter",60).coerceIn(0,3600) * 1000
                hint.text = "验证码已发送，请输入验证码"; timer.removeCallbacks(tick); tick.run()
            }, onFailure = { failed(it) })
        }
    }
    private fun login() {
        if (busy) return
        val id = challenge
        if (id == null || challengePhone != normalizedPhone()) { hint.text = "请先为当前手机号获取验证码"; return }
        val value = code.text.toString().trim()
        if (value.isEmpty()) { hint.text = "请输入验证码"; return }
        setBusy(true); hint.text = "正在登录…"
        call = OpenVelaLoginApi.post("sessions", JSONObject().put("challengeId",id).put("code",value)
            .put("installationId",OpenVelaAuth.installationId()).put("installBindingMaterial",JSONObject())) { result ->
            setBusy(false); code.text.clear(); challenge = null
            result.fold(onSuccess = { data ->
                try {
                    OpenVelaAuth.saveSession(data)
                    startActivity(android.content.Intent(this,OpenVelaPeopleActivity::class.java)
                        .addFlags(android.content.Intent.FLAG_ACTIVITY_CLEAR_TOP))
                    finish()
                } catch (_: Exception) { hint.text = "会话响应无效，请重新获取验证码登录" }
            }, onFailure = { failed(it) })
        }
    }
    override fun onDestroy() { call?.cancel(); timer.removeCallbacksAndMessages(null); super.onDestroy() }
}
