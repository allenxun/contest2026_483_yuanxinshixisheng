package com.example.aisia.ui.login

import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.os.CountDownTimer
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.text.InputFilter
import android.text.InputType
import android.text.SpannableString
import android.text.Spanned
import android.text.TextPaint
import android.text.method.LinkMovementMethod
import android.text.style.ClickableSpan
import android.text.style.ForegroundColorSpan
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.example.aisia.MainActivity
import com.example.aisia.R
import com.example.aisia.network.HttpHelper
import com.example.aisia.network.TokenManager
import com.example.aisia.privacy.PrivacyManager
import org.json.JSONObject

class LoginActivity : AppCompatActivity() {

    companion object {
        private const val LOGIN_SUBMIT_COOLDOWN_MS = 2000L
        private val loginSubmitLock = Any()
        private var lastLoginSubmitElapsedTime = 0L
    }

    private lateinit var etPhone: EditText
    private lateinit var etCode: EditText
    private lateinit var btnGetCode: Button
    private lateinit var btnLogin: Button
    private lateinit var layoutLoginMethodSwitch: View
    private lateinit var tvSmsLogin: TextView
    private lateinit var tvPasswordLogin: TextView
    private lateinit var tvCredentialLabel: TextView
    private lateinit var tvGoRegister: TextView
    private lateinit var tvBackToLogin: TextView
    private lateinit var btnRegister: Button
    private lateinit var layoutPrivacy: View
    private lateinit var flCheckbox: View
    private lateinit var vCheckboxBg: View
    private lateinit var ivCheckmark: ImageView
    private lateinit var tvPrivacyText: TextView
    private var isPrivacyChecked = false

    private enum class AuthMode {
        SMS_LOGIN,
        PASSWORD_LOGIN,
        SMS_REGISTER
    }

    private var authMode = AuthMode.SMS_LOGIN

    private var countDownTimer: CountDownTimer? = null

