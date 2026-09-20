package com.example.aisia.ui.home

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.View
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import androidx.viewpager2.widget.ViewPager2
import coil.load
import com.example.aisia.MainActivity
import com.example.aisia.R
import com.example.aisia.network.HttpHelper
import com.example.aisia.ui.skintest.SkinListActivity
import com.google.android.material.bottomsheet.BottomSheetBehavior
import com.google.android.material.card.MaterialCardView
import org.json.JSONObject

class HomeFragment : Fragment(R.layout.fragment_home) {

    companion object {
        private const val TAG = "HomeFragment"
    }

    // 轮播图网络图片（暂时隐藏slider3、slider4）
    private val banners = listOf(
        "https://aisia-common2.oss-cn-shenzhen.aliyuncs.com/face/slider1.png",
        "https://aisia-common2.oss-cn-shenzhen.aliyuncs.com/face/slider2.png"
    )

    // 卡片背景图（与小程序一致）
    private val skinTestBgUrl = "https://eveaisia.com/face/img/index_scan.png"
    private val deviceBgUrl = "https://eveaisia.com/face/img/index_device.png"
    private val deviceImgUrl = "https://eveaisia.com/face/img/dev_img.png"

    private lateinit var bannerPager: ViewPager2
    private lateinit var indicators: LinearLayout
    private lateinit var sheet: View

    // 功能卡片（无数据时显示）
    private lateinit var cardSkinTestFunc: MaterialCardView
    private lateinit var cardDeviceFunc: MaterialCardView
    private lateinit var imgSkinTestFunc: ImageView
    private lateinit var imgDeviceFunc: ImageView

    // 数据卡片（有数据时显示）
    private lateinit var cardSkinTestData: MaterialCardView
    private lateinit var cardDeviceData: MaterialCardView
    private lateinit var tvSkinType: TextView
    private lateinit var tvSkinScore: TextView
    private lateinit var btnRescan: TextView
    private lateinit var imgDeviceData: ImageView
    private lateinit var tvDeviceName: TextView
    private lateinit var tvDeviceTime: TextView
    private lateinit var btnReconnect: TextView

    // 数据
    private var skinList: List<SkinPersonData> = emptyList()
    private var lastDevice: DeviceData? = null

    private val autoScrollHandler = Handler(Looper.getMainLooper())
    private val autoScrollIntervalMs = 3000L
    private val autoScrollRunnable = object : Runnable {
        override fun run() {
            if (!isAdded || isHidden || view == null || !::bannerPager.isInitialized || banners.isEmpty()) return
            val next = (bannerPager.currentItem + 1) % banners.size
            bannerPager.setCurrentItem(next, true)
            autoScrollHandler.postDelayed(this, autoScrollIntervalMs)
        }
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        bannerPager = view.findViewById(R.id.bannerPager)
        indicators = view.findViewById(R.id.indicators)
        sheet = view.findViewById(R.id.bottomSheet)

        // 功能卡片
        cardSkinTestFunc = view.findViewById(R.id.cardSkinTestFunc)
        cardDeviceFunc = view.findViewById(R.id.cardDeviceFunc)
        imgSkinTestFunc = view.findViewById(R.id.imgSkinTestFunc)
        imgDeviceFunc = view.findViewById(R.id.imgDeviceFunc)

        // 数据卡片
        cardSkinTestData = view.findViewById(R.id.cardSkinTestData)
        cardDeviceData = view.findViewById(R.id.cardDeviceData)
        tvSkinType = view.findViewById(R.id.tvSkinType)
        tvSkinScore = view.findViewById(R.id.tvSkinScore)
        btnRescan = view.findViewById(R.id.btnRescan)
        imgDeviceData = view.findViewById(R.id.imgDeviceData)
        tvDeviceName = view.findViewById(R.id.tvDeviceName)
        tvDeviceTime = view.findViewById(R.id.tvDeviceTime)
        btnReconnect = view.findViewById(R.id.btnReconnect)

        setupCarousel()
        setupCardImages()
        setupBottomSheet()
        setupCardClicks()

        // onResume performs the initial load.
    }

