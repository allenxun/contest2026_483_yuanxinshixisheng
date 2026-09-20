package com.example.aisia.ble.k7

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.util.Base64

class K7ProtocolTest {
    private fun ap(encoded: String = "TGFuc2Vl", band: String = "2.4G", rssi: Int = -45) =
        K7Protocol.accessPoint(JSONObject().put("ssid_b64", encoded).put("rssi", rssi)
            .put("security", "rsn").put("band", band).put("channel", 1),
            { Base64.getDecoder().decode(it) }, { Base64.getEncoder().encodeToString(it) })
    @Test fun utf8IsDecodedOnlyAfterLfAcrossEveryByte() {
        val json = """{"v":1,"id":2,"event":"ap","label":"中文"}"""
        val framing = K7Protocol.JsonLines()
        val frames = mutableListOf<ByteArray>()
        json.toByteArray().forEach { frames.addAll(framing.feed(byteArrayOf(it))) }
        assertTrue(frames.isEmpty())
        frames.addAll(framing.feed(byteArrayOf(10)))
        assertEquals("中文", K7Protocol.json(frames.single()).getString("label"))
    }
    @Test fun severalJsonLinesInOneDelivery() {
        assertEquals(2, K7Protocol.JsonLines().feed("{}\n{}\n".toByteArray()).size)
    }
    @Test fun countIsCheckedBeforeDeduplication() {
        val scan = K7Protocol.ScanAccumulator()
        scan.start(7); scan.add(7, ap(rssi = -60)); scan.add(7, ap(rssi = -40))
        val result = scan.finish(7, 2)
        assertEquals(1, result.size); assertEquals(-40, result.single().rssi)
    }
    @Test(expected = IllegalArgumentException::class)
    fun missingRowCannotCompleteScan() {
        val scan = K7Protocol.ScanAccumulator()
        scan.start(7); scan.add(7, ap()); scan.finish(7, 2)
    }
    @Test(expected = IllegalArgumentException::class)
    fun wrongTransactionCannotAddRow() {
        val scan = K7Protocol.ScanAccumulator(); scan.start(7); scan.add(8, ap())
    }
    @Test fun sameSsidDifferentBandIsRetained() {
        val scan = K7Protocol.ScanAccumulator()
        scan.start(7); scan.add(7, ap()); scan.add(7, ap(band = "5G"))
        assertEquals(2, scan.finish(7, 2).size)
    }
    @Test fun hiddenAndNonUtf8NamesKeepTheirOriginalIdentity() {
        assertTrue(ap("").hidden)
        val network = ap("/w==")
        assertEquals("/w==", network.ssidB64); assertTrue(network.ssid.startsWith("非 UTF-8"))
    }
    @Test fun credentialsUseOriginalBase64AndPreserveAsciiWhitespace() {
        val password = "  test\"\\password  "
        val bytes = K7Protocol.request(101, "submit_credentials", ap(), password)
        assertEquals(10.toByte(), bytes.last())
        val obj = K7Protocol.json(bytes)
        assertEquals(1, obj.getInt("v")); assertEquals(101, obj.getInt("id"))
        assertEquals("submit_credentials", obj.getString("cmd")); assertEquals("TGFuc2Vl", obj.getString("ssid_b64"))
        assertEquals(password, obj.getString("password")); assertFalse(obj.has("pwd"))
    }
    @Test(expected = IllegalArgumentException::class)
    fun oversizedCredentialsAreRejectedBeforeWriting() {
        K7Protocol.request(1, "submit_credentials", ap(), "中".repeat(512))
    }
    @Test fun oldFirmwareCapabilityIsNotTreatedAsConnectSupport() {
        val caps = K7Protocol.capabilities(JSONObject("""{"v":1,"scan":true,"connect":false,"encrypted":true,"busy":false,"session":31}"""))
        assertTrue(caps.scan); assertFalse(caps.connect); assertTrue(caps.encrypted)
    }
    @Test(expected = IllegalArgumentException::class)
    fun unknownVersionIsRejected() {
        K7Protocol.capabilities(JSONObject("""{"v":2,"scan":true,"connect":true,"encrypted":true,"busy":false,"session":31}"""))
    }
    @Test fun successNeedsExplicitWifiFlagAndUsableIp() {
        assertFalse(K7Protocol.connected(JSONObject("""{"code":0,"result":1,"ip":"192.168.1.2"}""")))
        assertFalse(K7Protocol.connected(JSONObject("""{"wifi_connected":true,"ip":null}""")))
        assertFalse(K7Protocol.connected(JSONObject("""{"wifi_connected":true,"ip":"0.0.0.0"}""")))
        assertFalse(K7Protocol.connected(JSONObject("""{"wifi_connected":false,"ip":"192.168.1.2"}""")))
        assertTrue(K7Protocol.connected(JSONObject("""{"wifi_connected":true,"ip":"192.168.1.2"}""")))
    }

