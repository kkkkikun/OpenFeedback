package com.kkkkikun.openfeedback.core

/**
 * The contract shared by every OpenFeedback client.
 *
 * The Android SDK, the uni-app component, and the Rust client all speak the
 * same wire format, so a server change is not needed to onboard a new app.
 */

/** The kind of feedback the user is reporting. */
enum class FeedbackType(val wire: String, val label: String) {
    BUG("bug", "Bug"),
    FEATURE("feature", "功能建议"),
    EXPERIENCE("experience", "体验问题"),
    OTHER("other", "其他");

    companion object {
        /**
         * Accepts the four canonical names plus the legacy names OIT-Net-Portal
         * used before OpenFeedback (`issue`, `suggestion`, `ux`, `problem`).
         */
        fun fromWire(value: String): FeedbackType? {
            val key = value.trim().lowercase()
            return when (key) {
                "bug", "issue", "problem" -> BUG
                "feature", "suggestion" -> FEATURE
                "experience", "ux" -> EXPERIENCE
                "other" -> OTHER
                else -> null
            }
        }
    }
}

/** How far a feedback item has been handled. */
enum class FeedbackStatus(val wire: String, val label: String) {
    NEW("NEW", "待处理"),
    IN_PROGRESS("IN_PROGRESS", "处理中"),
    RESOLVED("RESOLVED", "已解决"),
    CLOSED("CLOSED", "已关闭"),
}

/**
 * Device and app context attached to every submission.
 *
 * Nothing here identifies a person: no IMEI, no serial number, no MAC
 * address, no location. The user is told exactly what is sent.
 */
data class DeviceContext(
    val appName: String? = null,
    val appVersion: String? = null,
    val appBuild: String? = null,
    val sdkVersion: String? = null,
    val androidVersion: String? = null,
    val apiLevel: Int? = null,
    val manufacturer: String? = null,
    val model: String? = null,
    val locale: String? = null,
) {
    fun toMap(): Map<String, Any?> = mapOf(
        "appName" to appName,
        "appVersion" to appVersion,
        "appBuild" to appBuild,
        "sdkVersion" to sdkVersion,
        "androidVersion" to androidVersion,
        "apiLevel" to apiLevel,
        "manufacturer" to manufacturer,
        "model" to model,
        "locale" to locale,
    )
}

/** A screenshot the user attached, already compressed and ready to upload. */
data class Attachment(
    val fileName: String,
    val mimeType: String,
    val bytes: ByteArray,
) {
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is Attachment) return false
        return fileName == other.fileName &&
            mimeType == other.mimeType &&
            bytes.contentEquals(other.bytes)
    }

    override fun hashCode(): Int {
        var result = fileName.hashCode()
        result = 31 * result + mimeType.hashCode()
        result = 31 * result + bytes.contentHashCode()
        return result
    }
}

/**
 * One feedback item, ready to be sent.
 *
 * [submissionId] is generated once per attempt and never changes. The server
 * uses it to make a retry idempotent, so a submission that succeeded but
 * whose response was lost does not create a duplicate.
 */
data class FeedbackSubmission(
    val submissionId: String,
    val type: FeedbackType,
    val title: String?,
    val description: String,
    val contact: String?,
    val device: DeviceContext,
    val diagnostics: String?,
    val attachments: List<Attachment> = emptyList(),
) {
    /** The metadata part of the multipart request. */
    fun toPayloadMap(appId: String): Map<String, Any?> {
        val map = linkedMapOf<String, Any?>(
            "appId" to appId,
            "submissionId" to submissionId,
            "type" to type.wire,
            "description" to description,
        )
        title?.let { map["title"] = it }
        contact?.let { map["contact"] = it }
        diagnostics?.let { map["diagnostics"] = it }
        map["appVersion"] = device.appVersion
        map["appBuild"] = device.appBuild
        map["sdkVersion"] = device.sdkVersion
        map["androidVersion"] = device.androidVersion
        map["apiLevel"] = device.apiLevel
        map["manufacturer"] = device.manufacturer
        map["model"] = device.model
        map["locale"] = device.locale
        return map
    }
}

/** The server's answer to a submission. */
data class SubmitResult(
    val feedbackId: Long,
    val submissionId: String,
    val duplicate: Boolean,
)

/** How a submission attempt ended. */
sealed class SubmitOutcome {
    /** The server stored the feedback. */
    data class Success(val result: SubmitResult) : SubmitOutcome()

    /**
     * The network failed or the server refused the request. The item is
     * queued on disk and retried when connectivity returns.
     */
    data class Queued(val reason: String) : SubmitOutcome()

    /** The server rejected the request in a way retrying will not fix. */
    data class Rejected(val message: String) : SubmitOutcome()
}
