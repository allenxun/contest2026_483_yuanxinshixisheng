package com.example.aisia.ui.common

import android.os.Handler
import android.os.Looper
import android.os.SystemClock

abstract class PausableCountdown(
    private val total: Long,
    private val interval: Long,
    private val now: () -> Long = { SystemClock.elapsedRealtime() },
    private val schedule: (Runnable, Long) -> Unit = { task, delay -> mainHandler.postDelayed(task, delay); Unit },
    private val unschedule: (Runnable) -> Unit = { mainHandler.removeCallbacks(it) }
) {
    companion object { private val mainHandler by lazy { Handler(Looper.getMainLooper()) } }
    init { require(total > 0 && interval > 0) }
    private var remaining = total
    private var deadline = 0L
    private var running = false
    private val tick = object : Runnable {
        override fun run() {
            if (!running) return
            remaining = (deadline - now()).coerceAtLeast(0L)
            if (remaining == 0L) { running = false; onFinish() }
            else { onTick(remaining); if (running) schedule(this, minOf(interval, remaining)) }
        }
    }
    abstract fun onTick(millisUntilFinished: Long)
    abstract fun onFinish()
    fun start() { cancel(); remaining = total; resume() }
    fun pause() {
        if (!running) return
        // Keep a pending completion for resume when pausing exactly at expiry.
        remaining = (deadline - now()).coerceAtLeast(1L)
        running = false; unschedule(tick)
    }
    fun resume() {
        if (running || remaining <= 0) return
        deadline = now() + remaining; running = true; schedule(tick, 0L)
    }
    fun cancel() { running = false; remaining = 0; unschedule(tick) }
}
