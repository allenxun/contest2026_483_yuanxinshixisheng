package com.example.aisia.network

import com.example.aisia.BuildConfig

/**
 * API 接口配置
 * 根据不同构建类型自动切换环境地址：
 * - debug（开发环境）: https://dev-eveaisia.com/
 * - release（正式环境）: https://eveaisia.com/
 */
object ApiConfig {

    /**
     * 接口基础地址，根据 BuildConfig 自动选择对应环境
     */
    val BASE_URL: String = BuildConfig.BASE_URL
}
