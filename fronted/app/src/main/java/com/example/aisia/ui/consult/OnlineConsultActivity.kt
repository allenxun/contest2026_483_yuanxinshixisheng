package com.example.aisia.ui.consult

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.example.aisia.R
import com.google.android.material.tabs.TabLayout

class OnlineConsultActivity : AppCompatActivity() {

    private val adapter = ConsultMessageAdapter()

    // type: 0 = 美容师消息   1 = 客服消息
    private val names    = listOf("张美容师", "客服小李", "李美容师", "客服小王", "王美容师", "客服小李")
    private val previews = listOf(
        "您好，您的皮肤检测报告已生成，请查看。",
        "您的预约已确认，请按时到店。",
        "建议下次护理时间：本周五下午。",
        "您好，请问有什么可以帮助您的？",
        "光子嫩肤术后24小时内避免使用化妆品。",
        "您的优惠券已到账，请在30天内使用。"
    )
    private val times = listOf("10:32", "09:15", "昨天", "昨天", "06/20", "06/18")
    private val types = listOf(0, 1, 0, 1, 0, 1)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_online_consult)

        val rv = findViewById<RecyclerView>(R.id.rvConsultMessages)
        val tvEmpty = findViewById<TextView>(R.id.tvConsultEmpty)
        val tabLayout = findViewById<TabLayout>(R.id.tabConsult)

        rv.layoutManager = LinearLayoutManager(this)
        rv.adapter = adapter

        tabLayout.addTab(tabLayout.newTab().setText("全部"))
        tabLayout.addTab(tabLayout.newTab().setText("美容师问诊"))
        tabLayout.addTab(tabLayout.newTab().setText("客服咨询"))

        tabLayout.addOnTabSelectedListener(object : TabLayout.OnTabSelectedListener {
            override fun onTabSelected(tab: TabLayout.Tab?) {
                applyFilter(tab?.position ?: 0)
            }
            override fun onTabUnselected(tab: TabLayout.Tab?) {}
            override fun onTabReselected(tab: TabLayout.Tab?) {}
        })

        applyFilter(0)

        adapter.registerAdapterDataObserver(object : RecyclerView.AdapterDataObserver() {
            override fun onChanged() {
                val isEmpty = adapter.itemCount == 0
                tvEmpty.visibility = if (isEmpty) View.VISIBLE else View.GONE
                rv.visibility      = if (isEmpty) View.GONE    else View.VISIBLE
            }
        })
    }

    fun onBackClick(view: android.view.View) {
        finish()
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }

    private fun applyFilter(tabPos: Int) {
        val targetType = when (tabPos) {
            1 -> 0
            2 -> 1
            else -> -1
        }
        val filtered = if (targetType == -1) {
            names.indices.map { Triple(names[it], previews[it], times[it]) }
        } else {
            names.indices
                .filter { types[it] == targetType }
                .map { Triple(names[it], previews[it], times[it]) }
        }
        adapter.submit(filtered)
    }

    companion object {
        fun start(ctx: android.content.Context) {
            ctx.startActivity(Intent(ctx, OnlineConsultActivity::class.java))
        }
    }
}