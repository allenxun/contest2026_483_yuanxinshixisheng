package com.example.aisia.ui.home

import android.view.LayoutInflater
import android.view.ViewGroup
import android.widget.ImageView
import androidx.recyclerview.widget.RecyclerView
import coil.load
import com.example.aisia.R

class BannerAdapter(
    private val data: List<String>,
    private val onItemClick: (position: Int) -> Unit = {}
) : RecyclerView.Adapter<BannerAdapter.BannerVH>() {

    class BannerVH(view: android.view.View) : RecyclerView.ViewHolder(view) {
        val image: ImageView = view.findViewById(R.id.bannerImage)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): BannerVH {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_banner, parent, false)
        return BannerVH(view)
    }

    override fun onBindViewHolder(holder: BannerVH, position: Int) {
        holder.image.load(data[position]) {
            crossfade(true)
            placeholder(R.drawable.banner_1)
            error(R.drawable.banner_1)
        }
        holder.itemView.setOnClickListener { onItemClick(position) }
    }

    override fun getItemCount(): Int = data.size
}
