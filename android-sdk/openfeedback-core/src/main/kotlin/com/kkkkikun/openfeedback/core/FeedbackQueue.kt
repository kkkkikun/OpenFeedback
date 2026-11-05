package com.kkkkikun.openfeedback.core

import android.content.Context
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

/**
 * The on-disk queue for feedback that could not be sent yet.
 *
 * Each queued item is a folder under the app's private directory:
 *
 *   noBackupFilesDir/openfeedback/queue/<submissionId>/
 *       submission.json    the metadata
 *       attachment-0.jpg   the screenshots, as separate files
 *
 * Image bytes are never put in WorkManager's `Data`, which is limited to a
 * few kilobytes. The queue holds plain files so a queued submission
 * survives a process death.
 */
class FeedbackQueue(
    context: Context,
    private val maxItems: Int = DEFAULT_MAX_ITEMS,
) {
    private val root: File = File(
        context.noBackupFilesDir,
        "openfeedback/queue",
    ).apply { mkdirs() }

    /** How many submissions are waiting. */
    fun size(): Int = root.listFiles()?.count { it.isDirectory } ?: 0

    /** The submission ids currently queued, oldest first. */
    fun pendingIds(): List<String> =
        root.listFiles()
            ?.filter { it.isDirectory }
            ?.sortedBy { it.lastModified() }
            ?.map { it.name }
            ?: emptyList()

    /**
     * Stores a submission for later.
     *
     * The submission id stays the same, so a later retry is still
     * idempotent on the server.
     */
    suspend fun enqueue(appId: String, submission: FeedbackSubmission): Boolean = withContext(Dispatchers.IO) {
        try {
            if (size() >= maxItems) {
                // Drop the oldest entry so a stuck queue cannot fill the disk.
                val oldest = root.listFiles()
                    ?.filter { it.isDirectory }
                    ?.minByOrNull { it.lastModified() }
                oldest?.deleteRecursively()
                Log.w(TAG, "queue is full; dropped the oldest entry")
            }

            val dir = File(root, submission.submissionId).apply { mkdirs() }
            val metadata = JSONObject(submission.toPayloadMap(appId)).toString()
            File(dir, METADATA_FILE).writeText(metadata, Charsets.UTF_8)

            submission.attachments.forEachIndexed { index, attachment ->
                File(dir, "attachment-$index").writeBytes(attachment.bytes)
            }
            true
        } catch (e: Exception) {
            Log.e(TAG, "could not queue the submission: ${e.message}")
            false
        }
    }

    /**
     * Takes the oldest queued submission.
     *
     * Returns null when the queue is empty. The item stays on disk until
     * [remove] is called, so a crash mid-upload does not lose it.
     */
    suspend fun peek(): QueuedSubmission? = withContext(Dispatchers.IO) {
        val dir = root.listFiles()
            ?.filter { it.isDirectory }
            ?.minByOrNull { it.lastModified() }
            ?: return@withContext null

        runCatching {
            val metadata = JSONObject(File(dir, METADATA_FILE).readText(Charsets.UTF_8))
            val attachments = dir.listFiles()
                ?.filter { it.name.startsWith("attachment-") }
                ?.sortedBy { it.name }
                ?.map { file ->
                    Attachment(
                        fileName = "${file.name.substringAfter('-')}.jpg",
                        mimeType = "image/jpeg",
                        bytes = file.readBytes(),
                    )
                }
                ?: emptyList()

            QueuedSubmission(
                submissionId = dir.name,
                appId = metadata.optString("appId"),
                type = FeedbackType.fromWire(metadata.optString("type")) ?: FeedbackType.OTHER,
                title = metadata.optString("title").takeIf { it.isNotBlank() },
                description = metadata.optString("description"),
                contact = metadata.optString("contact").takeIf { it.isNotBlank() },
                device = DeviceContext(
                    appVersion = metadata.optString("appVersion").takeIf { it.isNotBlank() },
                    appBuild = metadata.optString("appBuild").takeIf { it.isNotBlank() },
                    sdkVersion = metadata.optString("sdkVersion").takeIf { it.isNotBlank() },
                    androidVersion = metadata.optString("androidVersion").takeIf { it.isNotBlank() },
                    apiLevel = metadata.optInt("apiLevel").takeIf { it > 0 },
                    manufacturer = metadata.optString("manufacturer").takeIf { it.isNotBlank() },
                    model = metadata.optString("model").takeIf { it.isNotBlank() },
                    locale = metadata.optString("locale").takeIf { it.isNotBlank() },
                ),
                diagnostics = metadata.optString("diagnostics").takeIf { it.isNotBlank() },
                attachments = attachments,
            )
        }.getOrNull()
    }

    /** Removes a queued submission after it was sent. */
    suspend fun remove(submissionId: String): Boolean = withContext(Dispatchers.IO) {
        File(root, submissionId).deleteRecursively()
    }

    companion object {
        private const val TAG = "OpenFeedbackQueue"
        private const val METADATA_FILE = "submission.json"
        const val DEFAULT_MAX_ITEMS = 20
    }
}

/** A submission that was read back off disk. */
data class QueuedSubmission(
    val submissionId: String,
    val appId: String,
    val type: FeedbackType,
    val title: String?,
    val description: String,
    val contact: String?,
    val device: DeviceContext,
    val diagnostics: String?,
    val attachments: List<Attachment>,
) {
    fun toSubmission(): FeedbackSubmission = FeedbackSubmission(
        submissionId = submissionId,
        type = type,
        title = title,
        description = description,
        contact = contact,
        device = device,
        diagnostics = diagnostics,
        attachments = attachments,
    )
}

/** A fresh submission id, used by the queue and by the form. */
fun newSubmissionId(): String = UUID.randomUUID().toString()

/** Unused helper kept for JSON round-trips in tests. */
internal fun JSONArray.toList(): List<String> = (0 until length()).map { optString(it) }
