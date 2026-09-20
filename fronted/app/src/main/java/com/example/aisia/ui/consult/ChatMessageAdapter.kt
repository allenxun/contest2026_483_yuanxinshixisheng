package com.example.aisia.ui.consult

import android.os.Handler
import android.os.Looper
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import coil.load
import com.example.aisia.R

/**
 * 聊天消息列表适配器
 * 支持用户消息（右侧）和智能消息（左侧）
 * 支持打字机动画效果
 */
class ChatMessageAdapter : RecyclerView.Adapter<ChatMessageAdapter.VH>() {

    companion object {
        private const val AVATAR_URL = "https://eveaisia.com/face/img/user.png"
        private const val STREAM_TYPING_INTERVAL_MS = 48L
        private const val TEXT_PAYLOAD = "message_text"
    }

    /**
     * 消息数据：Pair(isUser, content)
     * isUser=true 表示用户消息（右侧），isUser=false 表示智能消息（左侧）
     */
    private var data: MutableList<Pair<Boolean, String>> = mutableListOf()
    private val handler = Handler(Looper.getMainLooper())
    
    // 打字机动画配置
    private var typingRunnable: Runnable? = null
    private var currentTypingPosition: Int = -1

    // SSE 增量回复的打字机队列。网络接收与界面展示解耦，避免大 chunk 一次性跳出。
    private var streamingRunnable: Runnable? = null
    private var streamingPosition: Int = -1
    private val streamingPending = StringBuilder()
    private var streamingPendingReadIndex = 0
    private val streamingDisplayed = StringBuilder()
    private var streamingHasDelta = false
    private var streamingEnded = false
    private var streamingCompleteCallback: (() -> Unit)? = null

    fun submit(list: List<Pair<Boolean, String>>) {
        data = list.toMutableList()
        notifyDataSetChanged()
    }

    fun addMessage(isUser: Boolean, content: String) {
        data.add(Pair(isUser, content))
        notifyItemInserted(data.size - 1)
    }

    /**
     * 更新最后一条智能消息（无动画）
     */
    fun updateLastAiMessage(content: String) {
        if (data.isNotEmpty() && !data.last().first) {
            data[data.lastIndex] = Pair(false, content)
            notifyItemChanged(data.size - 1)
        }
    }

    /**
     * 初始化最后一条智能消息的流式展示状态。
     * 占位文字会保留到第一个 delta 到达，避免出现空白气泡。
     */
    fun beginStreamingLastAiMessage() {
        cancelTypingAnimation()
        cancelStreamingAnimation()
        if (data.isEmpty() || data.last().first) return

        streamingPosition = data.lastIndex
        streamingPending.clear()
        streamingPendingReadIndex = 0
        streamingDisplayed.clear()
        streamingHasDelta = false
        streamingEnded = false
        streamingCompleteCallback = null
    }

    /** 第一个 delta 立即启动，之后约每 24ms 输出；积压越多，每帧输出字符数会适度增加。 */
    fun appendStreamingDelta(content: String) {
        if (content.isEmpty() || streamingPosition !in data.indices || streamingEnded) return

        if (!streamingHasDelta) {
            streamingHasDelta = true
            updateStreamingMessage("")
        }
        streamingPending.append(content)
        scheduleStreamingTick(immediate = streamingRunnable == null)
    }

    /** 网络流正常结束后，继续排空已接收文本，再回调允许下一次发送。 */
    fun completeStreamingLastAiMessage(onComplete: (() -> Unit)? = null) {
        if (streamingPosition !in data.indices) {
            onComplete?.invoke()
            return
        }
        if (!streamingHasDelta) {
            failStreamingLastAiMessage("未收到有效回复，请重试", onComplete)
            return
        }

        streamingEnded = true
        streamingCompleteCallback = onComplete
        if (streamingPendingSize() == 0 && streamingRunnable == null) {
            finishStreamingAnimation()
        } else {
            scheduleStreamingTick(immediate = streamingRunnable == null)
        }
    }

    /** 保留已经收到的部分内容，并在末尾追加明确的中断原因。 */
    fun failStreamingLastAiMessage(message: String, onComplete: (() -> Unit)? = null) {
        streamingRunnable?.let(handler::removeCallbacks)
        streamingRunnable = null

        val partial = buildString {
            append(streamingDisplayed)
            if (streamingPendingReadIndex < streamingPending.length) {
                append(streamingPending.substring(streamingPendingReadIndex))
            }
        }.trim()
        val finalText = if (partial.isEmpty()) {
            message
        } else {
            "$partial\n\n回复中断：$message"
        }
        if (streamingPosition in data.indices) updateStreamingMessage(finalText)

        resetStreamingState()
        onComplete?.invoke()
    }

    private fun scheduleStreamingTick(immediate: Boolean) {
        if (streamingRunnable != null || streamingPosition !in data.indices) return

        streamingRunnable = object : Runnable {
            override fun run() {
                if (streamingPosition !in data.indices) {
                    streamingRunnable = null
                    finishStreamingAnimation()
                    return
                }

                val charactersThisTick = when {
                    streamingPendingSize() > 480 -> 8
                    streamingPendingSize() > 180 -> 6
                    streamingPendingSize() > 60 -> 4
                    else -> 2
                }
                repeat(charactersThisTick) {
                    appendNextCodePoint()
                }

                updateStreamingMessage(streamingDisplayed.toString())
                if (streamingPendingSize() > 0) {
                    handler.postDelayed(this, STREAM_TYPING_INTERVAL_MS)
                } else {
                    streamingRunnable = null
                    if (streamingEnded) finishStreamingAnimation()
                }
            }
        }

        if (immediate) handler.post(streamingRunnable!!) else handler.postDelayed(
            streamingRunnable!!,
            STREAM_TYPING_INTERVAL_MS
        )
    }

