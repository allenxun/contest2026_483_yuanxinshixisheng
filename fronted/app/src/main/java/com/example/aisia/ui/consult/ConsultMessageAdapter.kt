package com.example.aisia.ui.consult

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.example.aisia.R

/**
 * 咨询消息列表适配器
 * 数据格式：Triple(name, preview, time)
 */
class ConsultMessageAdapter : RecyclerView.Adapter<ConsultMessageAdapter.VH>() {

    private var data: List<Triple<String, String, String>> = emptyList()

    fun submit(list: List<Triple<String, String, String>>) {
        data = list
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val v = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_consult_message, parent, false)
        return VH(v)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        val item = data[position]
        holder.tvName.text = item.first
        holder.tvPreview.text = item.second
        holder.tvTime.text = item.third
    }

    override fun getItemCount(): Int = data.size

    class VH(view: View) : RecyclerView.ViewHolder(view) {
        val tvName: TextView = view.findViewById(R.id.tvConsultName)
        val tvPreview: TextView = view.findViewById(R.id.tvConsultPreview)
        val tvTime: TextView = view.findViewById(R.id.tvConsultTime)
    }
}
