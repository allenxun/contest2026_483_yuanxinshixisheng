package com.example.aisia.ui.mine

import android.os.Bundle
import android.view.View
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.example.aisia.BuildConfig
import com.example.aisia.R
import com.example.aisia.privacy.PrivacyManager

/**
 * 关于我们：统一提供用户协议与隐私政策入口。
 * 两个入口复用登录页当前使用的同一份协议内容。
 */
class AboutUsActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_about_us)

        findViewById<View>(R.id.btnBack).setOnClickListener { finish() }
        findViewById<View>(R.id.layoutUserAgreement).setOnClickListener {
            PrivacyManager.showUserAgreementDialog(this)
        }
        findViewById<View>(R.id.layoutPrivacyPolicy).setOnClickListener {
            PrivacyManager.showPrivacyPolicyDialog(this)
        }
        findViewById<TextView>(R.id.tvVersion).text = "版本 ${BuildConfig.VERSION_NAME}"
    }
}
