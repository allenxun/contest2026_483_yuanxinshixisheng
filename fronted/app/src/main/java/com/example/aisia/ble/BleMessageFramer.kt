package com.example.aisia.ble

import java.io.ByteArrayOutputStream

/** Incremental UTF-8 framing: JSON objects/arrays, newline text, known standalone replies. */
class BleMessageFramer(private val maxBytes: Int = 65536) {
    private val buffer = ByteArrayOutputStream()
    private var depth = 0
    private var quoted = false
    private var escaped = false
    private var json = false
    private val tokens = setOf("1", "0", "ok", "success", "true", "fail", "failed", "false", "error", "wifi_ok", "connected", "ready", "running", "stopped", "completed")
    fun reset() { buffer.reset(); depth = 0; quoted = false; escaped = false; json = false }
    fun feed(bytes: ByteArray): List<String> {
        val result = mutableListOf<String>()
        fun emit() {
            buffer.toString("UTF-8").trim().takeIf { it.isNotEmpty() }?.let { result.add(it) }
            reset()
        }
        for (byte in bytes) {
            val c = byte.toInt() and 255
            if (buffer.size() == 0 && (c == 10 || c == 13 || c == 32)) continue
            if (buffer.size() >= maxBytes) { reset(); return result }
            if (buffer.size() == 0) json = c == 123 || c == 91
            if (!json && c == 10) { emit(); continue }
            buffer.write(c)
            if (json) {
                if (quoted) {
                    if (escaped) escaped = false
                    else if (c == 92) escaped = true
                    else if (c == 34) quoted = false
                } else {
                    when (c) {
                        34 -> quoted = true
                        123, 91 -> depth++
                        125, 93 -> depth--
                    }
                    if (depth == 0) emit()
                }
            }
        }
        if (!json && buffer.size() in 1..16 && buffer.toString("UTF-8").trim().lowercase() in tokens) emit()
        return result
    }
}
