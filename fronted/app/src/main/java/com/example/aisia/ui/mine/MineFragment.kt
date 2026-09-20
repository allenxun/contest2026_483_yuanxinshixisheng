package com.example.aisia.ui.mine

import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.ImageView
import android.widget.TextView
import androidx.fragment.app.Fragment
import coil.load
import coil.transform.CircleCropTransformation
import com.example.aisia.R
import com.example.aisia.network.HttpHelper
import com.example.aisia.network.TokenManager
import com.example.aisia.ui.devicehistory.DeviceHistoryActivity
import com.example.aisia.ui.login.LoginActivity
import com.example.aisia.ui.mine.ProfileActivity
import com.example.aisia.ui.skinhistory.SkinHistoryActivity
import com.example.aisia.ui.model3d.Model3DListActivity
import org.json.JSONObject

class MineFragment : Fragment(R.layout.fragment_mine) {

    companion object {
        private const val DEFAULT_AVATAR_URL = "https://eveaisia.com/face/img/user.png"
        private const val SKIN_HISTORY_ICON_URL = "https://eveaisia.com/face/img/mine_face.png"
        private const val DEVICE_HISTORY_ICON_URL = "https://eveaisia.com/face/img/mine_dev.png"
        private const val CARE_ICON_URL = "https://eveaisia.com/face/img/mine_face.png"
        private const val MODEL3D_ICON_URL = "https://eveaisia.com/face/img/mine_face.png"
    }

    private lateinit var ivAvatar: ImageView
    private lateinit var tvNickname: TextView
    private lateinit var tvPhone: TextView

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        ivAvatar = view.findViewById(R.id.ivAvatar)
        tvNickname = view.findViewById(R.id.tvNickname)
        tvPhone = view.findViewById(R.id.tvPhone)

        // 加载默认头像
        ivAvatar.load(DEFAULT_AVATAR_URL) {
            crossfade(true)
            placeholder(R.drawable.ic_default_avatar)
            error(R.drawable.ic_default_avatar)
            transformations(CircleCropTransformation())
        }

        // 加载菜单图标
        view.findViewById<ImageView>(R.id.ivSkinHistoryIcon).load(SKIN_HISTORY_ICON_URL) {
            crossfade(true)
            placeholder(R.drawable.mine_face)
            error(R.drawable.mine_face)
        }
        view.findViewById<ImageView>(R.id.ivDeviceHistoryIcon).load(DEVICE_HISTORY_ICON_URL) {
            crossfade(true)
            placeholder(R.drawable.mine_dev)
            error(R.drawable.mine_dev)
        }
        // [护理] 入口暂时隐藏：不再加载其图标（恢复时去掉 XML 中 visibility=gone 并解开以下注释）
        // view.findViewById<ImageView>(R.id.ivCareIcon).load(CARE_ICON_URL) {
        //     crossfade(true)
        //     placeholder(R.drawable.mine_face)
        //     error(R.drawable.mine_face)
        // }
        view.findViewById<ImageView>(R.id.ivModel3DIcon).load(MODEL3D_ICON_URL) {
            crossfade(true)
            placeholder(R.drawable.mine_face)
            error(R.drawable.mine_face)
        }

        view.findViewById<ImageView>(R.id.ivOpenVelaHistoryIcon).load(SKIN_HISTORY_ICON_URL) {
            crossfade(true)
            placeholder(R.drawable.mine_face)
            error(R.drawable.mine_face)
        }

        // 头像点击：判断登录状态，未登录跳转登录页，已登录跳转个人中心页
        view.findViewById<View>(R.id.layoutAvatar).setOnClickListener {
            val ctx = context ?: return@setOnClickListener
            if (TokenManager.isLoggedIn()) {
                startActivity(Intent(ctx, ProfileActivity::class.java))
            } else {
                startActivity(Intent(ctx, LoginActivity::class.java))
            }
        }

        // 测肤历史
        view.findViewById<View>(R.id.layoutOpenVelaHistory).setOnClickListener {
            startActivity(Intent(requireContext(), com.example.aisia.ui.openvela.OpenVelaPeopleActivity::class.java))
        }

        view.findViewById<View>(R.id.layoutSkinHistory).setOnClickListener {
            val ctx = context ?: return@setOnClickListener
            startActivity(Intent(ctx, SkinHistoryActivity::class.java))
        }

        // 设备历史
        view.findViewById<View>(R.id.layoutDeviceHistory).setOnClickListener {
            val ctx = context ?: return@setOnClickListener
            startActivity(Intent(ctx, DeviceHistoryActivity::class.java))
        }

