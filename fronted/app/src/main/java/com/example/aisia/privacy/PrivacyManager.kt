package com.example.aisia.privacy

import android.app.Activity
import android.app.AlertDialog
import android.app.Dialog
import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.TextPaint
import android.text.method.LinkMovementMethod
import android.text.style.ClickableSpan
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.core.content.ContextCompat
import com.example.aisia.R

/**
 * 隐私政策合规管理
 *
 * 合规要求（《个人信息保护法》及各大应用商店审核规范）：
 * 1. App 首次启动必须先弹出隐私政策弹窗，取得用户明确同意后，才能收集个人信息、申请敏感权限；
 * 2. 用户同意前，不得申请相机、位置、麦克风等敏感权限。
 *
 * 使用方式：
 * - [isAgreed] / [markAgreed]：读取/写入同意状态（SharedPreferences 持久化）；
 * - [ensureAgreed]：在 MainActivity 首次启动及各敏感权限申请入口调用，
 *   已同意则直接执行回调，未同意则先弹出隐私政策征得同意弹窗；
 * - [showPrivacyPolicyDialog]：全屏查看《隐私政策》原文。
 */
object PrivacyManager {

    private const val PREF_NAME = "aisia_privacy"
    private const val KEY_PRIVACY_AGREED = "privacy_agreed"

    /** 隐私政策地址（与登录页使用同一份） */
    const val PRIVACY_POLICY_URL = "https://eveaisia.com/face/privacy.html"

    /** 用户是否已同意隐私政策 */
    fun isAgreed(context: Context): Boolean {
        return context.applicationContext
            .getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
            .getBoolean(KEY_PRIVACY_AGREED, false)
    }

