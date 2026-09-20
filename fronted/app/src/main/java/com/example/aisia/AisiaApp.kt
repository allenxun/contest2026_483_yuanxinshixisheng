package com.example.aisia

import android.app.Application
import com.example.aisia.ble.BleManager

/**
 * 应用全局 Application 类
 * 用于提供全局 Context，便于在没有 Activity 上下文时使用（如 TokenManager 持久化）
 */
class AisiaApp : Application() {

    override fun onCreate() {
        super.onCreate()
        instance = this
    }

    override fun onTerminate() {
        // 应用退出时释放 BLE 连接（真机上此方法不一定被调，但做一层保护）
        try {
            BleManager.disconnect()
        } catch (_: Throwable) {}
        super.onTerminate()
    }

    companion object {
        lateinit var instance: AisiaApp
            private set
    }
}