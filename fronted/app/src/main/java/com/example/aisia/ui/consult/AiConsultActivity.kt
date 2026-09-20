package com.example.aisia.ui.consult

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.example.aisia.R
import com.example.aisia.network.HttpHelper
import org.json.JSONObject

/**
 * 智能咨询页面
 * 对接 Chat 聊天接口：
 * 1. GET  /api/chat/sessions    - 查询会话列表
 * 2. POST /api/chat/completions - 非流式对话补全（发送消息并获取智能回复）
 */
class AiConsultActivity : AppCompatActivity() {

    private val mainHandler = Handler(Looper.getMainLooper())
    private val chatAdapter = ChatMessageAdapter()

    // 当前会话 ID（用于持续对话）
    private var currentSessionId: String? = null

    // 是否正在等待智能回复
    private var isWaitingForResponse = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_ai_consult)

        // 返回按钮
        findViewById<ImageView>(R.id.btnBack).setOnClickListener { finish() }

        // 聊天消息列表
        val rvChat = findViewById<RecyclerView>(R.id.rvChatMessages)
        val lm = LinearLayoutManager(this).apply { stackFromEnd = true }
        rvChat.layoutManager = lm
        rvChat.adapter = chatAdapter

        // 热门问题
        findViewById<View>(R.id.layoutHot1).setOnClickListener {
            sendMessage("我的皮肤状态怎么样？")
        }
        findViewById<View>(R.id.layoutHot2).setOnClickListener {
            sendMessage("请帮我解读检测报告")
        }
        findViewById<View>(R.id.layoutHot3).setOnClickListener {
            sendMessage("设备使用有什么问题需要注意？")
        }
        findViewById<View>(R.id.layoutHot4).setOnClickListener {
            sendMessage("请给我一些护肤建议")
        }

        // 输入框
        val etMessage = findViewById<EditText>(R.id.etMessage)
        etMessage.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEND) {
                onSendClicked()
                true
            } else {
                false
            }
        }

        // 发送按钮
        findViewById<ImageView>(R.id.btnSend).setOnClickListener {
            onSendClicked()
        }
    }

    /**
     * 发送按钮点击
     */
    private fun onSendClicked() {
        if (isWaitingForResponse) return
        val etMessage = findViewById<EditText>(R.id.etMessage)
        val message = etMessage.text.toString().trim()
        if (message.isEmpty()) return

        sendMessage(message)
        etMessage.setText("")
        hideKeyboard()
    }

    /**
     * 隐藏键盘
     */
    private fun hideKeyboard() {
        val imm = getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager
        val view = currentFocus ?: View(this)
        imm.hideSoftInputFromWindow(view.windowToken, 0)
    }

    /**
     * 发送消息
     */
    private fun sendMessage(message: String) {
        if (isWaitingForResponse) return
        isWaitingForResponse = true

        // 切换到聊天模式
        switchToChatMode()

        // 显示用户消息（右侧）
        chatAdapter.addMessage(true, message)

        // 显示加载状态
        findViewById<View>(R.id.layoutLoading).visibility = View.VISIBLE
        scrollToBottom()

        // 构建请求参数
        val params = mutableMapOf<String, String>(
            "message" to message
        )
        currentSessionId?.let { params["session_id"] = it }

        HttpHelper.post(
            path = "/api/chat/completions",
            params = params,
            onSuccess = { responseBody ->
                mainHandler.post {
                    isWaitingForResponse = false
                    findViewById<View>(R.id.layoutLoading).visibility = View.GONE
                    handleCompletionResponse(responseBody)
                }
            },
            onFailure = { _, errorMsg ->
                mainHandler.post {
                    isWaitingForResponse = false
                    findViewById<View>(R.id.layoutLoading).visibility = View.GONE
                    chatAdapter.addMessage(false, "抱歉，请求失败：$errorMsg")
                    scrollToBottom()
                }
            },
            timeoutSeconds = 60L
        )
    }

    /**
     * 切换到聊天模式：隐藏热门问题，显示聊天列表
     */
    private fun switchToChatMode() {
        findViewById<View>(R.id.layoutHomePage).visibility = View.GONE
        findViewById<RecyclerView>(R.id.rvChatMessages).visibility = View.VISIBLE
    }

    /**
     * 处理智能回复
     */
    private fun handleCompletionResponse(responseBody: String) {
        try {
            val json = JSONObject(responseBody)
            currentSessionId = json.getString("session_id")
            val content = json.getString("content")

            chatAdapter.addMessage(false, content)
            scrollToBottom()
        } catch (e: Exception) {
            e.printStackTrace()
            chatAdapter.addMessage(false, "抱歉，解析回复失败：${e.message}")
            scrollToBottom()
        }
    }

    /**
     * 滚动到底部
     */
    private fun scrollToBottom() {
        val rv = findViewById<RecyclerView>(R.id.rvChatMessages)
        mainHandler.postDelayed({
            val count = chatAdapter.itemCount
            if (count > 0) {
                rv.smoothScrollToPosition(count - 1)
            }
        }, 150)
    }
}