    // 登录按钮背景色
    private val accentColor = 0xFFAF8D59.toInt()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_login)

        etPhone = findViewById(R.id.etPhone)
        etCode = findViewById(R.id.etCode)
        btnGetCode = findViewById(R.id.btnGetCode)
        btnLogin = findViewById(R.id.btnLogin)
        layoutLoginMethodSwitch = findViewById(R.id.layoutLoginMethodSwitch)
        tvSmsLogin = findViewById(R.id.tvSmsLogin)
        tvPasswordLogin = findViewById(R.id.tvPasswordLogin)
        tvCredentialLabel = findViewById(R.id.tvCredentialLabel)
        tvGoRegister = findViewById(R.id.tvGoRegister)
        tvBackToLogin = findViewById(R.id.tvBackToLogin)
        btnRegister = findViewById(R.id.btnRegister)
        layoutPrivacy = findViewById(R.id.layoutPrivacy)
        flCheckbox = findViewById(R.id.flCheckbox)
        vCheckboxBg = findViewById(R.id.vCheckboxBg)
        ivCheckmark = findViewById(R.id.ivCheckmark)
        tvPrivacyText = findViewById(R.id.tvPrivacyText)

        // 设置隐私协议复选框文字（含可点击链接）
        setupPrivacyCheckbox()

        // 返回按钮 - 返回 MainActivity（我的页面）
        findViewById<View>(R.id.btnBack).setOnClickListener {
            val intent = Intent(this, MainActivity::class.java)
            intent.putExtra(MainActivity.EXTRA_TAB, "mine")
            intent.flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
            startActivity(intent)
            finish()
        }

        // 获取验证码
        btnGetCode.setOnClickListener {
            val phone = etPhone.text.toString().trim()

            if (phone.isEmpty()) {
                Toast.makeText(this, "请输入手机号", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            if (!phone.matches(Regex("^1[3-9]\\d{9}$"))) {
                Toast.makeText(this, "请输入正确的手机号", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            btnGetCode.isEnabled = false

            HttpHelper.post(
                path = "/api/auth/app/sms/send",
                params = mapOf("phone" to phone),
                onSuccess = { _ ->
                    runOnUiThread {
                        Toast.makeText(this, "验证码已发送", Toast.LENGTH_SHORT).show()
                        startCountDown()
                    }
                },
                onFailure = { _, _ ->
                    runOnUiThread {
                        Toast.makeText(this, "验证码发送失败，请稍候再试！", Toast.LENGTH_SHORT).show()
                        btnGetCode.isEnabled = true
                    }
                }
            )
        }

        tvSmsLogin.setOnClickListener {
            renderAuthMode(AuthMode.SMS_LOGIN)
        }

        tvPasswordLogin.setOnClickListener {
            renderAuthMode(AuthMode.PASSWORD_LOGIN)
        }

        // 登录按钮：根据当前选择执行短信验证码登录或手机号密码登录
        btnLogin.setOnClickListener {
            val phone = etPhone.text.toString().trim()
            val credential = etCode.text.toString()

            if (!phone.matches(Regex("^1[3-9]\\d{9}$"))) {
                Toast.makeText(this, "请输入正确的手机号", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            if (!isPrivacyChecked) {
                Toast.makeText(this, "请先阅读并同意用户隐私协议和用户授权协议", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            when (authMode) {
                AuthMode.SMS_LOGIN -> {
                    val code = credential.trim()
                    if (code.isEmpty()) {
                        Toast.makeText(this, "请输入验证码", Toast.LENGTH_SHORT).show()
                        return@setOnClickListener
                    }
                    if (!tryAcquireLoginSubmit()) return@setOnClickListener
                    doSmsLogin(phone, code)
                }

                AuthMode.PASSWORD_LOGIN -> {
                    if (credential.length !in 6..32) {
                        Toast.makeText(this, "请输入6-32位密码", Toast.LENGTH_SHORT).show()
                        return@setOnClickListener
                    }
                    if (!tryAcquireLoginSubmit()) return@setOnClickListener
                    doPasswordLogin(phone, credential)
                }

                AuthMode.SMS_REGISTER -> Unit
            }
        }

        // "还没申请账号？去注册" 点击切换为注册模式
        tvGoRegister.setOnClickListener {
            renderAuthMode(AuthMode.SMS_REGISTER)
        }

        // "返回登录" 点击切换回登录模式
        tvBackToLogin.setOnClickListener {
            renderAuthMode(AuthMode.SMS_LOGIN)
        }

        // 自定义复选框点击切换
        flCheckbox.setOnClickListener {
            isPrivacyChecked = !isPrivacyChecked
            if (isPrivacyChecked) {
                vCheckboxBg.setBackgroundColor(accentColor)
                ivCheckmark.visibility = View.VISIBLE
            } else {
                vCheckboxBg.setBackgroundResource(R.drawable.cb_unchecked_bg)
                ivCheckmark.visibility = View.GONE
            }
        }

        // 注册按钮
        btnRegister.setOnClickListener {
            val phone = etPhone.text.toString().trim()
            val code = etCode.text.toString().trim()

            if (!phone.matches(Regex("^1[3-9]\\d{9}$"))) {
                Toast.makeText(this, "请输入正确的手机号", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            if (code.isEmpty()) {
                Toast.makeText(this, "请输入验证码", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            if (!isPrivacyChecked) {
                Toast.makeText(this, "请先阅读并同意用户隐私协议和用户授权协议", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            if (!tryAcquireLoginSubmit()) return@setOnClickListener

            // 用户已勾选同意隐私协议，同步记录合规同意状态
            PrivacyManager.markAgreed(this)
            doRegister(phone, code)
        }

        renderAuthMode(AuthMode.SMS_LOGIN, clearCredential = false)
    }

    /**
     * 进程级登录提交冷却。使用单调时钟，Activity 重建或系统时间变化都不会绕过冷却。
     */
    private fun tryAcquireLoginSubmit(): Boolean {
        val now = SystemClock.elapsedRealtime()
        val acquired = synchronized(loginSubmitLock) {
            if (now - lastLoginSubmitElapsedTime < LOGIN_SUBMIT_COOLDOWN_MS) {
                false
            } else {
                lastLoginSubmitElapsedTime = now
                true
            }
        }
        if (!acquired) {
            Toast.makeText(this, "请勿重复提交，请稍后再试", Toast.LENGTH_SHORT).show()
        }
        return acquired
    }

    private fun renderAuthMode(mode: AuthMode, clearCredential: Boolean = true) {
        if (authMode != mode && clearCredential) {
            etCode.text.clear()
        }
        authMode = mode

        val isPasswordLogin = mode == AuthMode.PASSWORD_LOGIN
        val isRegister = mode == AuthMode.SMS_REGISTER

        layoutLoginMethodSwitch.visibility = if (isRegister) View.GONE else View.VISIBLE
        btnLogin.visibility = if (isRegister) View.GONE else View.VISIBLE
        btnRegister.visibility = if (isRegister) View.VISIBLE else View.GONE
        tvGoRegister.visibility = if (isRegister) View.GONE else View.VISIBLE
        tvBackToLogin.visibility = if (isRegister) View.VISIBLE else View.GONE

        tvCredentialLabel.setText(if (isPasswordLogin) R.string.password_label else R.string.code_label)
        etCode.setHint(if (isPasswordLogin) R.string.password_hint else R.string.code_hint)
        etCode.inputType = if (isPasswordLogin) {
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        } else {
            InputType.TYPE_CLASS_NUMBER
        }
        etCode.filters = arrayOf(InputFilter.LengthFilter(if (isPasswordLogin) 32 else 6))
        btnGetCode.visibility = if (isPasswordLogin) View.GONE else View.VISIBLE

        updateLoginMethodTab(tvSmsLogin, mode == AuthMode.SMS_LOGIN)
        updateLoginMethodTab(tvPasswordLogin, isPasswordLogin)
    }

    private fun updateLoginMethodTab(tab: TextView, selected: Boolean) {
        tab.setBackgroundResource(
            if (selected) R.drawable.bg_login_method_selected else android.R.color.transparent
        )
        tab.setTextColor(if (selected) Color.WHITE else 0xFF666666.toInt())
        tab.setTypeface(null, if (selected) Typeface.BOLD else Typeface.NORMAL)
    }

    /**
     * 设置登录页协议文字；内容与前端登录页保持一致。
     * CheckBox 和 TextView 独立，点击协议链接不会误切换勾选状态。
     */
    private fun setupPrivacyCheckbox() {
        val fullText = "我已阅读并同意《用户隐私协议》和《用户授权协议》"
        val spannable = SpannableString(fullText)
        val links = listOf(
            ("《用户隐私协议》" to { showPrivacyDialog() }),
            ("《用户授权协议》" to { showUserAgreementDialog() })
        )

        links.forEach { (label, action) ->
            val start = fullText.indexOf(label)
            val end = start + label.length
            spannable.setSpan(
                ForegroundColorSpan(accentColor),
                start,
                end,
                Spanned.SPAN_EXCLUSIVE_EXCLUSIVE
            )
            spannable.setSpan(
                object : ClickableSpan() {
                    override fun onClick(widget: View) {
                        action()
                    }

                    override fun updateDrawState(ds: TextPaint) {
                        super.updateDrawState(ds)
                        ds.color = accentColor
                        ds.isUnderlineText = false
                    }
                },
                start,
                end,
                Spanned.SPAN_EXCLUSIVE_EXCLUSIVE
            )
        }

        tvPrivacyText.text = spannable
        tvPrivacyText.movementMethod = LinkMovementMethod.getInstance()
        tvPrivacyText.highlightColor = Color.TRANSPARENT
    }

    private fun showPrivacyDialog() {
        PrivacyManager.showPrivacyPolicyDialog(this)
    }

    private fun showUserAgreementDialog() {
        PrivacyManager.showUserAgreementDialog(this)
    }

    private fun dp2px(dp: Float): Int {
        return (dp * resources.displayMetrics.density + 0.5f).toInt()
    }

    /**
     * 调用注册接口（实际调用登录接口，附带 source=android 和 privacy_agreed=true）
     */
    private fun doRegister(phone: String, code: String) {
        btnRegister.isEnabled = false
        HttpHelper.post(
            path = "/api/auth/app/sms/login",
            params = mapOf(
                "phone" to phone,
                "code" to code,
                "source" to "android",
                "privacy_agreed" to "true"
            ),
            onSuccess = { resp ->
                val token = parseAccessToken(resp)
                runOnUiThread {
                    if (!token.isNullOrEmpty()) {
                        TokenManager.saveToken(token)
                        Toast.makeText(this, "注册成功", Toast.LENGTH_SHORT).show()
                        Handler(Looper.getMainLooper()).postDelayed({
                            val intent = Intent(this, MainActivity::class.java)
                            intent.putExtra(MainActivity.EXTRA_TAB, "home")
                            intent.flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
                            startActivity(intent)
                            finish()
                        }, 2000)
                    } else {
                        Toast.makeText(this, "注册失败，请重试", Toast.LENGTH_SHORT).show()
                        btnRegister.isEnabled = true
                    }
                }
            },
            onFailure = { _, _ ->
                runOnUiThread {
                    Toast.makeText(this, "注册失败，请重试", Toast.LENGTH_SHORT).show()
                    btnRegister.isEnabled = true
                }
            }
        )
    }

    /** 短信验证码登录。 */
    private fun doSmsLogin(phone: String, code: String) {
        btnLogin.isEnabled = false
        HttpHelper.post(
            path = "/api/auth/app/sms/login",
            params = mapOf(
                "phone" to phone,
                "code" to code,
                "source" to "android"
            ),
            onSuccess = { resp ->
                handleLoginResponse(resp)
            },
            onFailure = { _, message ->
                runOnUiThread {
                    Toast.makeText(
                        this,
                        extractErrorMessage(message, "登录失败，请重试"),
                        Toast.LENGTH_SHORT
                    ).show()
                    btnLogin.isEnabled = true
                }
            }
        )
    }

    /** 手机号密码登录。接口约束为密码 6-32 位。 */
    private fun doPasswordLogin(phone: String, password: String) {
        btnLogin.isEnabled = false
        HttpHelper.post(
            path = "/api/auth/app/login",
            params = mapOf(
                "phone" to phone,
                "password" to password,
                "source" to "android"
            ),
            onSuccess = { resp ->
                handleLoginResponse(resp)
            },
            onFailure = { _, message ->
                runOnUiThread {
                    Toast.makeText(
                        this,
                        extractErrorMessage(message, "手机号或密码错误"),
                        Toast.LENGTH_SHORT
                    ).show()
                    btnLogin.isEnabled = true
                }
            }
        )
    }

    private fun handleLoginResponse(response: String) {
        val token = parseAccessToken(response)
        runOnUiThread {
            if (!token.isNullOrEmpty()) {
                TokenManager.saveToken(token)
                Toast.makeText(this, "登录成功", Toast.LENGTH_SHORT).show()
                Handler(Looper.getMainLooper()).postDelayed({
                    val intent = Intent(this, MainActivity::class.java)
                    intent.putExtra(MainActivity.EXTRA_TAB, "home")
                    intent.flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
                    startActivity(intent)
                    finish()
                }, 2000)
            } else {
                Toast.makeText(this, "登录失败，请重试", Toast.LENGTH_SHORT).show()
                btnLogin.isEnabled = true
            }
        }
    }

    private fun extractErrorMessage(rawMessage: String, fallback: String): String {
        if (rawMessage.isBlank()) return fallback
        return try {
            JSONObject(rawMessage).optString("detail").takeIf { it.isNotBlank() } ?: fallback
        } catch (_: Exception) {
            rawMessage.takeIf { it.length <= 80 } ?: fallback
        }
    }

    private fun parseAccessToken(resp: String): String? {
        if (resp.isBlank()) return null
        return try {
            val json = JSONObject(resp)
            json.optString("access_token").takeIf { it.isNotEmpty() }
                ?: json.optJSONObject("data")?.optString("access_token")?.takeIf { it.isNotEmpty() }
        } catch (e: Exception) {
            null
        }
    }

    private fun startCountDown() {
        btnGetCode.isEnabled = false
        btnGetCode.setBackgroundColor(0xFFF6F6F6.toInt())
        btnGetCode.setTextColor(0xFF333333.toInt())

        countDownTimer = object : CountDownTimer(90000, 1000) {
            override fun onTick(millisUntilFinished: Long) {
                val seconds = (millisUntilFinished / 1000).toInt()
                btnGetCode.text = "${seconds}秒后获取"
            }

            override fun onFinish() {
                btnGetCode.isEnabled = true
                btnGetCode.setBackgroundColor(accentColor)
                btnGetCode.setTextColor(0xFFFFFFFF.toInt())
                btnGetCode.text = getString(R.string.get_code)
            }
        }.start()
    }

    override fun onDestroy() {
        super.onDestroy()
        countDownTimer?.cancel()
    }
}