    private fun setupCarousel() {
        bannerPager.adapter = BannerAdapter(banners) { position ->
            if (isAdded && position in banners.indices) com.example.aisia.ui.common.PhotoPreview.show(requireActivity(), banners[position], "图片预览")
        }
        bannerPager.offscreenPageLimit = 1
        buildIndicators(banners.size)
        updateIndicators(0)

        bannerPager.registerOnPageChangeCallback(object : ViewPager2.OnPageChangeCallback() {
            override fun onPageSelected(position: Int) {
                updateIndicators(position)
            }

            override fun onPageScrollStateChanged(state: Int) {
                when (state) {
                    ViewPager2.SCROLL_STATE_DRAGGING -> stopAutoScroll()
                    ViewPager2.SCROLL_STATE_IDLE -> startAutoScroll()
                }
            }
        })
    }

    /** 加载卡片背景图（与小程序一致） */
    private fun setupCardImages() {
        imgSkinTestFunc.load(skinTestBgUrl) {
            crossfade(true)
        }
        imgDeviceFunc.load(deviceBgUrl) {
            crossfade(true)
        }
        // 设备数据卡片的图片
        imgDeviceData.load(deviceImgUrl) {
            crossfade(true)
        }
    }

    private fun setupBottomSheet() {
        val behavior = BottomSheetBehavior.from(sheet)
        behavior.isHideable = false
        behavior.isDraggable = true
        behavior.state = BottomSheetBehavior.STATE_EXPANDED

        sheet.post {
            applyTransitionAlpha(1f)
        }

        behavior.addBottomSheetCallback(object : BottomSheetBehavior.BottomSheetCallback() {
            override fun onStateChanged(bottomSheet: View, newState: Int) = Unit

            override fun onSlide(bottomSheet: View, slideOffset: Float) {
                applyTransitionAlpha(slideOffset)
            }
        })
    }

    /**
     * 根据 BottomSheet 的 slideOffset 同步调节 UI 透明度
     */
    private fun applyTransitionAlpha(slideOffset: Float) {
        val ratio = slideOffset.coerceIn(0f, 1f)

        // 卡片透明度
        if (::cardSkinTestFunc.isInitialized) cardSkinTestFunc.alpha = ratio
        if (::cardDeviceFunc.isInitialized) cardDeviceFunc.alpha = ratio
        if (::cardSkinTestData.isInitialized) cardSkinTestData.alpha = ratio
        if (::cardDeviceData.isInitialized) cardDeviceData.alpha = ratio
        // 指示点透明度
        if (::indicators.isInitialized) indicators.alpha = ratio
    }

    private fun setupCardClicks() {
        // 功能卡片点击
        cardSkinTestFunc.setOnClickListener {
            navigateToSkinTest()
        }
        cardDeviceFunc.setOnClickListener {
            navigateToDevice()
        }

        // 数据卡片点击
        cardSkinTestData.setOnClickListener {
            navigateToSkinTest()
        }
        cardDeviceData.setOnClickListener {
            navigateToDevice()
        }

        // 按钮点击
        btnRescan.setOnClickListener {
            navigateToSkinTest()
        }
        btnReconnect.setOnClickListener {
            navigateToDevice()
        }
    }

    private fun navigateToSkinTest() {
        val intent = Intent(requireContext(), SkinListActivity::class.java)
        startActivity(intent)
    }

    private fun navigateToDevice() {
        // 点击"连接设备"跳转到养肤页面（底部导航的养肤 tab）
        (activity as? MainActivity)?.let { mainActivity ->
            val bottomNav = mainActivity.findViewById<com.google.android.material.bottomnavigation.BottomNavigationView>(R.id.bottomNav)
            bottomNav.selectedItemId = R.id.nav_skincare
        }
    }

