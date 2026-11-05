package com.kkkkikun.openfeedback.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The wire contract tests.
 *
 * These pin the shape every client relies on. If they change, the uni-app
 * component and the Rust client have to change with them.
 */
class ModelsTest {

    @Test
    fun `canonical types map to their wire names`() {
        assertEquals("bug", FeedbackType.BUG.wire)
        assertEquals("feature", FeedbackType.FEATURE.wire)
        assertEquals("experience", FeedbackType.EXPERIENCE.wire)
        assertEquals("other", FeedbackType.OTHER.wire)
    }

    @Test
    fun `legacy OIT categories are accepted`() {
        assertEquals(FeedbackType.BUG, FeedbackType.fromWire("issue"))
        assertEquals(FeedbackType.FEATURE, FeedbackType.fromWire("suggestion"))
        assertEquals(FeedbackType.EXPERIENCE, FeedbackType.fromWire("ux"))
        assertEquals(FeedbackType.OTHER, FeedbackType.fromWire("other"))
    }

    @Test
    fun `unknown categories are rejected`() {
        assertNull(FeedbackType.fromWire("nonsense"))
        assertNull(FeedbackType.fromWire(""))
    }

    @Test
    fun `the payload carries the fields the server expects`() {
        val submission = FeedbackSubmission(
            submissionId = "abc-123",
            type = FeedbackType.BUG,
            title = "闪退了",
            description = "打开设置页就闪退",
            contact = "someone@example.com",
            device = DeviceContext(
                appVersion = "1.0.0",
                appBuild = "11",
                sdkVersion = "0.1.0",
                androidVersion = "14",
                apiLevel = 34,
                manufacturer = "Xiaomi",
                model = "M2101K6G",
                locale = "zh-CN",
            ),
            diagnostics = null,
        )

        val payload = submission.toPayloadMap("localpixt")

        assertEquals("localpixt", payload["appId"])
        assertEquals("abc-123", payload["submissionId"])
        assertEquals("bug", payload["type"])
        assertEquals("闪退了", payload["title"])
        assertEquals("打开设置页就闪退", payload["description"])
        assertEquals("someone@example.com", payload["contact"])
        assertEquals("1.0.0", payload["appVersion"])
        assertEquals("11", payload["appBuild"])
        assertEquals("0.1.0", payload["sdkVersion"])
        assertEquals("14", payload["androidVersion"])
        assertEquals(34, payload["apiLevel"])
        assertEquals("Xiaomi", payload["manufacturer"])
        assertEquals("M2101K6G", payload["model"])
        assertEquals("zh-CN", payload["locale"])
    }

    @Test
    fun `absent optional fields are not sent as empty strings`() {
        val submission = FeedbackSubmission(
            submissionId = "abc-123",
            type = FeedbackType.OTHER,
            title = null,
            description = "hello",
            contact = null,
            device = DeviceContext(),
            diagnostics = null,
        )

        val payload = submission.toPayloadMap("schoolwall")

        assertNull(payload["title"])
        assertNull(payload["contact"])
        assertNull(payload["diagnostics"])
        assertEquals("schoolwall", payload["appId"])
    }

    @Test
    fun `diagnostics are only sent when the host provides them`() {
        val submission = FeedbackSubmission(
            submissionId = "abc-123",
            type = FeedbackType.OTHER,
            title = null,
            description = "hello",
            contact = null,
            device = DeviceContext(),
            diagnostics = "连接正常",
        )

        assertEquals("连接正常", submission.toPayloadMap("localpixt")["diagnostics"])
    }

    @Test
    fun `submission ids are unique`() {
        val ids = (1..100).map { newSubmissionId() }.toSet()
        assertEquals(100, ids.size)
        assertTrue(ids.all { it.isNotBlank() })
    }

    @Test
    fun `the device context never carries an identifier`() {
        val context = DeviceContext(
            appName = "显影",
            appVersion = "1.0.0",
            appBuild = "11",
            sdkVersion = "0.1.0",
            androidVersion = "14",
            apiLevel = 34,
            manufacturer = "Xiaomi",
            model = "M2101K6G",
            locale = "zh-CN",
        )

        val keys = context.toMap().keys.map { it.lowercase() }
        listOf("imei", "serial", "mac", "macaddress", "location", "latitude", "longitude")
            .forEach { forbidden ->
                assertTrue(
                    "device context must not contain $forbidden",
                    keys.none { it.contains(forbidden) },
                )
            }
    }

    @Test
    fun `attachments compare by content`() {
        val a = Attachment("a.jpg", "image/jpeg", byteArrayOf(1, 2, 3))
        val b = Attachment("a.jpg", "image/jpeg", byteArrayOf(1, 2, 3))
        val c = Attachment("a.jpg", "image/jpeg", byteArrayOf(1, 2, 4))

        assertEquals(a, b)
        assertEquals(a.hashCode(), b.hashCode())
        assertTrue(a != c)
    }

    @Test
    fun `statuses carry the server's names`() {
        assertEquals("NEW", FeedbackStatus.NEW.wire)
        assertEquals("IN_PROGRESS", FeedbackStatus.IN_PROGRESS.wire)
        assertEquals("RESOLVED", FeedbackStatus.RESOLVED.wire)
        assertEquals("CLOSED", FeedbackStatus.CLOSED.wire)
        assertNotNull(FeedbackStatus.valueOf("IN_PROGRESS"))
    }
}
