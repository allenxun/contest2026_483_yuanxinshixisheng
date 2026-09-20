package com.example.aisia.ui.skincare

import android.bluetooth.BluetoothDevice
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import coil.load
import com.example.aisia.R

class DeviceListAdapter(
    private val devices: MutableList<ScannedDevice>,
    private val onItemClick: (ScannedDevice) -> Unit
) : RecyclerView.Adapter<DeviceListAdapter.ViewHolder>() {

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val ivThumb: ImageView = view.findViewById(R.id.ivDeviceThumb)
        val tvName: TextView = view.findViewById(R.id.tvDeviceName)
        val tvRssi: TextView = view.findViewById(R.id.tvDeviceAddress)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_device, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val device = devices[position]
        holder.tvName.text = device.name

        // RSSI 信号描述（参考 JS：显示信号强度信息）
        holder.tvRssi.text = when {
            device.rssi >= -55 -> "信号强"
            device.rssi >= -75 -> "信号中"
            device.rssi > 0 -> ""
            else -> "信号弱"
        }

        // 设备缩略图
        holder.ivThumb.load("https://eveaisia.com/face/img/dev_img.png") {
            crossfade(true)
            placeholder(R.drawable.device_list_bg)
            error(R.drawable.device_list_bg)
        }

        holder.itemView.setOnClickListener {
            onItemClick(device)
        }
    }

    override fun getItemCount(): Int = devices.size

    fun addDevice(device: ScannedDevice) {
        if (devices.none { it.deviceId == device.deviceId }) {
            devices.add(device)
            notifyItemInserted(devices.size - 1)
        }
    }

    fun clear() {
        devices.clear()
        notifyDataSetChanged()
    }
}

/**
 * 扫描到的蓝牙设备信息（参考 JS：_addDeviceToList）
 */
data class ScannedDevice(
    val name: String,
    val deviceId: String,        // 蓝牙设备ID（MAC地址）
    val rssi: Int = 0,           // 信号强度
    val rawDevice: BluetoothDevice? = null
)