    /** 构建长条形指示点（与小程序一致） */
    private fun buildIndicators(count: Int) {
        indicators.removeAllViews()
        val ctx = requireContext()
        val widthNormal = (10 * resources.displayMetrics.density).toInt()
        val widthActive = (14 * resources.displayMetrics.density).toInt()
        val height = (4 * resources.displayMetrics.density).toInt()
        val margin = (4 * resources.displayMetrics.density).toInt()
        repeat(count) {
            val dot = View(ctx)
            val lp = LinearLayout.LayoutParams(widthNormal, height)
            lp.marginStart = margin
            lp.marginEnd = margin
            dot.layoutParams = lp
            indicators.addView(dot)
        }
    }

    private fun updateIndicators(selected: Int) {
        val widthNormal = (10 * resources.displayMetrics.density).toInt()
        val widthActive = (14 * resources.displayMetrics.density).toInt()
        val height = (4 * resources.displayMetrics.density).toInt()
        for (i in 0 until indicators.childCount) {
            val child = indicators.getChildAt(i)
            val lp = child.layoutParams as LinearLayout.LayoutParams
            lp.width = if (i == selected) widthActive else widthNormal
            lp.height = height
            child.layoutParams = lp
            val resId = if (i == selected) R.drawable.indicator_selected
            else R.drawable.indicator_unselected
            child.background = ContextCompat.getDrawable(requireContext(), resId)
        }
    }

    private fun startAutoScroll() {
        autoScrollHandler.removeCallbacks(autoScrollRunnable)
        if (isAdded && !isHidden && view != null && banners.size > 1) {
            autoScrollHandler.postDelayed(autoScrollRunnable, autoScrollIntervalMs)
        }
    }

    private fun stopAutoScroll() {
        autoScrollHandler.removeCallbacks(autoScrollRunnable)
    }

    override fun onResume() {
        super.onResume()
        startAutoScroll()
        // 每次回到首页时刷新数据
        loadData()
    }

    override fun onHiddenChanged(hidden: Boolean) {
        super.onHiddenChanged(hidden)
        if (hidden) stopAutoScroll() else if (isResumed) startAutoScroll()
    }
    override fun onDestroyView() {
        dataEpoch++
        skinRequestInFlight = false; deviceRequestInFlight = false
        stopAutoScroll()
        super.onDestroyView()
    }
    override fun onPause() {
        super.onPause()
        stopAutoScroll()
    }

    // ================== 数据加载 ==================

    private fun loadData() {
        loadSkinPersonList()
        loadDeviceList()
    }

    /**
     * 加载测肤人列表
     * GET /api/self-research-face/faces
     */
    private var skinRequestInFlight = false
    private var deviceRequestInFlight = false
    private var dataEpoch = 0

    private fun loadSkinPersonList() {
        if (skinRequestInFlight) return
        skinRequestInFlight = true
        val epoch = dataEpoch
        HttpHelper.get(
            path = "/api/self-research-face/faces",
            onSuccess = { resp ->
                Log.d(TAG, "loadSkinPersonList success")
                val list = parseSkinPersonList(resp)
                activity?.runOnUiThread {
                    if (epoch != dataEpoch || view == null) return@runOnUiThread
                    skinRequestInFlight = false
                    skinList = list
                    updateSkinTestCard()
                }
            },
            onFailure = { code, msg ->
                Log.e(TAG, "loadSkinPersonList failed: $code $msg")
                activity?.runOnUiThread {
                    if (epoch != dataEpoch || view == null) return@runOnUiThread
                    skinRequestInFlight = false
                    skinList = emptyList()
                    updateSkinTestCard()
                }
            }
        )
    }

