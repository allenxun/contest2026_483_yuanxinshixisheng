package com.example.aisia.ui.device

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.example.aisia.R
import com.example.aisia.privacy.PrivacyManager

class DeviceConnectionActivity : AppCompatActivity() {

    private lateinit var btnSearch: View
    private lateinit var tvStatus: TextView
    private lateinit var rvDevices: RecyclerView

    private var bluetoothAdapter: BluetoothAdapter? = null
    private var bleScanner: BluetoothLeScanner? = null
    private var isScanning = false
    private var bluetoothGatt: BluetoothGatt? = null

    private val deviceList = mutableListOf<BluetoothDevice>()
    private val deviceAdapter = DeviceAdapter(deviceList) { device -> connectDevice(device) }

    // 蓝牙开启请求
    private val enableBtLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            startBleScan()
        } else {
            Toast.makeText(this, "蓝牙开启失败，请手动开启蓝牙", Toast.LENGTH_SHORT).show()
        }
    }

    // 权限请求
    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val allGranted = permissions.values.all { it }
        if (allGranted) {
            initBluetooth()
        } else {
            Toast.makeText(this, "需要蓝牙权限才能搜索设备", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_device_connection)

        btnSearch = findViewById(R.id.btnSearchDevice)
        tvStatus = findViewById(R.id.tvSearchStatus)
        rvDevices = findViewById(R.id.rvDevices)

        rvDevices.layoutManager = LinearLayoutManager(this)
        rvDevices.adapter = deviceAdapter

        findViewById<View>(R.id.btnBack).setOnClickListener { finish() }

        btnSearch.setOnClickListener {
            checkPermissionsAndInit()
        }
    }

    private fun checkPermissionsAndInit() {
        // 合规要求：用户同意隐私政策后才能申请蓝牙/位置权限
        PrivacyManager.ensureAgreed(this) {
            val permissions = mutableListOf<String>()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                permissions.add(Manifest.permission.BLUETOOTH_SCAN)
                permissions.add(Manifest.permission.BLUETOOTH_CONNECT)
            } else {
                permissions.add(Manifest.permission.ACCESS_FINE_LOCATION)
            }

            val notGranted = permissions.filter {
                ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
            }

            if (notGranted.isEmpty()) {
                initBluetooth()
            } else {
                permissionLauncher.launch(notGranted.toTypedArray())
            }
        }
    }

    @SuppressLint("MissingPermission")
    private fun initBluetooth() {
        val bluetoothManager = getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
        bluetoothAdapter = bluetoothManager?.adapter

        if (bluetoothAdapter == null) {
            Toast.makeText(this, "该设备不支持蓝牙", Toast.LENGTH_SHORT).show()
            return
        }

        if (bluetoothAdapter?.isEnabled != true) {
            val enableBtIntent = Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE)
            enableBtLauncher.launch(enableBtIntent)
            return
        }

        startBleScan()
    }

    @SuppressLint("MissingPermission")
    private fun startBleScan() {
        if (isScanning) return

        bleScanner = bluetoothAdapter?.bluetoothLeScanner
        if (bleScanner == null) {
            Toast.makeText(this, "蓝牙初始化失败，无法搜索设备", Toast.LENGTH_SHORT).show()
            return
        }

        deviceList.clear()
        deviceAdapter.notifyDataSetChanged()
        isScanning = true

        tvStatus.text = "正在搜索设备..."
        tvStatus.visibility = View.VISIBLE

        bleScanner?.startScan(scanCallback)
    }

    @SuppressLint("MissingPermission")
    private fun stopBleScan() {
        if (isScanning) {
            bleScanner?.stopScan(scanCallback)
            isScanning = false
        }
    }

    private val scanCallback = object : ScanCallback() {
        @SuppressLint("MissingPermission")
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val device = result.device
            val deviceName = device.name ?: return

            // 只显示名称含 "EVE AISIA" 的设备
            if (!deviceName.contains("EVE AISIA", ignoreCase = true)) return

            // 避免重复添加
            if (deviceList.any { it.address == device.address }) return

            deviceList.add(device)
            runOnUiThread {
                deviceAdapter.notifyItemInserted(deviceList.size - 1)
                tvStatus.text = "已发现 ${deviceList.size} 个设备"
            }
        }

        override fun onScanFailed(errorCode: Int) {
            runOnUiThread {
                isScanning = false
                tvStatus.text = "搜索失败，请重试"
                Toast.makeText(
                    this@DeviceConnectionActivity,
                    "蓝牙搜索失败(错误码: $errorCode)",
                    Toast.LENGTH_SHORT
                ).show()
            }
        }
    }

    @SuppressLint("MissingPermission")
    private fun connectDevice(device: BluetoothDevice) {
        stopBleScan()
        tvStatus.text = "正在连接 ${device.name}..."

        bluetoothGatt = device.connectGatt(this, false, object : BluetoothGattCallback() {
            override fun onConnectionStateChange(gatt: BluetoothGatt?, status: Int, newState: Int) {
                runOnUiThread {
                    if (newState == BluetoothProfile.STATE_CONNECTED) {
                        Toast.makeText(
                            this@DeviceConnectionActivity,
                            "连接设备成功",
                            Toast.LENGTH_SHORT
                        ).show()
                        tvStatus.text = "已连接: ${device.name}"
                    } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                        Toast.makeText(
                            this@DeviceConnectionActivity,
                            "设备连接断开",
                            Toast.LENGTH_SHORT
                        ).show()
                        tvStatus.text = "连接已断开"
                    }
                }
            }
        })
    }

    @SuppressLint("MissingPermission")
    override fun onDestroy() {
        super.onDestroy()
        stopBleScan()
        bluetoothGatt?.close()
        bluetoothGatt = null
    }

    // ===== 设备列表 Adapter =====
    private class DeviceAdapter(
        private val devices: List<BluetoothDevice>,
        private val onItemClick: (BluetoothDevice) -> Unit
    ) : RecyclerView.Adapter<DeviceAdapter.ViewHolder>() {

        class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            val tvName: TextView = view.findViewById(R.id.tvDeviceName)
            val tvId: TextView = view.findViewById(R.id.tvDeviceAddress)
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
            val view = LayoutInflater.from(parent.context)
                .inflate(R.layout.item_device, parent, false)
            return ViewHolder(view)
        }

        @SuppressLint("MissingPermission")
        override fun onBindViewHolder(holder: ViewHolder, position: Int) {
            val device = devices[position]
            holder.tvName.text = device.name ?: "未知设备"
            holder.tvId.text = device.address
            holder.itemView.setOnClickListener { onItemClick(device) }
        }

        override fun getItemCount() = devices.size
    }
}
