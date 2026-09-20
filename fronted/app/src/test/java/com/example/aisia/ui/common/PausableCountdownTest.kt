package com.example.aisia.ui.common

import org.junit.Assert.*
import org.junit.Test

class PausableCountdownTest {
    private class Clock {
        var time = 0L
        val tasks = mutableMapOf<Runnable, Long>()
        fun post(task: Runnable, delay: Long) { tasks[task] = time + delay }
        fun remove(task: Runnable) { tasks.remove(task) }
        fun advance(delta: Long) {
            val target = time + delta
            while (true) {
                val next = tasks.entries.filter { it.value <= target }.minByOrNull { it.value } ?: break
                time = next.value; tasks.remove(next.key); next.key.run()
            }
            time = target
        }
    }
    @Test fun pausePreservesRemainingTime() {
        val clock = Clock()
        var finishes = 0
        val timer = object : PausableCountdown(1000, 100, { clock.time }, clock::post, clock::remove) {
            override fun onTick(millisUntilFinished: Long) {}
            override fun onFinish() { finishes++ }
        }
        timer.start(); clock.advance(400); timer.pause(); clock.advance(5000)
        assertEquals(0, finishes)
        timer.resume(); clock.advance(599); assertEquals(0, finishes)
        clock.advance(1); assertEquals(1, finishes)
    }
    @Test fun cancelCannotCompleteOrRestartOnResume() {
        val clock = Clock()
        var finishes = 0
        val timer = object : PausableCountdown(1000, 100, { clock.time }, clock::post, clock::remove) {
            override fun onTick(millisUntilFinished: Long) {}
            override fun onFinish() { finishes++ }
        }
        timer.start(); timer.cancel(); timer.resume(); clock.advance(10000)
        assertEquals(0, finishes); assertTrue(clock.tasks.isEmpty())
    }
    @Test fun pausingAtExpiryStillCompletesOnceAfterResume() {
        val clock = Clock()
        var finishes = 0
        val timer = object : PausableCountdown(1000, 100, { clock.time }, clock::post, clock::remove) {
            override fun onTick(millisUntilFinished: Long) {}
            override fun onFinish() { finishes++ }
        }
        timer.start(); clock.time = 1000; timer.pause()
        timer.resume(); clock.advance(1); clock.advance(10000)
        assertEquals(1, finishes)
    }
}
