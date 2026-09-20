package com.example.aisia.ui.devicehistory

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import coil.load
import com.example.aisia.R

/**
 * 设备连接历史列表适配器
 */
class DeviceHistoryAdapter(
    private val items: MutableList<DeviceHistoryItem> = mutableListOf()
) : RecyclerView.Adapter<DeviceHistoryAdapter.VH>() {

    var onItemClick: ((DeviceHistoryItem) -> Unit)? = null

    companion object {
        /** 设备卡片固定图片（与小程序一致） */
        const val DEVICE_IMG_URL = "https://eveaisia.com/face/img/dev_img.png"
    }

    class VH(itemView: View) : RecyclerView.ViewHolder(itemView) {
        val ivDevice: ImageView = itemView.findViewById(R.id.ivDevice)
        val tvName: TextView = itemView.findViewById(R.id.tvName)
        val tvTime: TextView = itemView.findViewById(R.id.tvTime)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_device_history, parent, false)
        return VH(view)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        val item = items[position]
        // 设备名称 + 状态
        holder.tvName.text = "${item.deviceName}(${item.statusText})"
        // 最近连接时间
        holder.tvTime.text = "最近连接时间：${item.lastConnectTime}"
        // 设备图片
        holder.ivDevice.load(DEVICE_IMG_URL) {
            placeholder(R.drawable.ic_device)
            error(R.drawable.ic_device)
        }
        holder.itemView.setOnClickListener { onItemClick?.invoke(item) }
    }

    override fun getItemCount(): Int = items.size

    fun setItems(list: List<DeviceHistoryItem>) {
        items.clear()
        items.addAll(list)
        notifyDataSetChanged()
    }
}