package com.example.aisia.ble

import org.junit.Assert.*
import org.junit.Test

class OwnedListenersTest {
    @Test fun closingWifiPageDoesNotRemoveWorkSessionListener() {
        val listeners = OwnedListeners<(String) -> Unit>()
        val wifiPage = Any()
        val workSession = Any()
        val received = mutableListOf<String>()
        listeners[wifiPage] = { received.add("wifi:$it") }
        listeners[workSession] = { received.add("work:$it") }
        listeners.remove(wifiPage)
        listeners.values.forEach { it("running") }
        assertEquals(listOf("work:running"), received)
    }
    @Test fun reconnectingOwnerReplacesOnlyItsOldCallback() {
        val listeners = OwnedListeners<() -> Unit>()
        val owner = Any()
        var oldCalls = 0
        var newCalls = 0
        listeners[owner] = { oldCalls++ }
        listeners[owner] = { newCalls++ }
        listeners.values.forEach { it() }
        assertEquals(0, oldCalls)
        assertEquals(1, newCalls)
    }
    @Test fun removingListenerWhileDispatchingDoesNotCrash() {
        val listeners = OwnedListeners<() -> Unit>()
        val first = Any()
        val second = Any()
        listeners[first] = { listeners.remove(first) }
        listeners[second] = {}
        listeners.values.forEach { it() }
        assertEquals(1, listeners.values.size)
    }
}
