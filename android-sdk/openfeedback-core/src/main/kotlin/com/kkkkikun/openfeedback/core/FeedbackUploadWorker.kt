package com.kkkkikun.openfeedback.core

import android.content.Context
import android.util.Log
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

/**
 * Sends whatever is waiting in the offline queue.
 *
 * The work is registered with a network constraint, so it only runs when
 * there is connectivity. Failures are retried with exponential backoff.
 */
class FeedbackUploadWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val client = FeedbackRuntime.client
        if (client == null) {
            // No client in this process: the host app has not configured
            // feedback yet, so there is nothing to send.
            return@withContext Result.success()
        }
        val queue = FeedbackQueue(applicationContext)

        val pending = queue.peek()
        if (pending == null) {
            return@withContext Result.success()
        }

        when (val outcome = client.apiClient.submit(client.config.appId, pending.toSubmission())) {
            is SubmitOutcome.Success -> {
                queue.peek()?.let { queue.remove(it.submissionId) }
                // Keep going while the queue still has entries.
                if (queue.size() > 0) Result.retry() else Result.success()
            }

            is SubmitOutcome.Rejected -> {
                // The server will not accept this one; keeping it would block
                // the queue forever, so it is dropped and logged.
                val pending = queue.peek()
                if (pending != null) {
                    Log.w(TAG, "dropping a queued submission the server refused: ${outcome.message}")
                    queue.remove(pending.submissionId)
                }
                if (queue.size() > 0) Result.retry() else Result.success()
            }

            is SubmitOutcome.Queued -> {
                Log.i(TAG, "still offline; will retry")
                Result.retry()
            }
        }
    }

    companion object {
        private const val TAG = "OpenFeedbackUpload"
        const val WORK_NAME = "openfeedback-upload"

        /**
         * Schedules an upload attempt.
         *
         * Called after every submission and after the app starts, so a
         * submission made while offline is sent as soon as the network
         * comes back.
         */
        fun enqueue(context: Context) {
            val request = OneTimeWorkRequestBuilder<FeedbackUploadWorker>()
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()

            WorkManager.getInstance(context.applicationContext).enqueueUniqueWork(
                WORK_NAME,
                ExistingWorkPolicy.REPLACE,
                request,
            )
        }
    }
}