    private fun appendNextCodePoint() {
        if (streamingPendingSize() == 0) return
        val codePoint = Character.codePointAt(streamingPending, streamingPendingReadIndex)
        val charCount = Character.charCount(codePoint)
            .coerceAtMost(streamingPending.length - streamingPendingReadIndex)
        val nextIndex = streamingPendingReadIndex + charCount
        streamingDisplayed.append(
            streamingPending,
            streamingPendingReadIndex,
            nextIndex
        )
        streamingPendingReadIndex = nextIndex

        // 避免逐字删除 StringBuilder 造成长回答 O(n²) 搬移；只在队列读空时一次性清理。
        if (streamingPendingReadIndex == streamingPending.length) {
            streamingPending.clear()
            streamingPendingReadIndex = 0
        }
    }

    private fun streamingPendingSize(): Int = streamingPending.length - streamingPendingReadIndex

    private fun updateStreamingMessage(content: String) {
        if (streamingPosition !in data.indices) return
        data[streamingPosition] = Pair(false, content)
        notifyItemChanged(streamingPosition, TEXT_PAYLOAD)
    }

    private fun finishStreamingAnimation() {
        val callback = streamingCompleteCallback
        resetStreamingState()
        callback?.invoke()
    }

    private fun resetStreamingState() {
        streamingRunnable?.let(handler::removeCallbacks)
        streamingRunnable = null
        streamingPosition = -1
        streamingPending.clear()
        streamingPendingReadIndex = 0
        streamingDisplayed.clear()
        streamingHasDelta = false
        streamingEnded = false
        streamingCompleteCallback = null
    }

    fun cancelStreamingAnimation() {
        resetStreamingState()
    }

    /**
     * 以打字机动画方式更新最后一条智能消息
     * @param content 完整的回复内容
     * @param charPerTick 每次显示的字符数
     * @param delayMs 每次显示的间隔毫秒
     * @param onComplete 动画完成后的回调
     */
    fun typewriterLastAiMessage(
        content: String,
        charPerTick: Int = 2,
        delayMs: Long = 50,
        onComplete: (() -> Unit)? = null
    ) {
        // 取消之前的动画
        cancelTypingAnimation()

        if (data.isEmpty() || data.last().first) return

        currentTypingPosition = data.size - 1
        var currentIndex = 0

        typingRunnable = object : Runnable {
            override fun run() {
                if (currentTypingPosition < 0 || currentTypingPosition >= data.size) {
                    onComplete?.invoke()
                    return
                }

                currentIndex = (currentIndex + charPerTick).coerceAtMost(content.length)
                val displayText = content.substring(0, currentIndex)

                data[currentTypingPosition] = Pair(false, displayText)
                notifyItemChanged(currentTypingPosition, TEXT_PAYLOAD)

                if (currentIndex < content.length) {
                    handler.postDelayed(this, delayMs)
                } else {
                    typingRunnable = null
                    currentTypingPosition = -1
                    onComplete?.invoke()
                }
            }
        }

        // 开始动画
        handler.post(typingRunnable!!)
    }

    /**
     * 取消打字机动画
     */
    fun cancelTypingAnimation() {
        typingRunnable?.let {
            handler.removeCallbacks(it)
            typingRunnable = null
        }
        currentTypingPosition = -1
    }

    /**
     * 是否正在播放打字动画
     */
    fun isTyping(): Boolean = typingRunnable != null || streamingRunnable != null || streamingPendingSize() > 0

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val v = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_chat_message, parent, false)
        return VH(v)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        val item = data[position]
        if (item.first) {
            // 用户消息
            holder.layoutUserMessage.visibility = View.VISIBLE
            holder.layoutAiMessage.visibility = View.GONE
            holder.tvUserMessage.text = item.second
            holder.ivUserAvatar.load(AVATAR_URL) {
                crossfade(true)
                placeholder(R.drawable.ic_default_avatar)
                error(R.drawable.ic_default_avatar)
            }
        } else {
            // 智能消息
            holder.layoutUserMessage.visibility = View.GONE
            holder.layoutAiMessage.visibility = View.VISIBLE
            holder.tvAiMessage.text = item.second
            holder.ivAiAvatar.load(AVATAR_URL) {
                crossfade(true)
                placeholder(R.drawable.ic_default_avatar)
                error(R.drawable.ic_default_avatar)
            }
        }
    }

    override fun onBindViewHolder(holder: VH, position: Int, payloads: MutableList<Any>) {
        if (payloads.isNotEmpty() && payloads.all { it == TEXT_PAYLOAD }) {
            if (data[position].first) holder.tvUserMessage.text = data[position].second
            else holder.tvAiMessage.text = data[position].second
        } else super.onBindViewHolder(holder, position, payloads)
    }

    override fun getItemCount(): Int = data.size

    class VH(view: View) : RecyclerView.ViewHolder(view) {
        val layoutUserMessage: LinearLayout = view.findViewById(R.id.layoutUserMessage)
        val layoutAiMessage: LinearLayout = view.findViewById(R.id.layoutAiMessage)
        val tvUserMessage: TextView = view.findViewById(R.id.tvUserMessage)
        val tvAiMessage: TextView = view.findViewById(R.id.tvAiMessage)
        val ivUserAvatar: ImageView = view.findViewById(R.id.ivUserAvatar)
        val ivAiAvatar: ImageView = view.findViewById(R.id.ivAiAvatar)
    }
}
