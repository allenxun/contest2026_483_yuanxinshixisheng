package com.example.aisia.ui.skintest

import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * GLB 上传 / 模型改造请求工具
 *
 * - uploadThreeAngles(): 上传 3 张人脸照片到 /upload，返回 GLB URL
 * - modifyModel(): 提交改造项（双眼皮、童话效果等），返回新的 GLB URL
 */
object UploadHelper {

    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(120, TimeUnit.SECONDS)
        .build()

    /**
     * 上传三角度人脸照片
     * @param front 正面照
     * @param left  左 45 度照
     * @param right 右 45 度照
     * @param baseUrl 服务地址，如 https://eveaisia.com
     * @param callback 主线程回调；url 为 null 时表示失败
     */
    fun uploadThreeAngles(
        front: File,
        left: File,
        right: File,
        baseUrl: String,
        callback: (url: String?, error: String?) -> Unit
    ) {
        Thread {
            try {
                val body = MultipartBody.Builder()
                    .setType(MultipartBody.FORM)
                    .addFormDataPart("type", "face_3angle")
                    .addFormDataPart("front", front.name, front.asRequestBody("image/jpeg".toMediaTypeOrNull()))
                    .addFormDataPart("left", left.name, left.asRequestBody("image/jpeg".toMediaTypeOrNull()))
                    .addFormDataPart("right", right.name, right.asRequestBody("image/jpeg".toMediaTypeOrNull()))
                    .build()

                val req = Request.Builder()
                    .url("${baseUrl.trimEnd('/')}/upload")
                    .post(body)
                    .build()

                client.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    if (!resp.isSuccessful) {
                        callback(null, "HTTP ${resp.code}: $text")
                        return@use
                    }
                    val url = parseGlbUrl(text)
                    if (url != null) callback(url, null) else callback(null, "未返回 GLB URL")
                }
            } catch (e: Exception) {
                callback(null, e.message ?: "网络异常")
            }
        }.start()
    }

    /**
     * 提交模型改造请求
     * @param sourceGlbUrl 上一步返回的 GLB URL
     * @param effectId 效果标识，如 "double_eyelid" / "fairy" / "slim_face"
     */
    fun modifyModel(
        sourceGlbUrl: String,
        effectId: String,
        baseUrl: String,
        callback: (newUrl: String?, error: String?) -> Unit
    ) {
        Thread {
            try {
                val json = JSONObject().apply {
                    put("source_glb", sourceGlbUrl)
                    put("effect", effectId)
                }
                val body = json.toString().toRequestBody("application/json".toMediaTypeOrNull())
                val req = Request.Builder()
                    .url("${baseUrl.trimEnd('/')}/model/modify")
                    .post(body)
                    .build()

                client.newCall(req).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    if (!resp.isSuccessful) {
                        callback(null, "HTTP ${resp.code}: $text")
                        return@use
                    }
                    val url = parseGlbUrl(text)
                    if (url != null) callback(url, null) else callback(null, "未返回新 GLB URL")
                }
            } catch (e: Exception) {
                callback(null, e.message ?: "网络异常")
            }
        }.start()
    }

    /**
     * 从接口响应 JSON 中提取 GLB URL
     * 兼容常见字段：glb_url / data.glb_url / url / data.url
     */
    private fun parseGlbUrl(text: String): String? {
        if (text.isBlank()) return null
        val direct = text.trim()
        // 可能是直接返回的 URL
        if (direct.startsWith("http") && direct.endsWith(".glb")) return direct
        return try {
            val root = JSONObject(direct)
            val candidates = listOf("glb_url", "url", "data")
            for (key in candidates) {
                val v = root.optString(key, "")
                if (v.startsWith("http") && v.endsWith(".glb")) return v
                if (key == "data") {
                    val nested = root.optJSONObject("data")
                    val nestedUrl = nested?.optString("glb_url", "")
                        ?: nested?.optString("url", "")
                    if (!nestedUrl.isNullOrEmpty() && nestedUrl.endsWith(".glb")) return nestedUrl
                }
            }
            null
        } catch (e: Exception) {
            null
        }
    }
}
