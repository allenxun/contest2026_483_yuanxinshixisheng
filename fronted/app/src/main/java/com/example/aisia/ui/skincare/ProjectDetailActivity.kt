package com.example.aisia.ui.skincare

import android.app.DatePickerDialog
import android.content.Intent
import android.os.Bundle
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.example.aisia.R
import com.example.aisia.ui.consult.OnlineConsultActivity
import java.util.Calendar

/**
 * 项目详情页
 * 展示项目信息、护理步骤、美容师选择、预约操作区
 */
class ProjectDetailActivity : AppCompatActivity() {

    private var selectedDoctorId: Int = R.id.doctor1

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_project_detail)

        // 返回按钮
        findViewById<android.view.View>(R.id.btnBack).setOnClickListener { finish() }

        // 默认选中第一个美容师
        highlightDoctor(selectedDoctorId)

        val doctorIds = listOf(R.id.doctor1, R.id.doctor2, R.id.doctor3)
        for (id in doctorIds) {
            findViewById<LinearLayout>(id).setOnClickListener {
                selectedDoctorId = id
                highlightDoctor(id)
            }
        }

        // 门店选择
        val tvStore = findViewById<TextView>(R.id.tvStoreSelect)
        val stores = listOf("远想想法旗舰店", "远想想法天河店", "远想想法珠江店")
        tvStore.setOnClickListener {
            showSingleChoiceDialog("选择门店", stores) { selected ->
                tvStore.text = selected
                tvStore.setTextColor(getColor(R.color.text_primary))
            }
        }

        // 日期选择
        val tvDate = findViewById<TextView>(R.id.tvDateSelect)
        tvDate.setOnClickListener {
            val cal = Calendar.getInstance()
            DatePickerDialog(
                this,
                { _, year, month, day ->
                    tvDate.text = String.format("%d-%02d-%02d", year, month + 1, day)
                    tvDate.setTextColor(getColor(R.color.text_primary))
                },
                cal.get(Calendar.YEAR),
                cal.get(Calendar.MONTH),
                cal.get(Calendar.DAY_OF_MONTH)
            ).show()
        }

        // 时段选择
        val tvTimeSlot = findViewById<TextView>(R.id.tvTimeSlot)
        val timeSlots = listOf(
            "09:00-10:00", "10:00-11:00", "11:00-12:00",
            "14:00-15:00", "15:00-16:00", "16:00-17:00"
        )
        tvTimeSlot.setOnClickListener {
            showSingleChoiceDialog("选择时段", timeSlots) { selected ->
                tvTimeSlot.text = selected
            }
        }

        // 立即预约 -> 跳转到在线咨询
        findViewById<android.view.View>(R.id.btnBookNow).setOnClickListener {
            startActivity(Intent(this, OnlineConsultActivity::class.java))
        }
    }

    private fun highlightDoctor(selectedId: Int) {
        val ids = listOf(R.id.doctor1, R.id.doctor2, R.id.doctor3)
        for (id in ids) {
            val layout = findViewById<LinearLayout>(id)
            if (id == selectedId) {
                layout.setBackgroundResource(R.drawable.edit_text_bg)
                layout.backgroundTintList = android.content.res.ColorStateList.valueOf(0xFFE8F0FB.toInt())
            } else {
                layout.setBackgroundResource(R.drawable.edit_text_bg)
                layout.backgroundTintList = android.content.res.ColorStateList.valueOf(0xFFFFFFFF.toInt())
            }
        }
    }

    private fun showSingleChoiceDialog(title: String, items: List<String>, onSelected: (String) -> Unit) {
        val arr = items.toTypedArray()
        androidx.appcompat.app.AlertDialog.Builder(this)
            .setTitle(title)
            .setItems(arr) { _, which -> onSelected(arr[which]) }
            .show()
    }
}