package com.example.aisia.ui.skinhistory

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import coil.load
import coil.request.CachePolicy
import coil.size.Precision
import coil.transform.CircleCropTransformation
import com.example.aisia.R
import com.example.aisia.network.ApiConfig
import kotlin.math.roundToInt

/**
 * 测肤历史人物列表适配器
 */
class SkinPersonAdapter(
    private val items: MutableList<SkinPerson> = mutableListOf()
) : RecyclerView.Adapter<SkinPersonAdapter.VH>() {

    var onItemClick: ((SkinPerson) -> Unit)? = null

    class VH(itemView: View) : RecyclerView.ViewHolder(itemView) {
        val ivFace: ImageView = itemView.findViewById(R.id.ivFace)
        val tvName: TextView = itemView.findViewById(R.id.tvName)
        val tvTime: TextView = itemView.findViewById(R.id.tvTime)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_skin_person, parent, false)
        return VH(view)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        val item = items[position]
        holder.tvName.text = item.faceNickname
        holder.tvTime.text = item.createTime ?: ""

        val imageUrl = normalizeImageUrl(item.faceImageUrl)
        val cacheKey = imageUrl?.let { buildStableCacheKey(item.faceId, it) }
        val avatarSizePx = (50 * holder.itemView.resources.displayMetrics.density).roundToInt()

        holder.ivFace.load(imageUrl) {
            placeholder(R.drawable.ic_default_avatar)
            fallback(R.drawable.ic_default_avatar)
            error(R.drawable.ic_default_avatar)
            size(avatarSizePx)
            precision(Precision.INEXACT)
            memoryCachePolicy(CachePolicy.ENABLED)
            diskCachePolicy(CachePolicy.ENABLED)
            networkCachePolicy(CachePolicy.ENABLED)
            if (cacheKey != null) {
                // 预签名 URL 的查询参数会定期变化；使用稳定 key 才能复用同一张人脸图缓存。
                memoryCacheKey(cacheKey)
                diskCacheKey(cacheKey)
            }
            transformations(CircleCropTransformation())
        }
        holder.itemView.setOnClickListener { onItemClick?.invoke(item) }
    }

    private fun normalizeImageUrl(rawUrl: String?): String? {
        val value = rawUrl?.trim()
            ?.takeIf { it.isNotEmpty() && !it.equals("null", ignoreCase = true) }
            ?: return null

        return when {
            value.startsWith("https://", ignoreCase = true) ||
                value.startsWith("http://", ignoreCase = true) -> value
            value.startsWith("//") -> "https:$value"
            value.startsWith("/") -> ApiConfig.BASE_URL.trimEnd('/') + value
            else -> ApiConfig.BASE_URL.trimEnd('/') + "/" + value
        }
    }

    private fun buildStableCacheKey(faceId: String, imageUrl: String): String {
        // OSS 等预签名地址通常只改变 ? 后的签名；对象路径不变时应命中同一缓存。
        val stableSource = imageUrl.substringBefore('?').substringBefore('#')
        return "history-face:$faceId:$stableSource"
    }

    override fun getItemCount(): Int = items.size

    fun setItems(list: List<SkinPerson>) {
        items.clear()
        items.addAll(list)
        notifyDataSetChanged()
    }
}
