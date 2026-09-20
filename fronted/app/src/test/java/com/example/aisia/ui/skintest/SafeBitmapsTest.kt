package com.example.aisia.ui.skintest

import org.junit.Assert.*
import org.junit.Test

class SafeBitmapsTest {
    @Test fun ordinaryPhotosKeepTheirSize() {
        assertEquals(1, SafeBitmaps.sampleSize(1920, 1080))
    }
    @Test fun largePortraitAndLandscapeFitTheSameBound() {
        for ((width, height) in listOf(8000 to 6000, 6000 to 8000, 12000 to 9000)) {
            val sample = SafeBitmaps.sampleSize(width, height)
            assertTrue(width / sample <= 2048)
            assertTrue(height / sample <= 2048)
            assertEquals(0, sample and (sample - 1))
        }
    }
    @Test(expected = IllegalArgumentException::class)
    fun invalidLimitIsRejected() { SafeBitmaps.sampleSize(4000, 3000, 0) }
}