    /** 记录用户已同意隐私政策（使用 commit 同步落盘，确保"只弹一次"不受进程被杀影响） */
    fun markAgreed(context: Context) {
        context.applicationContext
            .getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_PRIVACY_AGREED, true)
            .commit()
    }

    /**
     * 确保用户已同意隐私政策后再执行 [onAgreed]。
     * - 已同意：立即执行 [onAgreed]；
     * - 未同意：弹出隐私政策征得同意弹窗，用户点击"同意并继续"后才执行 [onAgreed]；
     *   用户点击"不同意"会二次确认，仍不同意则退出应用。
     *
     * 合规要求：同意前不得收集个人信息、不得申请任何敏感权限。
     */
    fun ensureAgreed(activity: Activity, onAgreed: () -> Unit) {
        if (activity.isFinishing || activity.isDestroyed) return
        val agreed = isAgreed(activity)
        android.util.Log.d(
            "PrivacyManager",
            "ensureAgreed: activity=${activity.javaClass.simpleName}, alreadyAgreed=$agreed"
        )
        if (agreed) {
            onAgreed()
            return
        }
        showConsentDialog(activity, onAgreed)
    }

    // ==================== 首次启动隐私政策征得同意弹窗 ====================

    private fun showConsentDialog(activity: Activity, onAgreed: () -> Unit) {
        if (activity.isFinishing || activity.isDestroyed) return

        val dialog = Dialog(activity, android.R.style.Theme_Translucent_NoTitleBar)

        // 半透明遮罩根布局（消费触摸事件，防止穿透）
        val root = FrameLayout(activity).apply {
            setBackgroundColor(0x66000000)
            setOnClickListener { /* 消费点击 */ }
        }

        // 白色圆角卡片
        val card = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.bg_privacy_dialog)
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                gravity = Gravity.CENTER
                leftMargin = dp(activity, 38f)
                rightMargin = dp(activity, 38f)
            }
        }

        // 标题
        val tvTitle = TextView(activity).apply {
            text = "温馨提示"
            setTextColor(ContextCompat.getColor(activity, R.color.text_primary))
            textSize = 18f
            setTypeface(typeface, Typeface.BOLD)
            gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(activity, 24f) }
        }

        // 正文（含可点击的《隐私政策》链接）
        val tvContent = TextView(activity).apply {
            text = buildContentText(activity)
            setTextColor(ContextCompat.getColor(activity, R.color.text_primary))
            textSize = 14f
            setLineSpacing(dp(activity, 4f).toFloat(), 1f)
            movementMethod = LinkMovementMethod.getInstance()
            highlightColor = Color.TRANSPARENT
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                topMargin = dp(activity, 16f)
                leftMargin = dp(activity, 20f)
                rightMargin = dp(activity, 20f)
            }
        }

        val scrollView = ScrollView(activity).apply {
            isVerticalScrollBarEnabled = false
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
            addView(tvContent)
        }

        // 同意按钮
        val btnAgree = TextView(activity).apply {
            text = "同意并继续"
            setTextColor(Color.WHITE)
            textSize = 16f
            gravity = Gravity.CENTER
            setBackgroundResource(R.drawable.bg_privacy_btn_primary)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(activity, 44f)
            ).apply {
                topMargin = dp(activity, 20f)
                leftMargin = dp(activity, 20f)
                rightMargin = dp(activity, 20f)
            }
            setOnClickListener {
                dialog.dismiss()
                markAgreed(activity)
                onAgreed()
            }
        }

        // 不同意按钮
        val btnDisagree = TextView(activity).apply {
            text = "不同意"
            setTextColor(ContextCompat.getColor(activity, R.color.text_secondary))
            textSize = 14f
            gravity = Gravity.CENTER
            setPadding(0, dp(activity, 12f), 0, dp(activity, 16f))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(activity, 4f) }
            setOnClickListener {
                showDisagreeConfirmDialog(activity, dialog, onAgreed)
            }
        }

        card.addView(tvTitle)
        card.addView(scrollView)
        card.addView(btnAgree)
        card.addView(btnDisagree)
        root.addView(card)

        dialog.setContentView(root)
        // 合规要求：弹窗不可被返回键/点击外部跳过，用户必须明确选择
        dialog.setCancelable(false)
        dialog.setCanceledOnTouchOutside(false)
        dialog.show()
        dialog.window?.setLayout(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT
        )
    }

    /** 构建弹窗正文，《隐私政策》可点击跳转全文 */
    private fun buildContentText(activity: Activity): SpannableStringBuilder {
        val builder = SpannableStringBuilder()
        builder.append("欢迎使用 Aisia！我们非常重视您的个人信息保护，请您在使用本应用前仔细阅读并充分理解")
        val start = builder.length
        builder.append("《隐私政策》")
        val end = builder.length
        builder.append("的全部内容。\n\n我们向您说明如下：\n")
        builder.append("1. 为提供智能测肤、3D 建模等功能，我们会向您申请相机权限（用于拍摄肌肤照片）；\n")
        builder.append("2. 为提供美容仪器连接功能（蓝牙/WiFi），我们会向您申请位置权限（用于蓝牙设备扫描及 WiFi 网络扫描）；\n")
        builder.append("3. 为提供语音输入功能，我们会向您申请麦克风权限；\n")
        builder.append("4. 上述权限均不会默认开启，仅在您主动使用对应功能时才会向您申请，您可以拒绝或在系统设置中随时撤回授权；\n")
        builder.append("5. 在您同意本政策前，我们不会收集您的任何个人信息，也不会申请任何敏感权限。\n\n")
        builder.append("如您同意，请点击\"同意并继续\"开始使用我们的服务。")

        builder.setSpan(
            object : ClickableSpan() {
                override fun onClick(widget: View) {
                    showPrivacyPolicyDialog(activity)
                }

                override fun updateDrawState(ds: TextPaint) {
                    ds.color = ContextCompat.getColor(activity, R.color.brand_gold)
                    ds.isUnderlineText = false
                }
            },
            start, end,
            Spanned.SPAN_EXCLUSIVE_EXCLUSIVE
        )
        return builder
    }

    /** 用户点击"不同意"时的二次确认弹窗 */
    private fun showDisagreeConfirmDialog(
        activity: Activity,
        consentDialog: Dialog,
        onAgreed: () -> Unit
    ) {
        if (activity.isFinishing || activity.isDestroyed) return
        AlertDialog.Builder(activity)
            .setTitle("温馨提示")
            .setMessage("您需要同意《隐私政策》后才能使用本应用。若您不同意，我们将无法为您提供服务，并会退出应用。")
            .setCancelable(false)
            .setPositiveButton("同意并继续") { _, _ ->
                consentDialog.dismiss()
                markAgreed(activity)
                onAgreed()
            }
            .setNegativeButton("不同意并退出") { _, _ ->
                consentDialog.dismiss()
                activity.finishAffinity()
            }
            .show()
    }

    // ==================== 协议全文查看弹窗 ====================

    /** 前端登录页《AISIA 用户授权协议》原文。 */
    private val userAgreementSections = listOf(
        "账户与身份验证授权" to
            "授权使用手机号验证码或微信身份标识完成注册、登录、账户找回和跨端绑定。",
        "相机与图像处理授权" to
            "点击开始测肤后调用相机采集正面及左右侧图像，并先完成角度、光线、模糊和遮挡判断。",
        "皮肤健康信息单独授权" to
            "授权处理皮肤图像、量化指标、问题标签、症状回答和历史变化，用于报告与趋势追踪。",
        "智能分析与边界" to
            "端侧模型负责质量检测，云端模型生成结构化结果；智能分析结果不等同于医疗诊断或处方。",
        "医生服务授权" to
            "仅在你主动发起问诊或报告复核后，将必要报告提供给医生。",
        "可选权限与撤回" to
            "相册、通知、位置和营销消息均为可选权限；撤回相机或皮肤信息授权后将无法继续自动测肤。"
    )

    /** 全屏弹窗查看登录页使用的《用户隐私协议》原文。 */
    fun showPrivacyPolicyDialog(context: Context) {
        val webView = WebView(context).apply {
            settings.javaScriptEnabled = false
            settings.domStorageEnabled = false
            webViewClient = WebViewClient()
            isClickable = true
        }
        webView.loadUrl(PRIVACY_POLICY_URL)
        showPolicyDocumentDialog(context, "用户隐私协议", webView)
    }

    /** 全屏弹窗查看前端登录页使用的《用户授权协议》原文。 */
    fun showUserAgreementDialog(context: Context) {
        val contentLayout = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(
                dp(context, 20f),
                dp(context, 12f),
                dp(context, 20f),
                dp(context, 32f)
            )
        }

        userAgreementSections.forEachIndexed { index, (sectionTitle, sectionContent) ->
            contentLayout.addView(
                TextView(context).apply {
                    text = sectionTitle
                    textSize = 17f
                    setTextColor(0xFF333333.toInt())
                    setTypeface(typeface, Typeface.BOLD)
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT
                    ).apply {
                        topMargin = dp(context, if (index == 0) 8f else 20f)
                    }
                }
            )
            contentLayout.addView(
                TextView(context).apply {
                    text = sectionContent
                    textSize = 15f
                    setTextColor(0xFF555555.toInt())
                    setLineSpacing(dp(context, 4f).toFloat(), 1f)
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT
                    ).apply {
                        topMargin = dp(context, 8f)
                    }
                }
            )
        }

        val scrollView = ScrollView(context).apply {
            isVerticalScrollBarEnabled = false
            addView(contentLayout)
        }
        showPolicyDocumentDialog(context, "AISIA 用户授权协议", scrollView)
    }

    /** 协议页面共用的全屏容器，登录页和关于我们均调用这里。 */
    private fun showPolicyDocumentDialog(context: Context, title: String, contentView: View) {
        val dialog = Dialog(context, android.R.style.Theme_Black_NoTitleBar_Fullscreen)

        val rootLayout = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.WHITE)
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
        }

        val titleBar = FrameLayout(context).apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(context, 56f)
            )
            setPadding(dp(context, 16f), 0, dp(context, 8f), 0)
        }

        val tvTitle = TextView(context).apply {
            text = title
            textSize = 18f
            setTextColor(0xFF333333.toInt())
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                gravity = Gravity.CENTER
                leftMargin = dp(context, 16f)
            }
        }

        val ivClose = ImageView(context).apply {
            setImageResource(R.drawable.ic_close_dark)
            setPadding(dp(context, 12f), dp(context, 12f), dp(context, 12f), dp(context, 12f))
            layoutParams = FrameLayout.LayoutParams(
                dp(context, 48f), dp(context, 48f)
            ).apply {
                gravity = Gravity.END or Gravity.CENTER_VERTICAL
            }
            setBackgroundColor(Color.TRANSPARENT)
            setOnClickListener { dialog.dismiss() }
        }

        titleBar.addView(tvTitle)
        titleBar.addView(ivClose)

        val divider = View(context).apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(context, 1f)
            )
            setBackgroundColor(0xFFEEEEEE.toInt())
        }

        contentView.layoutParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            0,
            1f
        )

        rootLayout.addView(titleBar)
        rootLayout.addView(divider)
        rootLayout.addView(contentView)
        rootLayout.setOnClickListener { /* 消费点击，防止穿透 */ }

        dialog.setContentView(rootLayout)
        dialog.setCancelable(true)
        dialog.show()
    }

    private fun dp(context: Context, dp: Float): Int {
        return (dp * context.resources.displayMetrics.density + 0.5f).toInt()
    }
}
