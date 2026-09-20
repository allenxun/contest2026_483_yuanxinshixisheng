package com.example.aisia.ui.model3d

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.example.aisia.R
import com.example.aisia.ui.skinhistory.Report

/**
 * 3D模型报告列表适配器
 * - 标题显示"3D模型结果"
 * - 时间显示"检测时间：xxx"
 * - 不显示得分
 */
class Report3DAdapter(
    private val items: MutableList<Report> = mutableListOf()
) : RecyclerView.Adapter<Report3DAdapter.VH>() {

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
        
        // 设置标题为"3D模型结果"
        holder.tvTitle.text = "3D模型结果"
        
        // 设置检测时间
        holder.tvTime.text = "检测时间：${item.createdAt ?: ""}"
        
        // 隐藏得分标签
        holder.tvScore.visibility = View.GONE
        
        holder.itemView.setOnClickListener { onItemClick?.invoke(item) }
    }

    override fun getItemCount(): Int = items.size

    fun setItems(list: List<Report>) {
        items.clear()
        items.addAll(list)
        notifyDataSetChanged()
    }
    
    fun appendItems(list: List<Report>) {
        val startPos = items.size
        items.addAll(list)
        notifyItemRangeInserted(startPos, list.size)
    }
}