package com.kkkkikun.openfeedback.core

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * The single entry point for sending feedback.
 *
 * The rule this class enforces: the SDK never reports success until the
 * server has actually stored the feedback. When the network is unavailable
 * the submission is written to the on-disk queue and the caller is told it
 * is queued, not sent.
 */
class FeedbackSubmitter(
    private val context: Context,
    private val client: FeedbackClient,
) {
    private val queue by lazy { FeedbackQueue(context) }

    /**
     * Sends one submission.
     *
     * @return [SubmitOutcome.Success] when the server stored it,
     *   [SubmitOutcome.Queued] when it is saved for a later retry, or
     *   [SubmitOutcome.Rejected] when the server refused it.
     */
    suspend fun submit(submission: FeedbackSubmission): SubmitOutcome =
        withContext(Dispatchers.IO) {
            when (val outcome = client.apiClient.submit(client.config.appId, submission)) {
                is SubmitOutcome.Success -> outcome
                is SubmitOutcome.Rejected -> outcome
                is SubmitOutcome.Queued -> {
                    val stored = queue.enqueue(client.config.appId, submission)
                    if (stored) {
                        FeedbackUploadWorker.enqueue(context)
                        SubmitOutcome.Queued(outcome.reason)
                    } else {
                        SubmitOutcome.Rejected("网络不可用，且本地缓存失败")
                    }
                }
            }
        }

    /** How many submissions are waiting for connectivity. */
    fun queuedCount(): Int = queue.size()

    /**
     * Drops a queued submission the user no longer wants to send.
     *
     * @return true when something was removed.
     */
    suspend fun cancel(submissionId: String): Boolean = queue.remove(submissionId)

    /** The submission ids currently waiting. */
    fun pendingIds(): List<String> = queue.pendingIds()

    /** Asks the worker to try sending the queue now. */
    fun retryNow() = FeedbackUploadWorker.enqueue(context)
}
