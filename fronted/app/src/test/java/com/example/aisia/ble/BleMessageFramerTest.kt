package com.example.aisia.ble

import org.junit.Assert.*
import org.junit.Test

class BleMessageFramerTest {
    @Test fun chineseJsonSurvivesEveryByteBoundary() {
        val text = """{"list":[{"ssid":"家庭无线","rssi":-45}]}"""
        val bytes = text.toByteArray(Charsets.UTF_8)
        for (cut in 1 until bytes.size) {
            val parser = BleMessageFramer()
            val output = parser.feed(bytes.copyOfRange(0, cut)) + parser.feed(bytes.copyOfRange(cut, bytes.size))
            assertEquals(listOf(text), output)
        }
    }
    @Test fun prettyJsonAndSeveralFramesStaySeparate() {
        val json = "{\n\"list\": [{\"ssid\":\"A\"}]\n}"
        assertEquals(listOf(json, "ok", "[]"), BleMessageFramer().feed((json + "\nok\n[]").toByteArray()))
    }
    @Test fun bracesAndEscapedQuotesInsideNamesDoNotEndFrame() {
        val json = """{"ssid":"name } [ \"quoted\"","rssi":-50}"""
        assertEquals(listOf(json), BleMessageFramer().feed(json.toByteArray()))
    }
    @Test fun fragmentedTextAndStandaloneReply() {
        val parser = BleMessageFramer()
        assertTrue(parser.feed("run".toByteArray()).isEmpty())
        assertEquals(listOf("running"), parser.feed("ning".toByteArray()))
        assertEquals(listOf("stopped"), parser.feed("stopped".toByteArray()))
    }
    @Test fun oversizedFrameIsDiscardedAndNextPacketRecovers() {
        val parser = BleMessageFramer(32)
        assertTrue(parser.feed(("{\"data\":\"" + "a".repeat(64)).toByteArray()).isEmpty())
        assertEquals(listOf("[]"), parser.feed("[]".toByteArray()))
    }
    @Test fun newRequestDoesNotInheritPartialOldMessage() {
        val parser = BleMessageFramer()
        parser.feed("{\"list\":".toByteArray())
        parser.reset()
        assertEquals(listOf("[]"), parser.feed("[]".toByteArray()))
    }
}
