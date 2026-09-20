package com.example.aisia.ui.devicehistory

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.example.aisia.R

/**
 * 历史设备方案列表适配器（模仿小程序 historyPlan 列表项）
 *
 * 三列布局：
 *   第一列（使用人）：头像占位 + "使用人" + "最近使用时间：xxx"
 *   第二列（使用的方案）：device_name 或 "使用的方案"
 *   第三列（时长）：duration 或 "00:00"
 */
class HistoryPlanAdapter(
    private val items: MutableList<HistoryPlanItem> = mutableListOf()
) : RecyclerView.Adapter<HistoryPlanAdapter.VH>() {

    var onItemClick: ((HistoryPlanItem) -> Unit)? = null

    class VH(itemView: View) : RecyclerView.ViewHolder(itemView) {
        val tvName: TextView = itemView.findViewById(R.id.tvName)
        val tvTime: TextView = itemView.findViewById(R.id.tvTime)
        val tvPlan: TextView = itemView.findViewById(R.id.tvPlan)
        val tvDuration: TextView = itemView.findViewById(R.id.tvDuration)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_history_plan, parent, false)
        return VH(view)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        val item = items[position]

        // 第一列：使用人（固定文本，与小程序一致）
        holder.tvName.text = "使用人"

        // 第一列：最近使用时间（与小程序 "最近使用时间：{{item.created_at || ''}}" 一致）
        holder.tvTime.text = "最近使用时间：${item.createdAt}"

        // 第二列：使用的方案（与小程序 "{{item.device_name || '使用的方案'}}" 一致）
        holder.tvPlan.text = item.deviceName.ifBlank { "使用的方案" }

        // 第三列：时长（与小程序 "{{item.duration || '00:00'}}" 一致）
        holder.tvDuration.text = item.duration.ifBlank { "00:00" }

        // 点击跳转到方案详情
        holder.itemView.setOnClickListener { onItemClick?.invoke(item) }
    }

    override fun getItemCount(): Int = items.size

    fun setItems(list: List<HistoryPlanItem>) {
        items.clear()
        items.addAll(list)
        notifyDataSetChanged()
    }
}
