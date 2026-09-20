package com.example.aisia.ui.scan

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.text.Editable
import android.text.TextWatcher
import android.util.Log
import android.view.MotionEvent
import android.view.View
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.widget.NestedScrollView
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.example.aisia.R
import com.example.aisia.network.HttpHelper
import com.example.aisia.privacy.PrivacyManager
import com.example.aisia.ui.consult.ChatMessageAdapter
import com.google.android.material.card.MaterialCardView
import okhttp3.Call
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

class ScanFragment : Fragment(R.layout.fragment_scan) {

    companion object {
        private const val TAG = "ScanFragment"
        private const val RECORD_AUDIO_PERMISSION_CODE = 1001
        private const val ASR_PATH = "/api/asr/recognize"
        private const val CHAT_STREAM_PATH = "/api/chat/completions/stream"
        private const val CHAT_IDLE_TIMEOUT_SECONDS = 30L
        private const val STATE_CHAT_SESSION_ID = "chat_session_id"
        private const val MIN_RECORD_DURATION_MS = 800L
        private const val CANCEL_SLIDE_THRESHOLD_DP = 80
        // WAV 录音参数（16kHz, 16bit, 单声道）
        private const val SAMPLE_RATE = 16000
        private const val CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO
        private const val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
    }

    private val chatAdapter = ChatMessageAdapter()
    private var isWaitingForResponse = false
    private val handler = Handler(Looper.getMainLooper())
    private var streamCall: Call? = null
    private var streamRequestId = 0
    private var streamDoneReceived = false
    private var streamCompletionStarted = false
    private var chatSessionId: String? = null

    // Views
    private var layoutHotQuestions: LinearLayout? = null
    private var rvChat: RecyclerView? = null
    private var scrollView: NestedScrollView? = null
    private var layoutInputMode: LinearLayout? = null
    private var layoutVoiceMode: LinearLayout? = null
    private var etMessage: EditText? = null
    private var btnVoiceInput: ImageView? = null
    private var btnSend: ImageView? = null
    private var btnHoldToSpeak: TextView? = null
    private var btnKeyboard: ImageView? = null

    // 录音状态（AudioRecord for WAV）
    private var audioRecord: AudioRecord? = null
    private var recordingThread: Thread? = null
    private var audioFile: File? = null
    @Volatile private var isRecording = false
    @Volatile private var recordingFinishing = false
    private var recordingEpoch = 0
    private val recordingToken = java.util.concurrent.atomic.AtomicInteger()
    private var recordStartTime = 0L
    private var recordError: String? = null