    /**
     * 加载设备列表
     * GET /api/my-device?page=1&page_size=99
     */
    private fun loadDeviceList() {
        if (deviceRequestInFlight) return
        deviceRequestInFlight = true
        val epoch = dataEpoch
        HttpHelper.get(
            path = "/api/my-device?page=1&page_size=99",
            onSuccess = { resp ->
                Log.d(TAG, "loadDeviceList success")
                val device = parseDeviceData(resp)
                activity?.runOnUiThread {
                    if (epoch != dataEpoch || view == null) return@runOnUiThread
                    deviceRequestInFlight = false
                    lastDevice = device
                    updateDeviceCard()
                }
            },
            onFailure = { code, msg ->
                Log.e(TAG, "loadDeviceList failed: $code $msg")
                activity?.runOnUiThread {
                    if (epoch != dataEpoch || view == null) return@runOnUiThread
                    deviceRequestInFlight = false
                    lastDevice = null
                    updateDeviceCard()
                }
            }
        )
    }

    /**
     * 解析测肤人列表
     */
    private fun parseSkinPersonList(resp: String): List<SkinPersonData> {
        if (resp.isBlank()) return emptyList()
        return try {
            val root = JSONObject(resp)
            val items = root.optJSONArray("items")
                ?: root.optJSONArray("list")
                ?: root.optJSONArray("data")
                ?: root.optJSONObject("data")?.optJSONArray("items")
                ?: return emptyList()

            (0 until items.length()).mapNotNull { i ->
                val obj = items.optJSONObject(i) ?: return@mapNotNull null
                SkinPersonData(
                    skinType = obj.optString("skin_type").ifEmpty {
                        obj.optString("type").ifEmpty { "中性" }
                    },
                    skinScore = obj.optString("skin_score").ifEmpty {
                        obj.optString("score").ifEmpty { "86" }
                    }
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "parseSkinPersonList failed", e)
            emptyList()
        }
    }

    /**
     * 解析设备数据
     */
    private fun parseDeviceData(resp: String): DeviceData? {
        if (resp.isBlank()) return null
        return try {
            val root = JSONObject(resp)
            val items = root.optJSONArray("items")
                ?: root.optJSONArray("list")
                ?: root.optJSONArray("data")
                ?: root.optJSONObject("data")?.optJSONArray("items")

            if (items == null || items.length() == 0) return null

            val obj = items.getJSONObject(0)
            DeviceData(
                deviceName = obj.optString("device_name", "未知设备"),
                createdAt = obj.optString("created_at").ifEmpty {
                    obj.optString("create_time").ifEmpty {
                        obj.optString("last_time").ifEmpty { "2026-06-25" }
                    }
                }
            )
        } catch (e: Exception) {
            Log.e(TAG, "parseDeviceData failed", e)
            null
        }
    }

    /**
     * 更新智能测肤卡片显示状态
     * 根据 skinList 是否为空展示不同效果
     */
    private fun updateSkinTestCard() {
        if (skinList.isNotEmpty()) {
            // 有数据：显示数据卡片
            cardSkinTestFunc.visibility = View.GONE
            cardSkinTestData.visibility = View.VISIBLE

            tvSkinType.text = "肤质检测"
            tvSkinScore.text = "结果评分"
        } else {
            // 无数据：显示功能卡片
            cardSkinTestFunc.visibility = View.VISIBLE
            cardSkinTestData.visibility = View.GONE
        }
    }

    /**
     * 更新连接设备卡片显示状态
     * 根据 lastDevice 是否为空展示不同效果
     */
    private fun updateDeviceCard() {
        if (lastDevice != null) {
            // 有数据：显示数据卡片
            cardDeviceFunc.visibility = View.GONE
            cardDeviceData.visibility = View.VISIBLE

            tvDeviceName.text = lastDevice!!.deviceName
            tvDeviceTime.text = "最近使用：${lastDevice!!.createdAt}"
        } else {
            // 无数据：显示功能卡片
            cardDeviceFunc.visibility = View.VISIBLE
            cardDeviceData.visibility = View.GONE
        }
    }
}

/**
 * 测肤人数据
 */
data class SkinPersonData(
    val skinType: String,
    val skinScore: String
)

/**
 * 设备数据
 */
data class DeviceData(
    val deviceName: String,
    val createdAt: String
)
