package com.example.aisia.ui.mine

import android.app.AlertDialog
import android.os.Bundle
import android.util.Log
import android.widget.EditText
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import coil.load
import com.example.aisia.R
import com.example.aisia.network.HttpHelper
import org.json.JSONObject

class ProfileEditActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "ProfileEditActivity"
    }

    private lateinit var ivAvatar: ImageView
    private lateinit var etNickname: EditText
    private lateinit var tvPhone: TextView
    private lateinit var btnChangePassword: TextView
    private lateinit var btnSave: TextView

    private var avatarUrl: String? = null
    private var phone: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_profile_edit)

        initViews()
        setupListeners()
        loadProfile()
    }

    private fun initViews() {
        ivAvatar = findViewById(R.id.ivAvatar)
        etNickname = findViewById(R.id.etNickname)
        tvPhone = findViewById(R.id.tvPhone)
        btnChangePassword = findViewById(R.id.btnChangePassword)
        btnSave = findViewById(R.id.btnSave)
    }

    private fun setupListeners() {
        btnSave.setOnClickListener {
            saveProfile()
        }
        btnChangePassword.setOnClickListener {
            showChangePasswordDialog()
        }
    }

    private fun loadProfile() {
        HttpHelper.get(
            path = "/api/user/profile",
            onSuccess = { response ->
                runOnUiThread {
                    parseProfile(response)
                }
            },
            onFailure = { code, msg ->
                Log.e(TAG, "加载资料失败: $code, $msg")
                runOnUiThread {
                    Toast.makeText(this, "加载资料失败", Toast.LENGTH_SHORT).show()
                }
            }
        )
    }

    private fun parseProfile(response: String) {
        try {
            val json = JSONObject(response)
            val profile = json.optJSONObject("profile") ?: json
            
            // 头像
            avatarUrl = profile.optString("avatar_url", null)
            if (!avatarUrl.isNullOrEmpty()) {
                ivAvatar.load(avatarUrl) {
                    crossfade(true)
                    placeholder(R.drawable.ic_default_avatar)
                    error(R.drawable.ic_default_avatar)
                }
            }
            
            // 昵称
            val nickname = profile.optString("nickname", "")
            if (nickname.isNotEmpty()) {
                etNickname.setText(nickname)
            }
            
            // 手机号
            phone = profile.optString("phone", null)
            if (!phone.isNullOrEmpty()) {
                tvPhone.text = phone
                tvPhone.setTextColor(getColor(R.color.text_primary))
            } else {
                tvPhone.text = "点击绑定手机号"
                tvPhone.setTextColor(getColor(R.color.text_secondary))
            }
        } catch (e: Exception) {
            Log.e(TAG, "解析资料失败", e)
            Toast.makeText(this, "解析资料失败", Toast.LENGTH_SHORT).show()
        }
    }

    private fun saveProfile() {
        val nickname = etNickname.text.toString().trim()
        
        if (nickname.isEmpty()) {
            Toast.makeText(this, "昵称不能为空", Toast.LENGTH_SHORT).show()
            return
        }

        val params = mapOf(
            "nickname" to nickname
        )

        HttpHelper.put(
            path = "/api/user/profile",
            params = params,
            onSuccess = {
                runOnUiThread {
                    Toast.makeText(this, "保存成功", Toast.LENGTH_SHORT).show()
                    finish()
                }
            },
            onFailure = { code, msg ->
                Log.e(TAG, "保存失败: $code, $msg")
                runOnUiThread {
                    Toast.makeText(this, "保存失败", Toast.LENGTH_SHORT).show()
                }
            }
        )
    }

    private fun showChangePasswordDialog() {
        val contentView = layoutInflater.inflate(R.layout.dialog_change_password, null)
        val etOldPassword = contentView.findViewById<EditText>(R.id.etOldPassword)
        val etNewPassword = contentView.findViewById<EditText>(R.id.etNewPassword)
        val etConfirmPassword = contentView.findViewById<EditText>(R.id.etConfirmPassword)

        val dialog = AlertDialog.Builder(this)
            .setTitle(R.string.change_password)
            .setView(contentView)
            .setNegativeButton("取消", null)
            .setPositiveButton("确认", null)
            .create()

        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val oldPassword = etOldPassword.text.toString()
                val newPassword = etNewPassword.text.toString()
                val confirmPassword = etConfirmPassword.text.toString()

                when {
                    oldPassword.length !in 6..32 -> {
                        etOldPassword.error = "请输入6-32位旧密码"
                        etOldPassword.requestFocus()
                    }

                    newPassword.length !in 8..32 -> {
                        etNewPassword.error = "新密码需要8-32位"
                        etNewPassword.requestFocus()
                    }

                    confirmPassword != newPassword -> {
                        etConfirmPassword.error = "两次输入的新密码不一致"
                        etConfirmPassword.requestFocus()
                    }

                    else -> changePassword(dialog, oldPassword, newPassword)
                }
            }
        }
        dialog.show()
    }

    private fun changePassword(dialog: AlertDialog, oldPassword: String, newPassword: String) {
        val submitButton = dialog.getButton(AlertDialog.BUTTON_POSITIVE)
        submitButton.isEnabled = false
        submitButton.text = "提交中…"

        HttpHelper.post(
            path = "/api/auth/app/password",
            params = mapOf(
                "old_password" to oldPassword,
                "password" to newPassword
            ),
            onSuccess = { response ->
                val succeeded = try {
                    JSONObject(response).optBoolean("success", true)
                } catch (_: Exception) {
                    true
                }
                runOnUiThread {
                    if (succeeded) {
                        dialog.dismiss()
                        Toast.makeText(this, "密码修改成功", Toast.LENGTH_SHORT).show()
                    } else {
                        submitButton.isEnabled = true
                        submitButton.text = "确认"
                        Toast.makeText(this, "密码修改失败，请重试", Toast.LENGTH_SHORT).show()
                    }
                }
            },
            onFailure = { code, message ->
                Log.e(TAG, "修改密码失败: $code, $message")
                runOnUiThread {
                    if (dialog.isShowing) {
                        submitButton.isEnabled = true
                        submitButton.text = "确认"
                    }
                    Toast.makeText(
                        this,
                        extractErrorMessage(message, "密码修改失败，请重试"),
                        Toast.LENGTH_SHORT
                    ).show()
                }
            }
        )
    }

    private fun extractErrorMessage(rawMessage: String, fallback: String): String {
        if (rawMessage.isBlank()) return fallback
        return try {
            JSONObject(rawMessage).optString("detail").takeIf { it.isNotBlank() } ?: fallback
        } catch (_: Exception) {
            rawMessage.takeIf { it.length <= 80 } ?: fallback
        }
    }
}
