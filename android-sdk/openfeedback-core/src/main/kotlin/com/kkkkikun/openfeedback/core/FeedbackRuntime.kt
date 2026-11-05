package com.kkkkikun.openfeedback.core

/**
 * The process-wide client registry.
 *
 * The background worker runs in a process that WorkManager may start on its
 * own, so it needs a way to find the configured client without the host app
 * having to set anything up by hand. The first client created in a process
 * becomes the default one.
 */
internal object FeedbackRuntime {

    @Volatile
    var client: FeedbackClient? = null
        private set

    /**
     * Registers a client as the process default.
     *
     * The first registration wins: a second client does not silently take
     * over, because the background worker must keep using the same endpoint
     * and appId that the user is interacting with.
     */
    @Synchronized
    fun register(candidate: FeedbackClient) {
        if (client == null) {
            client = candidate
        }
    }
}
