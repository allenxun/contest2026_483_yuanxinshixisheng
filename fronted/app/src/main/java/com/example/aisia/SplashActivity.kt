package com.example.aisia

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityOptionsCompat

class SplashActivity : AppCompatActivity() {

    companion object {
        private const val SPLASH_DELAY = 2000L // 启动页显示时间（毫秒）
    }

    private val handler = Handler(Looper.getMainLooper())
    private var hasNavigated = false
    private val navigateRunnable = Runnable {
        if (hasNavigated || isFinishing || isDestroyed) return@Runnable
        hasNavigated = true
        val intent = Intent(this, MainActivity::class.java)
        // 使用无动画的 ActivityOptions 避免过渡黑屏
        val options = ActivityOptionsCompat.makeCustomAnimation(this, 0, 0)
        startActivity(intent, options.toBundle())
        finish()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_splash)

        // 延迟后跳转到 MainActivity
        handler.postDelayed(navigateRunnable, SPLASH_DELAY)
    }

    override fun onDestroy() {
        handler.removeCallbacks(navigateRunnable)
        super.onDestroy()
    }

    override fun finish() {
        handler.removeCallbacks(navigateRunnable)
        super.finish()
        @Suppress("DEPRECATION")
        overridePendingTransition(0, 0)
    }
}
