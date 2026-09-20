package com.example.aisia.ble.k7

import android.util.Base64
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.util.UUID

object K7Protocol {
    val SERVICE: UUID = UUID.fromString("6b7a0001-78c3-4f2e-9c2f-3ecbc2d74680")
    val COMMAND: UUID = UUID.fromString("6b7a0002-78c3-4f2e-9c2f-3ecbc2d74680")
    val NOTIFY: UUID = UUID.fromString("6b7a0003-78c3-4f2e-9c2f-3ecbc2d74680")
    val STATUS: UUID = UUID.fromString("6b7a0004-78c3-4f2e-9c2f-3ecbc2d74680")
    val CCCD: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
    data class Capabilities(val scan: Boolean, val connect: Boolean, val encrypted: Boolean, val busy: Boolean, val session: Int, val receiveCredentials: Boolean = false)
    data class AccessPoint(val ssidB64: String, val ssid: String, val rssi: Int, val security: String, val band: String, val channel: Int) {
        val hidden get() = ssidB64.isEmpty()
    }
    fun json(bytes: ByteArray): JSONObject {
        val text = Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString()
        return JSONObject(text)
    }
    fun capabilities(obj: JSONObject): Capabilities {
        require(obj.opt("v") == 1) { "不支持的设备协议版本" }
        return Capabilities(obj.getBoolean("scan"), obj.getBoolean("connect"), obj.getBoolean("encrypted"),
            obj.getBoolean("busy"), obj.getInt("session"), obj.opt("receive_credentials") == true)
    }
    fun request(id: Int, command: String, ap: AccessPoint? = null, password: String = ""): ByteArray {
        require(id in 1..65535)
        require(command in setOf("scan", "status", "submit_credentials", "connect")) { "当前协议未开放联网命令" }
        val obj = JSONObject().put("v", 1).put("id", id).put("cmd", command)
        if (command == "submit_credentials" || command == "connect") {
            require(ap != null && !ap.hidden) { "请选择有名称的网络" }
            require(validSsid(ap.ssidB64)) { "网络标识无效，请重新扫描" }
            require(validPassword(password)) { "密码须为8至63个可打印ASCII字符" }
            obj.put("ssid_b64", ap.ssidB64).put("password", password)
        }
        val bytes = (obj.toString() + "\n").toByteArray(Charsets.UTF_8)
        require(bytes.size <= 512) { "网络名称或密码过长" }
        return bytes
    }
    fun accessPoint(
        obj: JSONObject,
        decode: (String) -> ByteArray = { Base64.decode(it, Base64.NO_WRAP) },
        encode: (ByteArray) -> String = { Base64.encodeToString(it, Base64.NO_WRAP) }
    ): AccessPoint {
        val encoded = obj.getString("ssid_b64")
        require(encoded.length <= 44 && Regex("[A-Za-z0-9+/]*={0,2}").matches(encoded))
        val bytes = decode(encoded)
        require(bytes.size <= 32 && encode(bytes) == encoded)
        val display = if (bytes.isEmpty()) "隐藏网络" else try {
            Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString()
                .replace(Regex("[\\p{Cntrl}]"), "�")
        } catch (_: Exception) { "非 UTF-8 网络 (${encoded.take(8)}…)" }
        return AccessPoint(encoded, display, obj.getInt("rssi"), obj.getString("security"), obj.getString("band"), obj.getInt("channel"))
    }
    const val CONNECT_TIMEOUT_MS = 120000L
    const val SCAN_TIMEOUT_MS = 60000L
    fun validIp(raw: String?): Boolean {
        if (raw == null || !Regex("(?:[0-9]{1,3}\\.){3}[0-9]{1,3}").matches(raw)) return false
        val parts = raw.split('.')
        if (parts.any { it.length > 1 && it.startsWith("0") }) return false
        val octets = parts.map { it.toInt() }
        return octets.all { it in 0..255 } && octets.any { it != 0 } && octets.any { it != 255 }
    }
    fun networkStatus(obj: JSONObject, id: Int, session: Int): Boolean {
        require(obj.opt("v") == 1 && obj.opt("id") == id && obj.opt("session") == session)
        require(obj.optString("event") == "status" && obj.opt("wifi_connected") is Boolean)
        val online = obj.getBoolean("wifi_connected")
        require(!online || validIp(obj.opt("ip") as? String))
        return online
    }
    fun validPassword(password: String): Boolean = password.length in 8..63 && password.all { it.code in 0x20..0x7e }
    fun validSsid(encoded: String): Boolean {
        if (!Regex("(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?").matches(encoded)) return false
        val padding = encoded.takeLastWhile { it == '=' }.length
        if (encoded.length / 4 * 3 - padding !in 1..32) return false
        val alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        val last = alphabet.indexOf(encoded[encoded.length - padding - 1])
        return when (padding) { 2 -> last and 15 == 0; 1 -> last and 3 == 0; else -> true }
    }
    fun isTerminalEvent(event: String) = event in setOf("scan_done", "error", "credentials_received", "status", "wifi_connected")
    fun credentialsReceived(obj: JSONObject, id: Int, session: Int): Boolean =
        obj.opt("v") == 1 && obj.opt("id") == id && obj.opt("session") == session &&
            obj.optString("event") == "credentials_received" &&
            obj.opt("validated") == true && obj.opt("stored") == false &&
            obj.opt("wifi_connected") == false && obj.has("ip") && obj.isNull("ip")
    fun wifiConnected(obj: JSONObject, id: Int, session: Int): Boolean =
        obj.opt("v") == 1 && obj.opt("id") == id && obj.optString("event") == "wifi_connected" &&
            obj.opt("session") == session &&
            obj.opt("wifi_connected") == true && validIp(obj.opt("ip") as? String)
    fun connected(obj: JSONObject): Boolean = obj.opt("wifi_connected") == true && validIp(obj.optString("ip"))
    class JsonLines {
        private val buffer = ByteArrayOutputStream()
        val hasPartial get() = buffer.size() > 0
        fun reset() { buffer.reset() }
        fun feed(bytes: ByteArray): List<ByteArray> {
            val lines = mutableListOf<ByteArray>()
            for (byte in bytes) {
                if (byte == 10.toByte()) {
                    if (buffer.size() > 0) lines.add(buffer.toByteArray())
                    buffer.reset()
                } else {
                    require(buffer.size() < 4096) { "设备消息过长" }
                    buffer.write(byte.toInt())
                }
            }
            return lines
        }
    }
    class ScanAccumulator {
        var id: Int? = null
            private set
        private val rows = mutableListOf<AccessPoint>()
        fun start(value: Int) { require(id == null && value in 1..65535); id = value }
        fun add(value: Int, ap: AccessPoint) { require(id == value && rows.size < 64); rows.add(ap) }
        fun finish(value: Int, count: Int): List<AccessPoint> {
            require(id == value && count == rows.size) { "Wi-Fi列表不完整，请重试" }
            // Validate raw count before grouping; keep original SSID encoding for connect.
            return rows.sortedByDescending { it.rssi }.distinctBy { Triple(it.ssidB64, it.band, it.security) }
        }
    }
}
