package com.kkkkikun.openfeedback.core

import android.content.Context

/**
 * A configured client for one host app.
 *
 * This is the entry point for a host app that keeps its own feedback UI and
 * only wants the transport, the offline queue, and the retry behaviour.
 * An app that uses the SDK's own Compose sheet can use [FeedbackSDK] instead,
 * which wraps a `FeedbackClient`.
 *
 * ```
 * val client = FeedbackClient(
 *     context = applicationContext,
 *     config = FeedbackConfig(
 *         appId = "oit-net-portal",
 *         endpoint = "https://feedback.example.com",
 *         appName = "校园网助手",
 *     ),
 * )
 * val outcome = client.submitter.submit(submission)
 * ```
 */
class FeedbackClient(
    private val context: Context,
    val config: FeedbackConfig,
    val deviceContext: DeviceContext = DeviceContextCollector(context, config).collect(),
    val apiClient: FeedbackApiClient = FeedbackApiClient(config.endpoint),
) {
    /** Sends feedback, queueing it when the network is unavailable. */
    val submitter: FeedbackSubmitter by lazy { FeedbackSubmitter(context, this) }

    init {
        // The background worker needs to find a client in a process that
        // WorkManager may have started on its own.
        FeedbackRuntime.register(this)
    }
}
