package com.kkkkikun.openfeedback.core

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.DataOutputStream
import java.io.IOException
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID

/**
 * The HTTP client for the OpenFeedback API.
 *
 * `HttpURLConnection` is used on purpose: it is part of the Android
 * framework, so the SDK adds no third-party dependency to the host app and
 * cannot cause a version conflict with OkHttp or Retrofit.
 */
class FeedbackApiClient(
    private val endpoint: String,
    private val connectTimeoutMs: Int = 15_000,
    private val readTimeoutMs: Int = 30_000,
) {

    /**
     * Submits one feedback item.
     *
     * Returns [SubmitOutcome.Success] when the server stored it,
     * [SubmitOutcome.Rejected] when the server refused it in a way that
     * retrying cannot fix (bad type, unknown app, too many attachments), and
     * [SubmitOutcome.Queued] for transport failures, which are worth retrying.
     */
    suspend fun submit(appId: String, submission: FeedbackSubmission): SubmitOutcome =
        withContext(Dispatchers.IO) {
            val base = endpoint.trimEnd('/')
            val url = URL("$base/api/v1/feedback")
            var connection: HttpURLConnection? = null
            try {
                connection = (url.openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    doOutput = true
                    connectTimeout = connectTimeoutMs
                    readTimeout = readTimeoutMs
                    setRequestProperty("Content-Type", "multipart/form-data; boundary=$BOUNDARY")
                    setRequestProperty("Accept", "application/json")
                    setRequestProperty("User-Agent", userAgent())
                }

                writeMultipart(connection, submission.toPayloadMap(appId), submission.attachments)

                val status = connection.responseCode
                if (status in 200..299) {
                    val body = connection.inputStream.readTextOrEmpty()
                    val json = runCatching { JSONObject(body) }.getOrNull()
                    SubmitOutcome.Success(
                        SubmitResult(
                            feedbackId = json?.optLong("feedback_id", 0L) ?: 0L,
                            submissionId = json?.optString("submission_id")
                                ?.takeIf { it.isNotBlank() }
                                ?: submission.submissionId,
                            duplicate = json?.optBoolean("duplicate", false) ?: false,
                        )
                    )
                } else {
                    val errorBody = connection.errorStream.readTextOrEmpty()
                    val message = parseError(errorBody) ?: "服务暂时不可用（HTTP $status）"
                    // 4xx means the payload itself is wrong; retrying is futile.
                    if (status in 400..499 && status != 408 && status != 429) {
                        SubmitOutcome.Rejected(message)
                    } else {
                        SubmitOutcome.Queued(message)
                    }
                }
            } catch (e: IOException) {
                SubmitOutcome.Queued(e.message ?: "网络不可用")
            } catch (e: Exception) {
                SubmitOutcome.Queued(e.message ?: "提交失败")
            } finally {
                connection?.disconnect()
            }
        }

    /** Sends a health check. Used by the SDK's connectivity probe. */
    suspend fun health(): Boolean = withContext(Dispatchers.IO) {
        try {
            val url = URL("${endpoint.trimEnd('/')}/api/v1/health")
            val connection = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = 5_000
                readTimeout = 5_000
            }
            val ok = connection.responseCode in 200..299
            connection.disconnect()
            ok
        } catch (e: Exception) {
            false
        }
    }

    private fun writeMultipart(
        connection: HttpURLConnection,
        payload: Map<String, Any?>,
        attachments: List<Attachment>,
    ) {
        DataOutputStream(connection.outputStream).use { out ->
            // The metadata travels as one JSON string, so every client sends
            // the same shape.
            writeField(out, "payload", JSONObject(payload as Map<*, *>).toString())
            attachments.forEach { attachment ->
                out.writeBytes("--$BOUNDARY\r\n")
                out.writeBytes(
                    "Content-Disposition: form-data; name=\"attachments\"; filename=\"${attachment.fileName}\"\r\n"
                )
                out.writeBytes("Content-Type: ${attachment.mimeType}\r\n\r\n")
                out.write(attachment.bytes)
                out.writeBytes("\r\n")
            }
            out.writeBytes("--$BOUNDARY--\r\n")
            out.flush()
        }
    }

    private fun writeField(out: DataOutputStream, name: String, value: String) {
        out.writeBytes("--$BOUNDARY\r\n")
        out.writeBytes("Content-Disposition: form-data; name=\"$name\"\r\n\r\n")
        out.write(value.toByteArray(Charsets.UTF_8))
        out.writeBytes("\r\n")
    }

    private fun parseError(body: String): String? {
        if (body.isBlank()) return null
        return runCatching {
            val json = JSONObject(body)
            json.optString("detail").takeIf { it.isNotBlank() }
        }.getOrNull()
    }

    private fun userAgent(): String =
        "OpenFeedback-Android/${BuildConfig.SDK_VERSION} (Android)"

    companion object {
        // Not a `const val`: the boundary carries a random suffix, so it is
        // computed once per client instance.
        private val BOUNDARY: String =
            "----OpenFeedbackBoundary${UUID.randomUUID().toString().replace("-", "")}"

        /** A fresh submission id. */
        fun newSubmissionId(): String = UUID.randomUUID().toString()
    }
}

private fun InputStream.readTextOrEmpty(): String =
    runCatching {
        BufferedInputStream(this).use { it.readBytes().toString(Charsets.UTF_8) }
    }.getOrDefault("")

/** Convenience for JSON arrays in tests. */
internal fun JSONArray.toStringList(): List<String> =
    (0 until length()).map { optString(it) }
