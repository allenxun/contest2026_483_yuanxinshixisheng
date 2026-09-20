package com.example.aisia

import android.content.Intent
import android.os.Bundle
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.updatePadding
import androidx.fragment.app.Fragment
import com.example.aisia.privacy.PrivacyManager
import com.example.aisia.ui.home.HomeFragment
import com.example.aisia.ui.mine.MineFragment
import com.example.aisia.ui.scan.ScanFragment
import com.example.aisia.ui.skincare.SkincareFragment
import com.google.android.material.bottomnavigation.BottomNavigationView

class MainActivity : AppCompatActivity() {

    companion object {
        /** Intent extra key: 指定启动时显示的 tab，可选值: "home", "scan", "skincare", "mine" */
        const val EXTRA_TAB = "extra_tab"
        private const val TAG_HOME = "home"
        private const val TAG_SCAN = "scan"
        private const val TAG_SKINCARE = "skincare"
        private const val TAG_MINE = "mine"
    }

    private lateinit var homeFragment: HomeFragment
    private lateinit var scanFragment: ScanFragment
    private lateinit var skincareFragment: SkincareFragment
    private lateinit var mineFragment: MineFragment
    private var currentFragment: Fragment? = null
    private var tabsInitialized = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContentView(R.layout.activity_main)

        val root = findViewById<android.view.View>(R.id.main)
        val bottomNav = findViewById<BottomNavigationView>(R.id.bottomNav)

        // 适配系统栏：底部留导航栏内边距，顶部不留（轮播图顶到最上方）
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            bottomNav.updatePadding(bottom = bars.bottom)
            insets
        }

        // 合规要求：首次启动必须先弹出隐私政策征得同意弹窗，
        // 用户同意前不初始化功能页面（不申请敏感权限、不收集个人信息）
        PrivacyManager.ensureAgreed(this) {
            setupTabs(bottomNav)
        }
    }

    /** 初始化底部导航；优先复用 FragmentManager 已恢复的实例。 */
    private fun setupTabs(bottomNav: BottomNavigationView) {
        if (isFinishing || isDestroyed || tabsInitialized) return
        tabsInitialized = true

        val fragmentManager = supportFragmentManager
        homeFragment = fragmentManager.findFragmentByTag(TAG_HOME) as? HomeFragment ?: HomeFragment()
        scanFragment = fragmentManager.findFragmentByTag(TAG_SCAN) as? ScanFragment ?: ScanFragment()
        skincareFragment = fragmentManager.findFragmentByTag(TAG_SKINCARE) as? SkincareFragment ?: SkincareFragment()
        mineFragment = fragmentManager.findFragmentByTag(TAG_MINE) as? MineFragment ?: MineFragment()
        currentFragment = fragmentManager.fragments.lastOrNull { fragment ->
            fragment.id == R.id.fragmentContainer && fragment.isAdded && !fragment.isHidden
        }

        bottomNav.setOnItemSelectedListener { item ->
            when (item.itemId) {
                R.id.nav_home -> { switchFragment(homeFragment, TAG_HOME); true }
                R.id.nav_scan -> { switchFragment(scanFragment, TAG_SCAN); true }
                R.id.nav_skincare -> { switchFragment(skincareFragment, TAG_SKINCARE); true }
                R.id.nav_mine -> { switchFragment(mineFragment, TAG_MINE); true }
                else -> false
            }
        }

        val restoredItemId = when (currentFragment?.tag) {
            TAG_SCAN -> R.id.nav_scan
            TAG_SKINCARE -> R.id.nav_skincare
            TAG_MINE -> R.id.nav_mine
            TAG_HOME -> R.id.nav_home
            else -> null
        }
        if (restoredItemId != null) {
            // Fragment 已由系统恢复，只同步导航选中态，不重复 add。
            bottomNav.menu.findItem(restoredItemId).isChecked = true
        } else {
            val initialItemId = tabToItemId(intent.getStringExtra(EXTRA_TAB))
            bottomNav.menu.findItem(initialItemId).isChecked = true
            when (initialItemId) {
                R.id.nav_scan -> switchFragment(scanFragment, TAG_SCAN)
                R.id.nav_skincare -> switchFragment(skincareFragment, TAG_SKINCARE)
                R.id.nav_mine -> switchFragment(mineFragment, TAG_MINE)
                else -> switchFragment(homeFragment, TAG_HOME)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        // 未同意隐私政策时不处理 Tab 切换（理论上不会出现，做一层保护）
        if (!PrivacyManager.isAgreed(this)) return
        // 处理 FLAG_ACTIVITY_CLEAR_TOP | FLAG_ACTIVITY_SINGLE_TOP 场景
        val tab = intent.getStringExtra(EXTRA_TAB)
        if (tab != null) {
            val bottomNav = findViewById<BottomNavigationView>(R.id.bottomNav)
            bottomNav.selectedItemId = tabToItemId(tab)
        }
    }

    private fun tabToItemId(tab: String?): Int = when (tab) {
        "scan" -> R.id.nav_scan
        "skincare" -> R.id.nav_skincare
        "mine" -> R.id.nav_mine
        else -> R.id.nav_home
    }

    private fun switchFragment(target: Fragment, tag: String) {
        if (currentFragment === target) return
        val fragmentManager = supportFragmentManager
        if (fragmentManager.isStateSaved) return
        val tx = fragmentManager.beginTransaction().setReorderingAllowed(true)
        fragmentManager.fragments
            .filter { it.id == R.id.fragmentContainer && it.isAdded && it !== target && !it.isHidden }
            .forEach { tx.hide(it) }
        if (target.isAdded) {
            tx.show(target)
        } else {
            tx.add(R.id.fragmentContainer, target, tag)
        }
        currentFragment = target
        tx.commitNow()
    }
}
