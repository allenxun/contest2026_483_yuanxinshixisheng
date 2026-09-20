package com.example.aisia.ui.skinhistory

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.example.aisia.R

/**
 * 测肤报告列表适配器
 */
class ReportAdapter(
    private val items: MutableList<Report> = mutableListOf()
) : RecyclerView.Adapter<ReportAdapter.VH>() {

    var onItemClick: ((Report) -> Unit)? = null

    class VH(itemView: View) : RecyclerView.ViewHolder(itemView) {
        val tvTitle: TextView = itemView.findViewById(R.id.tvTitle)
        val tvTime: TextView = itemView.findViewById(R.id.tvTime)
        val tvScore: TextView = itemView.findViewById(R.id.tvScore)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_report, parent, false)
        return VH(view)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        val item = items[position]
        
        // 设置标题
        holder.tvTitle.text = "测肤结果"
        
        // 设置测肤时间
        holder.tvTime.text = "测肤时间：${item.createdAt ?: ""}"
        
        // 设置得分值（参考小程序显示实际得分）
        val score = item.skinScore
        holder.tvScore.text = if (score != null && score > 0) "${score}分" else "得分"
        
        holder.itemView.setOnClickListener { onItemClick?.invoke(item) }
    }

    override fun getItemCount(): Int = items.size

    fun setItems(list: List<Report>) {
        items.clear()
        items.addAll(list)
        notifyDataSetChanged()
    }
    
    fun getItems(): List<Report> = items.toList()

    fun appendItems(list: List<Report>) {
        val startPos = items.size
        items.addAll(list)
        notifyItemRangeInserted(startPos, list.size)
    }
}