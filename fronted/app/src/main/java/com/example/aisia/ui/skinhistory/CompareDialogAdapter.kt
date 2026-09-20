package com.example.aisia.ui.skinhistory

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.CheckBox
import android.widget.TextView
import android.widget.Toast
import androidx.recyclerview.widget.RecyclerView
import com.example.aisia.R

/**
 * 历史对比弹窗列表适配器
 * - 仅维护选中状态（最多 2 条），不再自动跳转
 * - 选中数量变化时通过 onSelectionChanged 回调通知外部（用于更新底部"对比"按钮状态）
 */
class CompareDialogAdapter(
    private val items: List<Report>,
    private val selectedIds: MutableSet<String>,
    private val onSelectionChanged: ((Int) -> Unit)? = null
) : RecyclerView.Adapter<CompareDialogAdapter.VH>() {

    class VH(itemView: View) : RecyclerView.ViewHolder(itemView) {
        val cbSelect: CheckBox = itemView.findViewById(R.id.cbSelect)
        val tvTime: TextView = itemView.findViewById(R.id.tvCompareTime)
        val tvScore: TextView = itemView.findViewById(R.id.tvCompareScore)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_report_compare, parent, false)
        return VH(view)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        val item = items[position]
        holder.tvTime.text = item.createdAt ?: ""
        val score = item.skinScore
        holder.tvScore.text = if (score != null && score > 0) "${score}分" else "暂无评分"
        holder.cbSelect.isChecked = selectedIds.contains(item.reportId)

        holder.itemView.setOnClickListener {
            val pos = holder.bindingAdapterPosition
            if (pos == RecyclerView.NO_POSITION) return@setOnClickListener
            val currentId = items[pos].reportId

            if (selectedIds.contains(currentId)) {
                selectedIds.remove(currentId)
            } else {
                if (selectedIds.size >= 2) {
                    Toast.makeText(
                        holder.itemView.context,
                        "只能选择两条数据进行对比",
                        Toast.LENGTH_SHORT
                    ).show()
                    return@setOnClickListener
                }
                selectedIds.add(currentId)
            }

            // 手动更新所有可见子 View 的 CheckBox，不调用 notifyDataSetChanged
            val rv = holder.itemView.parent as? RecyclerView
            if (rv != null) {
                for (i in 0 until rv.childCount) {
                    val child = rv.getChildAt(i)
                    val vh = rv.getChildViewHolder(child) as? VH
                    val childPos = vh?.bindingAdapterPosition ?: RecyclerView.NO_POSITION
                    if (vh != null && childPos != RecyclerView.NO_POSITION && childPos < items.size) {
                        vh.cbSelect.isChecked = selectedIds.contains(items[childPos].reportId)
                    }
                }
            }

            // 通知选中数量变化，由外部决定"对比"按钮是否可点击
            onSelectionChanged?.invoke(selectedIds.size)
        }
    }

    override fun getItemCount(): Int = items.size
}