    // 触摸状态
    private var touchDownY = 0f
    private var isCancelMode = false
    private var permissionGrantedCallback: (() -> Unit)? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        chatSessionId = savedInstanceState?.getString(STATE_CHAT_SESSION_ID)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        chatSessionId?.let { outState.putString(STATE_CHAT_SESSION_ID, it) }
        super.onSaveInstanceState(outState)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        initViews(view)
        initChatList()
        initHotQuestionCards(view)
        initInputModeListeners()
        initVoiceModeListeners()
        Log.d(TAG, "onViewCreated complete")
    }

    private fun initViews(view: View) {
        layoutHotQuestions = view.findViewById(R.id.layoutHotQuestions)
        rvChat = view.findViewById(R.id.rvChatMessages)
        scrollView = view.findViewById(R.id.scrollView)
        layoutInputMode = view.findViewById(R.id.layoutInputMode)
        layoutVoiceMode = view.findViewById(R.id.layoutVoiceMode)
        etMessage = view.findViewById(R.id.etMessage)
        btnVoiceInput = view.findViewById(R.id.btnVoiceInput)
        btnSend = view.findViewById(R.id.btnSend)
        btnHoldToSpeak = view.findViewById(R.id.btnHoldToSpeak)
        btnKeyboard = view.findViewById(R.id.btnKeyboard)
    }

    private fun initChatList() {
        rvChat?.layoutManager = LinearLayoutManager(requireContext())
        rvChat?.adapter = chatAdapter
    }

    private fun initHotQuestionCards(view: View) {
        view.findViewById<MaterialCardView>(R.id.cardSkinState)
            ?.setOnClickListener { sendMessage("我的皮肤状态怎么样？") }
        view.findViewById<MaterialCardView>(R.id.cardReportAnalysis)
            ?.setOnClickListener { sendMessage("帮我解读一下检测报告") }
        view.findViewById<MaterialCardView>(R.id.cardDeviceHelp)
            ?.setOnClickListener { sendMessage("设备连接不上怎么办？") }
        view.findViewById<MaterialCardView>(R.id.cardSkincareAdvice)
            ?.setOnClickListener { sendMessage("给我一些护肤建议") }
    }

    private fun initInputModeListeners() {
        etMessage?.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                updateInputButtonVisibility(s?.toString()?.trim()?.isNotEmpty() == true)
            }
        })
        btnVoiceInput?.setOnClickListener {
            ensureRecordPermission { switchToVoiceMode() }
        }
        btnSend?.setOnClickListener {
            val msg = etMessage?.text?.toString()?.trim() ?: ""
            if (msg.isNotEmpty() && sendMessage(msg)) {
                etMessage?.setText("")
            }
        }
    }

    private fun ensureRecordPermission(onGranted: () -> Unit) {
        // 合规要求：用户同意隐私政策后才能申请麦克风权限
        PrivacyManager.ensureAgreed(requireActivity()) {
            if (ContextCompat.checkSelfPermission(requireContext(), Manifest.permission.RECORD_AUDIO)
                == PackageManager.PERMISSION_GRANTED
            ) {
                onGranted()
            } else {
                permissionGrantedCallback = onGranted
                Log.d(TAG, "Requesting RECORD_AUDIO permission")
                requestPermissions(
                    arrayOf(Manifest.permission.RECORD_AUDIO),
                    RECORD_AUDIO_PERMISSION_CODE
                )
            }
        }
    }

    @Deprecated("Use ensureRecordPermission instead")
    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        Log.d(TAG, "onRequestPermissionsResult: requestCode=$requestCode, grants=${grantResults.toList()}")
        if (requestCode == RECORD_AUDIO_PERMISSION_CODE) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                Log.d(TAG, "Permission GRANTED")
                permissionGrantedCallback?.invoke()
            } else {
                Log.d(TAG, "Permission DENIED, shouldShowRationale=${shouldShowRequestPermissionRationale(Manifest.permission.RECORD_AUDIO)}")
                if (!shouldShowRequestPermissionRationale(Manifest.permission.RECORD_AUDIO)) {
                    // 永久拒绝，引导去设置页
                    android.app.AlertDialog.Builder(requireContext())
                        .setTitle("需要麦克风权限")
                        .setMessage("语音功能需要麦克风权限，请在设置中手动开启")
                        .setPositiveButton("去设置") { _, _ ->
                            try {
                                startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                                    data = Uri.fromParts("package", requireContext().packageName, null)
                                })
                            } catch (_: Exception) {}
                        }
                        .setNegativeButton("取消", null)
                        .show()
                } else {
                    Toast.makeText(requireContext(), "❌ 需要麦克风权限才能使用语音", Toast.LENGTH_LONG).show()
                }
            }
            permissionGrantedCallback = null
        }
    }

    private fun initVoiceModeListeners() {
        btnKeyboard?.setOnClickListener { switchToInputMode() }

        val btn = btnHoldToSpeak ?: return

        btn.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    Log.d(TAG, ">>> ACTION_DOWN")
                    touchDownY = event.rawY
                    isCancelMode = false
                    recordError = null

                    val started = startRecording()
                    if (!started) {
                        btn.text = recordError ?: "录音启动失败"
                        btn.setTextColor(0xFFFF4444.toInt())
                    } else {
                        btn.text = "松开发送，上滑取消"
                        btn.setTextColor(0xFF333333.toInt())
                    }
                    true
                }

                MotionEvent.ACTION_MOVE -> {
                    if (!isRecording) return@setOnTouchListener true
                    val deltaY = touchDownY - event.rawY
                    val thresholdPx = CANCEL_SLIDE_THRESHOLD_DP * resources.displayMetrics.density
                    if (deltaY > thresholdPx && !isCancelMode) {
                        isCancelMode = true
                        btn.text = "松开取消"
                        btn.setTextColor(0xFFFF4444.toInt())
                    } else if (deltaY <= thresholdPx && isCancelMode) {
                        isCancelMode = false
                        btn.text = "松开发送，上滑取消"
                        btn.setTextColor(0xFF333333.toInt())
                    }
                    true
                }

                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    val actionName = if (event.actionMasked == MotionEvent.ACTION_UP) "ACTION_UP" else "ACTION_CANCEL"
                    Log.d(TAG, ">>> $actionName, isRecording=$isRecording, isCancelMode=$isCancelMode")
                    try {
                        if (!isRecording) {
                            if (recordError != null) {
                                Toast.makeText(requireContext(), "❌ $recordError", Toast.LENGTH_LONG).show()
                            }
                        } else if (isCancelMode) {
                            discardRecording()
                            Toast.makeText(requireContext(), "已取消录音", Toast.LENGTH_SHORT).show()
                        } else {
                            stopRecordingAndSend()
                        }
                    } catch (e: Exception) {
                        Log.e(TAG, "touch end exception", e)
                        Toast.makeText(requireContext(), "❌ ${e.message}", Toast.LENGTH_LONG).show()
                        isRecording = false
                        discardRecording()
                        recordingThread = null
                        try { audioRecord?.stop() } catch (_: Exception) {}
                        try { audioRecord?.release() } catch (_: Exception) {}
                        audioRecord = null
                    }
                    isCancelMode = false
                    btn.text = "按住 说话"
                    btn.setTextColor(0xFF333333.toInt())
                    true
                }

                else -> false
            }
        }
    }

    /**
     * 使用 AudioRecord 录制 WAV 格式（PCM 16-bit, 16kHz, 单声道）
     */
    private fun startRecording(): Boolean {
        Log.d(TAG, "startRecording: begin (WAV via AudioRecord)")
        if (recordingFinishing) { recordError = "录音正在保存，请稍候"; return false }

        if (ContextCompat.checkSelfPermission(requireContext(), Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED
        ) {
            recordError = "没有麦克风权限"
            return false
        }

        try {
            val bufferSize = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT)
            val recorder = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT, bufferSize
            )

            if (recorder.state != AudioRecord.STATE_INITIALIZED) {
                recordError = "AudioRecord 初始化失败"
                recorder.release()
                return false
            }

            audioFile = File(requireContext().cacheDir, "voice_${System.currentTimeMillis()}.wav")
            recorder.startRecording()
            audioRecord = recorder
            isRecording = true
            recordStartTime = System.currentTimeMillis()

            val token = recordingToken.incrementAndGet()
            val file = audioFile!!
            val buffer = ByteArray(bufferSize)
            recordingThread = Thread {
                try {
                    java.io.RandomAccessFile(file, "rw").use { output ->
                        output.setLength(0)
                        output.write(ByteArray(44))
                        var dataSize = 0
                        while (isRecording && token == recordingToken.get() && !Thread.currentThread().isInterrupted) {
                            val read = recorder.read(buffer, 0, buffer.size)
                            if (read > 0) { output.write(buffer, 0, read); dataSize += read }
                            else if (read < 0) break
                            if (dataSize >= SAMPLE_RATE * 2 * 300) {
                                handler.post { if (token == recordingToken.get() && isAdded) stopRecordingAndSend() }
                                break
                            }
                        }
                        val header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
                        header.put("RIFF".toByteArray()).putInt(36 + dataSize).put("WAVE".toByteArray())
                        header.put("fmt ".toByteArray()).putInt(16).putShort(1).putShort(1)
                        header.putInt(SAMPLE_RATE).putInt(SAMPLE_RATE * 2).putShort(2).putShort(16)
                        header.put("data".toByteArray()).putInt(dataSize)
                        output.seek(0); output.write(header.array())
                    }
                } catch (e: Exception) { Log.e(TAG, "录音写入失败", e) }
            }.also { it.start() }

            return true
        } catch (e: Exception) {
            recordError = "录音失败: ${e.message ?: "未知"}"
            Log.e(TAG, "startRecording error", e)
            isRecording = false
            return false
        }
    }

    /**
     * 将 PCM 数据写入 WAV 文件（44 字节 RIFF 头 + PCM 数据）
     */
    private fun writeWavFile(file: File, pcmData: ByteArray) {
        val channels = 1
        val bitsPerSample = 16
        val byteRate = SAMPLE_RATE * channels * bitsPerSample / 8
        val blockAlign = channels * bitsPerSample / 8
        val dataSize = pcmData.size

        FileOutputStream(file).use { fos ->
            val header = ByteBuffer.allocate(44).apply {
                order(ByteOrder.LITTLE_ENDIAN)
                // RIFF chunk
                put('R'.code.toByte()); put('I'.code.toByte())
                put('F'.code.toByte()); put('F'.code.toByte())
                putInt(36 + dataSize)
                put('W'.code.toByte()); put('A'.code.toByte())
                put('V'.code.toByte()); put('E'.code.toByte())
                // fmt subchunk
                put('f'.code.toByte()); put('m'.code.toByte())
                put('t'.code.toByte()); put(' '.code.toByte())
                putInt(16)              // Subchunk1Size
                putShort(1)             // AudioFormat: PCM
                putShort(channels.toShort())
                putInt(SAMPLE_RATE)
                putInt(byteRate)
                putShort(blockAlign.toShort())
                putShort(bitsPerSample.toShort())
                // data subchunk
                put('d'.code.toByte()); put('a'.code.toByte())
                put('t'.code.toByte()); put('a'.code.toByte())
                putInt(dataSize)
            }
            fos.write(header.array())
            fos.write(pcmData)
        }
    }

    private fun stopRecordingAndSend() {
        if (!isRecording) return
        finishRecording(send = System.currentTimeMillis() - recordStartTime >= MIN_RECORD_DURATION_MS)
    }

    private fun discardRecording() = finishRecording(send = false)

    private fun finishRecording(send: Boolean) {
        isRecording = false
        recordingToken.incrementAndGet()
        if (audioRecord == null && recordingThread == null) return
        recordingFinishing = true
        val recorder = audioRecord; audioRecord = null
        val worker = recordingThread; recordingThread = null
        val file = audioFile; audioFile = null
        val epoch = recordingEpoch
        Thread {
            try {
                try { recorder?.stop() } catch (_: Exception) {}
                // Off-main wait: never upload a WAV whose header is still being written.
                worker?.join(3000)
                try { recorder?.release() } catch (_: Exception) {}
                if (worker?.isAlive == true) worker.join(1000)
                handler.post {
                    if (send && worker?.isAlive != true && epoch == recordingEpoch && isAdded && view != null && file != null && file.length() > 44) {
                        recognizeSpeech(file)
                    } else file?.delete()
                }
            } finally { recordingFinishing = false }
        }.start()
    }

    private fun recognizeSpeech(file: File) {
        Log.d(TAG, "recognizeSpeech: fileSize=${file.length()}")
        layoutHotQuestions?.visibility = View.GONE
        val epoch = recordingEpoch
        Thread {
        try {
            if (file.length() > 16L * 1024 * 1024) throw java.io.IOException("录音过长，请分段录制")
            val audioBytes = file.readBytes()
            val base64Audio = android.util.Base64.encodeToString(audioBytes, android.util.Base64.NO_WRAP)
            Log.d(TAG, "Base64 length=${base64Audio.length}")

            // 接口支持 wav 格式
            val jsonBody = JSONObject().apply {
                put("audio_data", base64Audio)
                put("format", "wav")
                put("language", "zh")
            }.toString()
            Log.d(TAG, "JSON body size=${jsonBody.length}")

            HttpHelper.postJson(
                path = ASR_PATH,
                jsonBody = jsonBody,
                timeoutSeconds = 60,
                onSuccess = { responseBody ->
                    Log.d(TAG, "ASR success: responseLength=${responseBody.length}")
                    handler.post {
                        if (epoch != recordingEpoch || !isAdded || view == null) return@post
                        handleAsrResponse(responseBody)
                    }
                },
                onFailure = { code, errorMsg ->
                    Log.e(TAG, "ASR failure: code=$code, msg=$errorMsg")
                    handler.post {
                        if (epoch != recordingEpoch || !isAdded || view == null) return@post
                        chatAdapter.updateLastAiMessage("语音识别失败，请重试")
                        scrollToBottom()
                    }
                }
            )
        } catch (e: Exception) {
            Log.e(TAG, "recognizeSpeech failed", e)
            handler.post {
                if (epoch == recordingEpoch && isAdded && view != null) {
                    chatAdapter.updateLastAiMessage("语音识别失败，请重试")
                    scrollToBottom()
                }
            }
        }
        }.start()
    }

    private fun handleAsrResponse(body: String) {
        try {
            val json = JSONObject(body)
            val recognizedText = json.optString("text", "")
                .ifEmpty { json.optString("result", "") }
                .ifEmpty { json.optJSONObject("data")?.optString("text", "") ?: "" }

            if (recognizedText.isNotEmpty()) {
                Log.d(TAG, "ASR recognized: textLength=${recognizedText.length}")
                sendMessage(recognizedText)
            } else {
                chatAdapter.updateLastAiMessage("未能识别语音内容，请重试")
                scrollToBottom()
            }
        } catch (e: Exception) {
            Log.e(TAG, "handleAsrResponse error", e)
            chatAdapter.updateLastAiMessage("语音识别解析失败")
            scrollToBottom()
        }
    }


    private fun updateInputButtonVisibility(hasText: Boolean) {
        btnVoiceInput?.visibility = if (hasText) View.GONE else View.VISIBLE
        btnSend?.visibility = if (hasText) View.VISIBLE else View.GONE
    }

    private fun switchToVoiceMode() {
        layoutInputMode?.visibility = View.GONE
        layoutVoiceMode?.visibility = View.VISIBLE
    }

    private fun switchToInputMode() {
        layoutVoiceMode?.visibility = View.GONE
        layoutInputMode?.visibility = View.VISIBLE
    }

    private fun sendMessage(message: String): Boolean {
        val normalizedMessage = message.trim()
        if (normalizedMessage.isEmpty()) return false
        if (isWaitingForResponse) {
            Toast.makeText(requireContext(), "请等待当前回复完成", Toast.LENGTH_SHORT).show()
            return false
        }

        isWaitingForResponse = true
        setSendingState(true)
        layoutHotQuestions?.visibility = View.GONE
        chatAdapter.addMessage(true, normalizedMessage)
        scrollToBottom()
        chatAdapter.addMessage(false, "正在思考...")
        chatAdapter.beginStreamingLastAiMessage()
        scrollToBottom()
        startAutoScrollDuringTyping()

        val requestId = ++streamRequestId
        streamDoneReceived = false
        streamCompletionStarted = false
        val requestBody = JSONObject().apply {
            put("message", normalizedMessage)
            chatSessionId?.takeIf { it.isNotBlank() }?.let { put("session_id", it) }
        }.toString()

        val call = HttpHelper.postSse(
            path = CHAT_STREAM_PATH,
            jsonBody = requestBody,
            idleTimeoutSeconds = CHAT_IDLE_TIMEOUT_SECONDS,
            onEvent = { data ->
                handler.post {
                    if (isCurrentStream(requestId)) handleStreamEvent(requestId, data)
                }
            },
            onClosed = {
                handler.post {
                    if (!isCurrentStream(requestId)) return@post
                    if (!streamDoneReceived && !streamCompletionStarted) {
                        failStream(requestId, "连接提前结束，请重试")
                    }
                }
            },
            onFailure = { code, errorMsg ->
                handler.post {
                    if (!isCurrentStream(requestId) || streamCompletionStarted) return@post
                    val message = when (code) {
                        401 -> "登录已失效，请重新登录"
                        else -> extractStreamError(errorMsg)
                    }
                    failStream(requestId, message)
                }
            }
        )
        if (isCurrentStream(requestId)) {
            streamCall = call
        } else {
            call.cancel()
        }
        return true
    }

    private fun handleStreamEvent(requestId: Int, data: String) {
        if (data == "[DONE]") {
            completeStream(requestId)
            return
        }

        try {
            val event = JSONObject(data)
            when (event.optString("type")) {
                "delta" -> {
                    val content = event.optString("content", "")
                        .takeUnless { it.equals("null", ignoreCase = true) }
                        .orEmpty()
                    if (content.isNotEmpty()) {
                        chatAdapter.appendStreamingDelta(content)
                        scrollToBottom()
                    }
                }
                "usage" -> Unit
                "done" -> {
                    event.optString("session_id", "")
                        .takeIf { it.isNotBlank() && !it.equals("null", ignoreCase = true) }
                        ?.let { chatSessionId = it }
                    completeStream(requestId)
                }
                "error" -> {
                    val message = event.optString("message", "回复生成失败，请重试")
                    failStream(requestId, message)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "SSE event parse failed", e)
            failStream(requestId, "回复数据解析失败，请重试")
        }
    }

    private fun completeStream(requestId: Int) {
        if (!isCurrentStream(requestId) || streamCompletionStarted) return
        streamDoneReceived = true
        streamCompletionStarted = true
        chatAdapter.completeStreamingLastAiMessage {
            finishStreamRequest(requestId)
        }
    }

    private fun failStream(requestId: Int, message: String) {
        if (!isCurrentStream(requestId) || streamCompletionStarted) return
        streamCompletionStarted = true
        streamCall?.cancel()
        streamCall = null
        chatAdapter.failStreamingLastAiMessage(message) {
            finishStreamRequest(requestId)
        }
    }

    private fun finishStreamRequest(requestId: Int) {
        if (requestId != streamRequestId) return
        streamCall = null
        isWaitingForResponse = false
        setSendingState(false)
        scrollToBottom()
    }

    private fun isCurrentStream(requestId: Int): Boolean =
        requestId == streamRequestId && isWaitingForResponse && isAdded && view != null

    private fun setSendingState(sending: Boolean) {
        btnSend?.isEnabled = !sending
        btnSend?.alpha = if (sending) 0.5f else 1f
        btnVoiceInput?.isEnabled = !sending
        btnHoldToSpeak?.isEnabled = !sending
    }

    private fun extractStreamError(rawMessage: String): String {
        if (rawMessage.isBlank()) return "回复生成失败，请重试"
        return try {
            val json = JSONObject(rawMessage)
            json.optString("message", "")
                .ifBlank { json.optString("detail", "") }
                .ifBlank { json.optString("error", "") }
                .ifBlank { "回复生成失败，请重试" }
        } catch (_: Exception) {
            rawMessage
        }
    }

    private fun startAutoScrollDuringTyping() {
        val scrollRunnable = object : Runnable {
            override fun run() {
                scrollToBottom()
                if (isWaitingForResponse || chatAdapter.isTyping()) handler.postDelayed(this, 100)
            }
        }
        handler.post(scrollRunnable)
    }

    private fun scrollToBottom() {
        rvChat?.let { rv ->
            if (chatAdapter.itemCount > 0) rv.scrollToPosition(chatAdapter.itemCount - 1)
        }
        scrollView?.post { scrollView?.fullScroll(View.FOCUS_DOWN) }
    }

    override fun onDestroyView() {
        recordingEpoch++
        finishRecording(send = false)
        streamRequestId++
        streamCall?.cancel()
        streamCall = null
        isWaitingForResponse = false
        handler.removeCallbacksAndMessages(null)
        chatAdapter.cancelTypingAnimation()
        chatAdapter.cancelStreamingAnimation()
        isRecording = false
        try { audioRecord?.stop() } catch (_: Exception) {}
        try { audioRecord?.release() } catch (_: Exception) {}
        audioRecord = null
        recordingThread = null
        layoutHotQuestions = null; rvChat = null; scrollView = null
        layoutInputMode = null; layoutVoiceMode = null
        etMessage = null; btnVoiceInput = null; btnSend = null
        btnHoldToSpeak = null; btnKeyboard = null; permissionGrantedCallback = null
        super.onDestroyView()
    }
}
