package com.example.aisia.ui.mine

import android.app.AlertDialog
import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import coil.load
import coil.transform.CircleCropTransformation
import com.example.aisia.R
import com.example.aisia.network.HttpHelper
import com.example.aisia.network.TokenManager
import com.example.aisia.ui.login.LoginActivity
import org.json.JSONObject

/**
 * 个人中心页面（模仿小程序 profile）
 * - 显示头像、昵称、手机号
 * - 修改个人信息按钮（跳转到编辑页）
 * - 退出登录与注销账号均先调用服务端接口，成功后清除本地 token
 * - 进入时调用 GET /api/user/profile 加载资料
 */
class ProfileActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "ProfileActivity"
    }

    private lateinit var ivAvatar: ImageView
    private lateinit var tvNickname: TextView
    private lateinit var tvPhone: TextView
    private lateinit var btnLogout: TextView
    private lateinit var btnDeactivate: TextView
    private var accountActionInProgress = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_profile)

        ivAvatar = findViewById(R.id.ivAvatar)
        tvNickname = findViewById(R.id.tvNickname)
        tvPhone = findViewById(R.id.tvPhone)
        btnLogout = findViewById(R.id.btnLogout)
        btnDeactivate = findViewById(R.id.btnDeactivate)

        findViewById<View>(R.id.btnBack).setOnClickListener { finish() }

        // 修改个人信息按钮（与小程序 onEditTap 一致）
        findViewById<View>(R.id.btnEdit).setOnClickListener {
            startActivity(Intent(this, ProfileEditActivity::class.java))
        }

        btnLogout.setOnClickListener {
            showLogoutDialog()
        }

        btnDeactivate.setOnClickListener {
            showDeactivateDialog()
        }

        loadProfile()
    }

    override fun onResume() {
        super.onResume()
        // 每次回到页面时重新加载（与小程序 onShow 行为一致）
        loadProfile()
    }

    /**
     * 加载用户资料（与小程序 loadProfile 一致）
     * API: GET /api/user/profile
     */
    private fun loadProfile() {
        HttpHelper.get(
            path = "/api/user/profile",
            onSuccess = { resp ->
                runOnUiThread { bindProfile(resp) }
            },
            onFailure = { code, msg ->
                Log.e(TAG, "load profile failed: $code $msg")
            }
        )
    }

    /**
     * 绑定用户资料到 UI（与小程序 setData({ profile: res.profile || {} }) 一致）
     */
    private fun bindProfile(resp: String) {
        if (resp.isBlank()) return
        try {
            val root = JSONObject(resp)
            val profile = extractProfile(root)

            // 头像（与小程序 profile.avatar_url || 默认头像 一致）
            val avatarUrl = profile.optString("avatar_url")
            if (avatarUrl.isNotBlank() && avatarUrl != "null") {
                ivAvatar.load(avatarUrl) {
                    crossfade(true)
                    transformations(CircleCropTransformation())
                    error(R.drawable.ic_default_avatar)
                }
            }

            // 昵称（与小程序 profile.nickname || '' 一致）
            val nickname = profile.optString("nickname")
            tvNickname.text = if (nickname.isBlank() || nickname == "null") "" else nickname

            // 手机号（与小程序 profile.phone || '未绑定' 一致）
            val phone = profile.optString("phone")
            tvPhone.text = if (phone.isBlank() || phone == "null") "未绑定" else phone
        } catch (e: Exception) {
            Log.e(TAG, "parse profile failed", e)
        }
    }

    /**
     * 从响应中提取 profile 对象（兼容多种包装结构）
     */
    private fun extractProfile(root: JSONObject): JSONObject {
        // 直接有 nickname 字段
        if (root.has("nickname")) return root
        // data.profile 结构
        val data = root.optJSONObject("data")
        if (data != null) {
            if (data.has("nickname")) return data
            val profile = data.optJSONObject("profile")
            if (profile != null) return profile
        }
        // result 结构
        val result = root.optJSONObject("result")
        if (result != null && result.has("nickname")) return result
        return root
    }

    /**
     * 退出登录确认弹窗。
     * 确认后调用服务端退出接口，成功再清除本地 token 并跳转登录页。
     */
    private fun showLogoutDialog() {
        AlertDialog.Builder(this)
            .setTitle("退出登录")
            .setMessage("确认退出登录？")
            .setPositiveButton("确认") { _, _ ->
                performAccountAction(
                    path = "/api/auth/app/logout",
                    successMessage = "已退出登录",
                    failureFallback = "退出登录失败，请稍后重试"
                )
            }
            .setNegativeButton("取消", null)
            .show()
    }

    private fun showDeactivateDialog() {
        val dialog = AlertDialog.Builder(this)
            .setTitle("注销账号")
            .setMessage(
                "注销后账号将立即退出，并进入90天冷静期。冷静期内可以恢复账号；" +
                    "超过冷静期后原账号将无法恢复。确认继续注销？"
            )
            .setPositiveButton("确认注销") { _, _ ->
                performAccountAction(
                    path = "/api/auth/app/deactivate",
                    successMessage = "账号已注销",
                    failureFallback = "注销账号失败，请稍后重试"
                )
            }
            .setNegativeButton("取消", null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setTextColor(0xFFD94A4A.toInt())
        }
        dialog.show()
    }

    private fun performAccountAction(
        path: String,
        successMessage: String,
        failureFallback: String
    ) {
        if (accountActionInProgress) return
        setAccountActionsEnabled(false)

        HttpHelper.postEmpty(
            path = path,
            onSuccess = {
                runOnUiThread {
                    if (isFinishing || isDestroyed) return@runOnUiThread
                    finishAccountSession(successMessage)
                }
            },
            onFailure = { code, message ->
                runOnUiThread {
                    if (isFinishing || isDestroyed) return@runOnUiThread
                    if (code == 401) {
                        // HttpHelper 已统一清 Token 并跳转登录页。
                        finish()
                        return@runOnUiThread
                    }
                    setAccountActionsEnabled(true)
                    Toast.makeText(
                        this,
                        extractErrorMessage(message, failureFallback),
                        Toast.LENGTH_SHORT
                    ).show()
                }
            }
        )
    }

    private fun setAccountActionsEnabled(enabled: Boolean) {
        accountActionInProgress = !enabled
        btnLogout.isEnabled = enabled
        btnDeactivate.isEnabled = enabled
        val alpha = if (enabled) 1f else 0.5f
        btnLogout.alpha = alpha
        btnDeactivate.alpha = alpha
    }

    private fun finishAccountSession(message: String) {
        TokenManager.clearToken()
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
        val intent = Intent(this, LoginActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        }
        startActivity(intent)
        finish()
    }

    private fun extractErrorMessage(rawMessage: String, fallback: String): String {
        if (rawMessage.isBlank()) return fallback
        return try {
            val json = JSONObject(rawMessage)
            json.optString("detail", "")
                .ifBlank { json.optString("message", "") }
                .ifBlank { json.optString("error", "") }
                .ifBlank { fallback }
        } catch (_: Exception) {
            rawMessage.takeIf { it.length <= 100 } ?: fallback
        }
    }
}
