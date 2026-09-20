package com.example.aisia.ble

/** Owner-scoped listeners. All manager access is confined to its main-thread lane. */
class OwnedListeners<T> {
    private val entries = linkedMapOf<Any, T>()
    operator fun set(owner: Any, listener: T) { entries[owner] = listener }
    fun remove(owner: Any) { entries.remove(owner) }
    val values: List<T> get() = entries.values.toList()
}
