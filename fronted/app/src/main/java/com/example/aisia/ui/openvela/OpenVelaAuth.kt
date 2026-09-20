package com.example.aisia.ui.openvela

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.util.Log
import com.example.aisia.AisiaApp
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Token 管理：负责保存、读取、清除登录后的 access_token
 */
object OpenVelaAuth {

    private const val TAG = "OpenVelaAuth"
    private const val PREF_NAME = "openvela_auth_v1"
    private const val LEGACY_KEY_TOKEN = "access_token"
    private const val KEY_TOKEN_CIPHERTEXT = "access_token_ciphertext"
    private const val KEY_TOKEN_IV = "access_token_iv"
    private const val KEY_ALIAS = "openvela_access_token_key_v1"
    private const val ANDROID_KEY_STORE = "AndroidKeyStore"
    private const val CIPHER_TRANSFORMATION = "AES/GCM/NoPadding"

    private val lock = Any()
    @Volatile private var memoryToken: String? = null

    private val sp by lazy {
        AisiaApp.instance.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
    }

    /**
     * 保存 token
     */
    fun saveToken(token: String) {
        synchronized(lock) {
            memoryToken = token
            try {
                val encrypted = encrypt(token)
                sp.edit()
                    .putString(KEY_TOKEN_CIPHERTEXT, encrypted.ciphertext)
                    .putString(KEY_TOKEN_IV, encrypted.iv)
                    .remove(LEGACY_KEY_TOKEN)
                    .apply()
            } catch (e: Exception) {
                // 不回退到明文落盘；当前进程仍可使用内存 token，避免登录流程中断。
                sp.edit()
                    .remove(LEGACY_KEY_TOKEN)
                    .remove(KEY_TOKEN_CIPHERTEXT)
                    .remove(KEY_TOKEN_IV)
                    .apply()
                Log.e(TAG, "保存加密登录凭据失败: ${e.javaClass.simpleName}")
            }
        }
    }

    /**
     * 获取 token，未登录时返回 null
     */
    private fun storedToken(): String? {
        memoryToken?.let { return it }
        return synchronized(lock) {
            memoryToken?.let { return@synchronized it }

            val ciphertext = sp.getString(KEY_TOKEN_CIPHERTEXT, null)
            val iv = sp.getString(KEY_TOKEN_IV, null)
            if (!ciphertext.isNullOrEmpty() && !iv.isNullOrEmpty()) {
                try {
                    return@synchronized decrypt(ciphertext, iv).also { memoryToken = it }
                } catch (e: Exception) {
                    Log.e(TAG, "读取加密登录凭据失败，清除失效数据: ${e.javaClass.simpleName}")
                    sp.edit().remove(KEY_TOKEN_CIPHERTEXT).remove(KEY_TOKEN_IV).apply()
                }
            }

            // 兼容升级前已经登录的用户：首次读取后原位迁移到 Keystore 加密存储。
            val legacyToken = sp.getString(LEGACY_KEY_TOKEN, null)
            if (!legacyToken.isNullOrEmpty()) {
                memoryToken = legacyToken
                try {
                    val encrypted = encrypt(legacyToken)
                    sp.edit()
                        .putString(KEY_TOKEN_CIPHERTEXT, encrypted.ciphertext)
                        .putString(KEY_TOKEN_IV, encrypted.iv)
                        .remove(LEGACY_KEY_TOKEN)
                        .apply()
                } catch (e: Exception) {
                    // 保留旧值以避免升级后意外退出登录，下次读取会继续尝试迁移。
                    Log.e(TAG, "迁移登录凭据失败: ${e.javaClass.simpleName}")
                }
                legacyToken
            } else {
                null
            }
        }
    }

    /**
     * 清除 token（登出时使用）
     */
    fun clearToken() {
        synchronized(lock) {
            memoryToken = null
            sp.edit()
                .remove("expires_at")
                .remove("account_id")
                .remove(LEGACY_KEY_TOKEN)
                .remove(KEY_TOKEN_CIPHERTEXT)
                .remove(KEY_TOKEN_IV)
                .apply()
        }
    }

    /**
     * 是否已登录
     */

    fun installationId(): String = synchronized(lock) {
        sp.getString("installation_id", null) ?: java.util.UUID.randomUUID().toString().also {
            sp.edit().putString("installation_id", it).apply()
        }
    }
    fun saveSession(data: org.json.JSONObject) {
        val token = data.getString("accessToken")
        val account = data.getString("accountId")
        require(account.isNotBlank())
        require(token.isNotBlank() && data.getString("tokenType") == "Bearer")
        val format = java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", java.util.Locale.US).apply {
            timeZone = java.util.TimeZone.getTimeZone("UTC"); isLenient = false
        }
        val expires = format.parse(data.getString("expiresAt"))?.time ?: error("缺少会话有效期")
        require(expires > System.currentTimeMillis()) { "会话已过期" }
        synchronized(lock) {
            saveToken(token)
            sp.edit().putLong("expires_at", expires).putString("account_id", account).apply()
        }
    }
    fun getToken(): String? {
        if (sp.getLong("expires_at", 0L) <= System.currentTimeMillis()) return null
        return storedToken()
    }
    fun clearIfCurrent(expected: String) {
        synchronized(lock) { if (storedToken() == expected) clearToken() }
    }
    fun isLoggedIn(): Boolean = !getToken().isNullOrEmpty()

    private data class EncryptedToken(val ciphertext: String, val iv: String)

    private fun encrypt(token: String): EncryptedToken {
        val cipher = Cipher.getInstance(CIPHER_TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateSecretKey())
        return EncryptedToken(
            ciphertext = Base64.encodeToString(cipher.doFinal(token.toByteArray(Charsets.UTF_8)), Base64.NO_WRAP),
            iv = Base64.encodeToString(cipher.iv, Base64.NO_WRAP)
        )
    }

    private fun decrypt(ciphertext: String, iv: String): String {
        val cipher = Cipher.getInstance(CIPHER_TRANSFORMATION)
        val ivBytes = Base64.decode(iv, Base64.NO_WRAP)
        cipher.init(Cipher.DECRYPT_MODE, getOrCreateSecretKey(), GCMParameterSpec(128, ivBytes))
        val plaintext = cipher.doFinal(Base64.decode(ciphertext, Base64.NO_WRAP))
        return plaintext.toString(Charsets.UTF_8)
    }

    private fun getOrCreateSecretKey(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEY_STORE).apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }

        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEY_STORE).run {
            init(
                KeyGenParameterSpec.Builder(
                    KEY_ALIAS,
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
                )
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setRandomizedEncryptionRequired(true)
                    .build()
            )
            generateKey()
        }
    }
}