        // 护理入口（暂时隐藏）
        // view.findViewById<View>(R.id.layoutCare).setOnClickListener {
        //     val ctx = context ?: return@setOnClickListener
        //     startActivity(Intent(ctx, com.example.aisia.ui.skincare.ProjectDetailActivity::class.java))
        // }

        // 3D模型列表
        view.findViewById<View>(R.id.layoutModel3D).setOnClickListener {
            val ctx = context ?: return@setOnClickListener
            startActivity(Intent(ctx, Model3DListActivity::class.java))
        }

        // 关于我们：用户协议、隐私协议
        view.findViewById<View>(R.id.layoutAbout).setOnClickListener {
            val ctx = context ?: return@setOnClickListener
            startActivity(Intent(ctx, AboutUsActivity::class.java))
        }

        // 首次进入"我的"时拉取资料
        fetchUserProfile()
    }

    override fun onHiddenChanged(hidden: Boolean) {
        super.onHiddenChanged(hidden)
        // 每次切换到"我的"时拉取资料
        if (!hidden) {
            fetchUserProfile()
        }
    }

    /**
     * 调用 /api/user/profile 拉取用户资料
     * 401 由 HttpHelper 全局统一处理（清 token + 跳登录页）
     */
    private fun fetchUserProfile() {
        HttpHelper.get(
            path = "/api/user/profile",
            onSuccess = { resp ->
                val activity = activity ?: return@get
                activity.runOnUiThread { applyProfile(resp) }
            },
            onFailure = { _, _ -> /* 401 已全局处理，其他错误不吵扰用户 */ }
        )
    }

    /**
     * 解析接口返回，刷新 UI
     * 后端协议字段（详见 API_CHANGES_FOR_FRONTEND.md §2.4）：
     *   user_id    string   用户 ID（雪花 BIGINT 字符串）
     *   nickname   string?  昵称
     *   phone      string?  手机号（脱敏 138****5678）
     *   avatar_url string?  头像 URL
     *   birthday   string?  YYYY-MM-DD
     *   location   object?  { province, city, district }
     * 兼容多种常见响应包装结构：
     * - {nickname: ..., phone: ...}
     * - {data: {nickname: ..., phone: ...}}
     * - {data: {profile: {nickname: ..., phone: ...}}}
     * - {result: {nickname: ..., phone: ...}}
     */
    private fun applyProfile(resp: String) {
        Log.d("MineFragment", "profile loaded")

        val profile = extractProfileObject(resp)
        Log.d("MineFragment", "parsed profile keys: ${profile?.keys()?.asSequence()?.toList()}")

        // 昵称（后端字段已由 name 改为 nickname）
        val nickname = profile.readString("nickname")
        tvNickname.text = if (nickname.isNotEmpty()) nickname else getString(R.string.not_logged_in)

        // 手机号：null 或 空字符串显示"未绑定"
        val phone = profile.readString("phone")
        tvPhone.text = if (phone.isEmpty()) {
            getString(R.string.phone_unbound)
        } else {
            phone
        }

        // 头像：优先使用后端返回的 avatar_url，否则使用默认头像
        val avatarUrl = profile.readString("avatar_url")
        val finalAvatarUrl = if (avatarUrl.isNotEmpty()) avatarUrl else DEFAULT_AVATAR_URL
        ivAvatar.load(finalAvatarUrl) {
            crossfade(true)
            placeholder(R.drawable.ic_default_avatar)
            error(R.drawable.ic_default_avatar)
            transformations(CircleCropTransformation())
        }
    }

    /**
     * 从响应中提取包含用户资料的 JSONObject，
     * 逐层查找 nickname/phone 字段所在的对象。
     */
    private fun extractProfileObject(resp: String): JSONObject? {
        if (resp.isBlank()) return null
        val root = try {
            JSONObject(resp)
        } catch (e: Exception) {
            return null
        }
        // 如果根对象本身就有 nickname 字段，直接返回
        if (root.has("nickname")) return root

        // 依次尝试常见包装字段
        for (wrapper in listOf("data", "result", "payload")) {
            val obj = root.optJSONObject(wrapper) ?: continue
            if (obj.has("nickname")) return obj
            // 再嵌套一层（如 data.profile）
            for (inner in listOf("profile", "user", "userInfo", "info")) {
                val nested = obj.optJSONObject(inner)
                if (nested != null && nested.has("nickname")) return nested
            }
            // 如果都不匹配，退而返回这个 wrapper 对象
            return obj
        }
        return root
    }

    /**
     * 安全读取字符串字段，处理 JSON null 与 字面量"null"字符串
     */
    private fun JSONObject?.readString(key: String): String {
        if (this == null) return ""
        if (this.isNull(key)) return ""
        val value = this.optString(key, "")
        return if (value.equals("null", ignoreCase = true)) "" else value
    }
}
