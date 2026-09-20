package com.example.aisia.ui.openvela

import android.content.Context
import android.widget.ImageView
import coil.ImageLoader
import coil.load
import coil.request.CachePolicy
import coil.transform.Transformation
import com.example.aisia.AisiaApp
import com.example.aisia.R
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

/** No cross-origin credentials, redirects or persistent personal-image caches. */
internal object OpenVelaImages {
    private val loader by lazy {
        val client = OkHttpClient.Builder().followRedirects(false).followSslRedirects(false)
            .connectTimeout(15, TimeUnit.SECONDS).readTimeout(20, TimeUnit.SECONDS).callTimeout(25, TimeUnit.SECONDS)
            .addInterceptor { chain ->
                val request = chain.request()
                if (OpenVelaApi.image(request.url.toString()) == null) throw java.io.IOException("不允许的图片来源")
                val builder = request.newBuilder().removeHeader("Authorization").header("Cache-Control", "no-store")
                if (OpenVelaApi.media(request.url.toString()) != null) {
                    val token = OpenVelaAuth.getToken()?.takeIf { it.isNotBlank() } ?: throw java.io.IOException("未登录")
                    builder.header("Authorization", "Bearer " + token)
                }
                chain.proceed(builder.build())
            }.build()
        ImageLoader.Builder(AisiaApp.instance).okHttpClient(client)
            .memoryCachePolicy(CachePolicy.DISABLED).diskCachePolicy(CachePolicy.DISABLED).build()
    }
    fun bind(view: ImageView, raw: String?, transformations: List<Transformation> = emptyList(),
        success: () -> Unit = {}, failure: () -> Unit = {}) {
        val url = OpenVelaApi.image(raw)
        view.load(url, loader) {
            size(360)
            placeholder(R.drawable.ic_default_avatar)
            fallback(R.drawable.ic_default_avatar)
            error(R.drawable.ic_default_avatar)
            if (transformations.isNotEmpty()) transformations(transformations)
            listener(onSuccess = { _, _ -> success() }, onError = { _, _ -> failure() })
        }
    }
    fun preview(context: Context, raw: String, title: String) {
        val url = OpenVelaApi.image(raw)
        if (url == null) { android.widget.Toast.makeText(context, "图片来源不受支持", android.widget.Toast.LENGTH_SHORT).show(); return }
        com.example.aisia.ui.common.PhotoPreview.show(context, url, title, imageLoader = loader)
    }
}
