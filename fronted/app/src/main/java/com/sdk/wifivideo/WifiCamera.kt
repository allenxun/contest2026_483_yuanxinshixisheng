package com.sdk.wifivideo

import android.content.Context
import android.util.Log
import java.io.File

/**
 * WiFi 摄像头控制类
 *
 * 包路径必须为 com.sdk.wifivideo，因为 .so 中的 JNI 函数注册在此包下。
 * JNI 命名规则：
 *   Java_包名_类名_方法名
 *   Java_com_sdk_wifivideo_WifiCamera_nativeCreateCamera
 *
 * 摄像头配置：
 *   IP: 192.168.100.1
 *   视频端口: 10900
 *   协议: RTP/AVP 26 (MJPEG)
 */
class WifiCamera {

    companion object {
        private const val TAG = "WifiCamera"

        /** native 库是否加载成功 */
        @JvmStatic
        var isLibraryLoaded: Boolean = false
            private set

        // 加载底层 so 库（只在第一次创建实例时加载）
        @JvmStatic
        private var librariesLoaded = false

        @Synchronized
        @JvmStatic
        fun ensureLibrariesLoaded(): Boolean {
            if (librariesLoaded) return isLibraryLoaded
            librariesLoaded = true

            val logs = StringBuilder()

            // 按依赖顺序加载 FFmpeg 库（很多设备自带，可能不需要）
            val ffmpegLibs = listOf(
                "avutil", "swresample", "avcodec",
                "avformat", "avfilter", "swscale", "postproc"
            )
            for (lib in ffmpegLibs) {
                try {
                    System.loadLibrary(lib)
                    Log.d(TAG, "已加载 FFmpeg 库: $lib")
                    logs.append("[OK] $lib\n")
                } catch (e: UnsatisfiedLinkError) {
                    Log.w(TAG, "FFmpeg 库不存在（非必需）: $lib - ${e.message}")
                    logs.append("[SKIP] $lib: ${e.message}\n")
                } catch (e: Exception) {
                    Log.w(TAG, "加载 FFmpeg 库异常: $lib - ${e.message}")
                    logs.append("[ERR] $lib: ${e.message}\n")
                }
            }

            // 加载 wificamera 主库（必需！）
            try {
                System.loadLibrary("wificamera")
                isLibraryLoaded = true
                Log.i(TAG, "✓ wificamera 库加载成功")
                logs.append("[OK] wificamera\n")
            } catch (e: UnsatisfiedLinkError) {
                isLibraryLoaded = false
                Log.e(TAG, "✗ wificamera 库加载失败: ${e.message}", e)
                logs.append("[FAIL] wificamera: ${e.message}\n")
            } catch (e: Exception) {
                isLibraryLoaded = false
                Log.e(TAG, "✗ wificamera 库加载异常: ${e.message}", e)
                logs.append("[ERR] wificamera: ${e.message}\n")
            }

            Log.i(TAG, "库加载日志:\n$logs")
            return isLibraryLoaded
        }

        // ========== JNI Native 方法声明（静态方法）==========
        // 注意：native 方法必须放在 companion object 中并标记 @JvmStatic
        // 这对应 .so 中的静态 JNI 函数：
        //   Java_com_sdk_wifivideo_WifiCamera_nativeCreateCamera(JNIEnv *env, jclass clazz, jstring sdpPath)
        // 大多数硬件 SDK 采用静态方法设计

        @JvmStatic
        private external fun nativeCreateCamera(sdpPath: String): Long

        @JvmStatic
        private external fun nativeDestroyCamera(cameraId: Long)

        @JvmStatic
        private external fun nativeStartPreview(cameraId: Long): Boolean

        @JvmStatic
        private external fun nativeStopPreview(cameraId: Long)

        @JvmStatic
        private external fun nativeGetFrameBuffer(cameraId: Long): ByteArray?

        @JvmStatic
        private external fun nativeSetCameraLed(cameraId: Long, ledIndex: Int)

        @JvmStatic
        private external fun nativeGetShuifen(cameraId: Long): Int

        @JvmStatic
        private external fun nativeGetDianliang(cameraId: Long): Int

        @JvmStatic
        private external fun nativeHardwareTakePicture(cameraId: Long): Boolean
    }

    // ========== 初始化 ==========
    private val liveHandles = mutableSetOf<Long>()

    init {
        // 确保 native 库已加载
        ensureLibrariesLoaded()
        Log.i(TAG, "WifiCamera 实例创建，库状态: isLibraryLoaded=$isLibraryLoaded")
    }