    @Test fun receiveCapabilityIsIndependentOfConnectCapability() {
        val caps = K7Protocol.capabilities(JSONObject("""{"v":1,"scan":true,"receive_credentials":true,"connect":false,"encrypted":true,"busy":false,"session":25}"""))
        assertTrue(caps.receiveCredentials)
        assertFalse(caps.connect)
        val old = K7Protocol.capabilities(JSONObject("""{"v":1,"scan":true,"connect":false,"encrypted":true,"busy":false,"session":25}"""))
        assertFalse(old.receiveCredentials)
    }
    @Test fun passwordRulesFollowAsciiByteBoundsWithoutTrimming() {
        assertTrue(K7Protocol.validPassword("12345678"))
        assertTrue(K7Protocol.validPassword("x".repeat(63)))
        assertTrue(K7Protocol.validPassword("  pass word  "))
        assertFalse(K7Protocol.validPassword("short"))
        assertFalse(K7Protocol.validPassword("x".repeat(64)))
        assertFalse(K7Protocol.validPassword("中文password"))
        assertFalse(K7Protocol.validPassword("password\n"))
    }
    @Test fun receiptRequiresSameTransactionSessionAndExplicitReceiptFlags() {
        val receipt = JSONObject("""{"v":1,"id":103,"session":25,"event":"credentials_received","validated":true,"stored":false,"wifi_connected":false,"ip":null}""")
        assertTrue(K7Protocol.credentialsReceived(receipt, 103, 25))
        assertFalse(K7Protocol.connected(receipt))
        assertFalse(K7Protocol.credentialsReceived(receipt, 104, 25))
        assertFalse(K7Protocol.credentialsReceived(receipt, 103, 26))
        for (key in listOf("session", "validated", "stored", "wifi_connected", "ip")) {
            val incomplete = JSONObject(receipt.toString()); incomplete.remove(key)
            assertFalse(K7Protocol.credentialsReceived(incomplete, 103, 25))
        }
        receipt.put("validated", false)
        assertFalse(K7Protocol.credentialsReceived(receipt, 103, 25))
    }
    @Test fun connectCommandAndRealSuccessEvent() {
        val request = K7Protocol.json(K7Protocol.request(103, "connect", ap(), "EXAMPLE_ONLY_123"))
        assertEquals("connect", request.getString("cmd"))
        val result = JSONObject("""{"v":1,"id":103,"session":25,"event":"wifi_connected","wifi_connected":true,"ip":"192.168.1.10"}""")
        assertTrue(K7Protocol.wifiConnected(result, 103, 25))
        assertFalse(K7Protocol.wifiConnected(result, 104, 25))
        assertFalse(K7Protocol.wifiConnected(result, 103, 26))
        result.put("event", "wifi_connecting")
        assertFalse(K7Protocol.wifiConnected(result, 103, 25))
        result.put("event", "credentials_received")
        assertFalse(K7Protocol.wifiConnected(result, 103, 25))
        result.put("event", "wifi_connected").put("ip", "0.0.0.0")
        assertFalse(K7Protocol.wifiConnected(result, 103, 25))
    }
    @Test fun onlyCanonicalNonEmptySsidCanBeSubmitted() {
        assertTrue(K7Protocol.validSsid("TGFuc2Vl"))
        assertFalse(K7Protocol.validSsid(""))
        assertFalse(K7Protocol.validSsid("===="))
        assertFalse(K7Protocol.validSsid("Zh=="))
        assertFalse(K7Protocol.validSsid(Base64.getEncoder().encodeToString(ByteArray(33))))
    }
    @Test fun successRequiresSessionAndExplicitFlag() {
        val full = JSONObject("""{"v":1,"id":101,"session":7,"event":"wifi_connected","wifi_connected":true,"ip":"10.3.0.214","stored":false}""")
        assertTrue(K7Protocol.wifiConnected(full,101,7))
        for (key in listOf("session","wifi_connected","ip")) {
            val copy = JSONObject(full.toString()); copy.remove(key)
            assertFalse(K7Protocol.wifiConnected(copy,101,7))
        }
        full.put("wifi_connected",false)
        assertFalse(K7Protocol.wifiConnected(full,101,7))
    }
    @Test fun ipv4OnlyAndInvalidAddressesRejected() {
        for (ip in listOf("::1","::","0.0.0.0","255.255.255.255","256.1.1.1","1.2.3","01.2.3.4"," 10.0.0.1")) assertFalse(ip,K7Protocol.validIp(ip))
        assertTrue(K7Protocol.validIp("10.3.0.214"))
        assertTrue(K7Protocol.validIp("192.168.1.100"))
    }
    @Test fun statusRestoresWithNewSession() {
        val state=JSONObject("""{"v":1,"id":102,"session":8,"event":"status","wifi_connected":true,"ip":"10.3.0.214"}""")
        assertTrue(K7Protocol.networkStatus(state,102,8))
        state.put("wifi_connected",false).put("ip",JSONObject.NULL)
        assertFalse(K7Protocol.networkStatus(state,102,8))
    }
    @Test(expected=IllegalArgumentException::class) fun statusRejectsPreviousSession() {
        K7Protocol.networkStatus(JSONObject("""{"v":1,"id":102,"session":7,"event":"status","wifi_connected":true,"ip":"10.3.0.214"}"""),102,8)
    }
    @Test(expected=IllegalArgumentException::class) fun statusRejectsMissingSuccessIp() {
        K7Protocol.networkStatus(JSONObject("""{"v":1,"id":102,"session":8,"event":"status","wifi_connected":true}"""),102,8)
    }
    @Test fun deadlinesFollowHandover() {
        assertEquals(120000L,K7Protocol.CONNECT_TIMEOUT_MS)
        assertEquals(60000L,K7Protocol.SCAN_TIMEOUT_MS)
        assertFalse(K7Protocol.isTerminalEvent("wifi_connecting"))
    }
}
