package com.example.aisia.ui.model3d

import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.example.aisia.R
import com.example.aisia.network.HttpHelper
import com.example.aisia.ui.skinhistory.SkinPerson
import com.example.aisia.ui.skinhistory.SkinPersonAdapter
import com.example.aisia.ui.skintest.SmartSkinTestActivity
import org.json.JSONObject

/**
 * 3D模型列表页面
 * - 内容和接口暂时与测肤历史列表（SkinHistoryActivity）完全一致
 * - 点击列表卡片跳转的页面也与测肤历史一致（ReportListActivity）
 */
class Model3DListActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "Model3DListActivity"
    }

    private lateinit var rv: RecyclerView
    private lateinit var tvEmpty: TextView
    private val adapter = SkinPersonAdapter()

    private var id: String? = null
    private var deviceId: String? = null
    private var deviceName: String? = null
    private var deviceType: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_model_3d_list)

        id = intent.getStringExtra("id")
        deviceId = intent.getStringExtra("deviceId")
        deviceName = intent.getStringExtra("deviceName")
        deviceType = intent.getStringExtra("deviceType")
        Log.d(TAG, "onCreate: id=$id, deviceId=$deviceId, deviceName=$deviceName, deviceType=$deviceType")

        findViewById<View>(R.id.btnBack).setOnClickListener { finish() }

        rv = findViewById(R.id.rvPersons)
        tvEmpty = findViewById(R.id.tvEmpty)
        rv.layoutManager = LinearLayoutManager(this)
        rv.adapter = adapter

        // 点击列表项跳转到3D模型报告列表页面
        adapter.onItemClick = { person ->
            val intent = Intent(this, Model3DReportListActivity::class.java).apply {
                putExtra("faceId", person.faceId)
                putExtra("faceNickname", person.faceNickname)
                if (!id.isNullOrEmpty()) {
                    putExtra("device_id", id)
                }
                if (!deviceId.isNullOrEmpty()) {
                    putExtra("deviceId", deviceId)
                }
            }
            startActivity(intent)
        }

        // 点击添加按钮跳转到测肤页面（type=3d）
        findViewById<View>(R.id.btnAdd).setOnClickListener {
            val intent = Intent(this, SmartSkinTestActivity::class.java).apply {
                putExtra("type", "3d")
                if (!id.isNullOrEmpty()) {
                    putExtra("id", id)
                }
                if (!deviceId.isNullOrEmpty()) {
                    putExtra("deviceId", deviceId)
                }
                putExtra("deviceName", deviceName)
                putExtra("deviceType", deviceType)
            }
            startActivity(intent)
        }

        if (!deviceId.isNullOrEmpty()) {
            loadPersonsByDevice(deviceId!!)
        } else {
            loadPersons()
        }
    }

    private fun loadPersonsByDevice(deviceId: String) {
        Log.d(TAG, "loadPersonsByDevice: deviceId=$deviceId")
        HttpHelper.get(
            path = "/api/3d/faces?deviceId=$deviceId",
            onSuccess = { resp ->
                Log.d(TAG, "loadPersonsByDevice success")
                val list = parseList(resp)
                Log.d(TAG, "loadPersonsByDevice parsed list size: ${list.size}")
                runOnUiThread { applyList(list) }
            },
            onFailure = { code, msg ->
                Log.e(TAG, "load persons by device failed: $code $msg")
                runOnUiThread { loadPersons() }
            }
        )
    }

    private fun loadPersons() {
        Log.d(TAG, "loadPersons: start loading...")
        HttpHelper.get(
            path = "/api/3d/faces",
            onSuccess = { resp ->
                Log.d(TAG, "loadPersons success")
                val list = parseList(resp)
                Log.d(TAG, "loadPersons parsed list size: ${list.size}")
                runOnUiThread { applyList(list) }
            },
            onFailure = { code, msg ->
                Log.e(TAG, "load persons failed: $code $msg")
                runOnUiThread { applyList(emptyList()) }
            }
        )
    }

    private fun parseList(resp: String): List<SkinPerson> {
        if (resp.isBlank()) return emptyList()
        return try {
            if (resp.trim().startsWith("[")) {
                val arr = org.json.JSONArray(resp)
                return parseArray(arr)
            }

            val root = JSONObject(resp)
            Log.d(TAG, "parseList root keys: ${root.keys().asSequence().toList()}")

            val items = root.optJSONArray("items")
                ?: root.optJSONArray("list")
                ?: root.optJSONArray("data")
                ?: root.optJSONObject("data")?.optJSONArray("items")
                ?: root.optJSONObject("data")?.optJSONArray("list")
                ?: root.optJSONObject("result")?.optJSONArray("items")
                ?: root.optJSONObject("result")?.optJSONArray("list")
                ?: return emptyList()

            Log.d(TAG, "parseList items length: ${items.length()}")
            parseArray(items)
        } catch (e: Exception) {
            Log.e(TAG, "parse list failed", e)
            emptyList()
        }
    }

    private fun parseArray(items: org.json.JSONArray): List<SkinPerson> {
        return (0 until items.length()).mapNotNull { i ->
            val obj = items.optJSONObject(i) ?: return@mapNotNull null
            SkinPerson(
                faceId = obj.optString("face_id").ifEmpty { obj.optString("id") },
                faceNickname = obj.optString("face_nickname").ifEmpty {
                    obj.optString("nickname").ifEmpty { obj.optString("name") }
                },
                recordCount = obj.optInt("record_count", 0),
                faceImageUrl = obj.optString("face_image_url").takeIf { it.isNotBlank() && it != "null" },
                createTime = obj.optString("create_time").takeIf { it.isNotBlank() && it != "null" }
            )
        }
    }

    private fun applyList(list: List<SkinPerson>) {
        adapter.setItems(list)
        tvEmpty.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
    }
}