    /**
     * 创建SDP配置文件（RTP会话描述文件）
     * 该文件描述了视频流的来源、编码格式等信息
     *
     * SDP 格式参考（摄像头期望的格式）：
     *   v=0
     *   o=- 0 0 IN IP4 127.0.0.1
     *   s=No Name
     *   t=0 0
     *   c=IN IP4 192.168.100.1   ← 摄像头IP
     *   m=video 10900 RTP/AVP 26  ← 视频端口+编码
     *   a=rtpmap:26 JPEG/90000
     *   a=recvonly
     *
     * @param context 应用上下文
     * @param localIp 手机自身的IP（连接摄像头WiFi后获取，用于SDP的c行）。
     *                如果传入 null，默认使用 192.168.100.1
     * @return SDP 文件的绝对路径，失败返回空字符串
     */
    fun createSdpFile(context: Context, localIp: String? = null): String {
        return try {
            // IP 配置：优先使用传入的本机IP，否则用默认 192.168.100.1
            val connectIp = localIp ?: "192.168.100.1"

            // 构建标准的 SDP 会话描述
            val sdpContent = buildString {
                append("v=0\n")
                append("o=- 0 0 IN IP4 127.0.0.1\n")
                append("s=No Name\n")
                append("c=IN IP4 $connectIp\n")
                append("t=0 0\n")
                append("m=video 10900 RTP/AVP 26\n")
                append("a=rtpmap:26 JPEG/90000\n")
                append("a=recvonly\n")
            }

            // 创建目录并写入文件
            val sdpDir = File(context.filesDir, "camera")
            if (!sdpDir.exists()) {
                val created = sdpDir.mkdirs()
                Log.d(TAG, "创建目录 ${sdpDir.absolutePath}: $created")
            }

            val sdpFile = File(sdpDir, "session.sdp")
            sdpFile.writeText(sdpContent)
            sdpFile.setReadable(true, false)
            sdpFile.setWritable(true, false)

            Log.i(TAG, "✓ SDP文件已创建: ${sdpFile.absolutePath}")
            Log.i(TAG, "  文件大小: ${sdpFile.length()} bytes")
            Log.i(TAG, "  文件内容:\n$sdpContent")

            sdpFile.absolutePath

        } catch (e: Exception) {
            Log.e(TAG, "✗ 创建SDP文件失败: ${e.message}", e)
            ""
        }
    }

    /**
     * 创建摄像头实例
     * @param sdpPath SDP 文件路径
     * @return 摄像头句柄（>0 表示成功，=0 表示失败）
     */
    @Synchronized
    fun createCamera(sdpPath: String): Long {
        if (!isLibraryLoaded) {
            Log.e(TAG, "createCamera: 库未加载，无法创建摄像头")
            return 0L
        }
        if (sdpPath.isEmpty()) {
            Log.e(TAG, "createCamera: SDP路径为空")
            return 0L
        }

        return try {
            Log.i(TAG, "调用 nativeCreateCamera, sdpPath=$sdpPath")
            val result = nativeCreateCamera(sdpPath)
            if (result != 0L) liveHandles.add(result)
            Log.i(TAG, "nativeCreateCamera 返回: $result (${if (result > 0) "成功" else "失败"})")
            result
        } catch (e: UnsatisfiedLinkError) {
            Log.e(TAG, "nativeCreateCamera JNI 错误: ${e.message}", e)
            0L
        } catch (e: Exception) {
            Log.e(TAG, "nativeCreateCamera 异常: ${e.message}", e)
            0L
        }
    }

    @Synchronized
    fun destroyCamera(cameraId: Long) {
        if (!isLibraryLoaded || cameraId == 0L || cameraId !in liveHandles) return
        try {
            liveHandles.remove(cameraId)
            nativeDestroyCamera(cameraId)
        } catch (e: Exception) {
            Log.e(TAG, "destroyCamera 异常: ${e.message}")
        }
    }

    @Synchronized
    fun startPreview(cameraId: Long): Boolean {
        if (!isLibraryLoaded || cameraId == 0L || cameraId !in liveHandles) return false
        return try {
            nativeStartPreview(cameraId)
        } catch (e: Exception) {
            Log.e(TAG, "startPreview 异常: ${e.message}")
            false
        }
    }

    @Synchronized
    fun stopPreview(cameraId: Long) {
        if (!isLibraryLoaded || cameraId == 0L || cameraId !in liveHandles) return
        try {
            nativeStopPreview(cameraId)
        } catch (e: Exception) { }
    }

    @Synchronized
    fun getFrameBuffer(cameraId: Long): ByteArray? {
        if (!isLibraryLoaded || cameraId == 0L || cameraId !in liveHandles) return null
        return try {
            nativeGetFrameBuffer(cameraId)
        } catch (e: Exception) {
            null
        }
    }

    @Synchronized
    fun setCameraLed(cameraId: Long, ledIndex: Int) {
        if (!isLibraryLoaded || cameraId == 0L || cameraId !in liveHandles) return
        try {
            nativeSetCameraLed(cameraId, ledIndex)
        } catch (e: Exception) { }
    }

    @Synchronized
    fun getShuifen(cameraId: Long): Int {
        if (!isLibraryLoaded || cameraId == 0L || cameraId !in liveHandles) return -1
        return try {
            nativeGetShuifen(cameraId)
        } catch (e: Exception) {
            -1
        }
    }

    @Synchronized
    fun getDianliang(cameraId: Long): Int {
        if (!isLibraryLoaded || cameraId == 0L || cameraId !in liveHandles) return -1
        return try {
            nativeGetDianliang(cameraId)
        } catch (e: Exception) {
            -1
        }
    }

    @Synchronized
    fun hardwareTakePicture(cameraId: Long): Boolean {
        if (!isLibraryLoaded || cameraId == 0L || cameraId !in liveHandles) return false
        return try {
            nativeHardwareTakePicture(cameraId)
        } catch (e: Exception) {
            false
        }
    }
}
