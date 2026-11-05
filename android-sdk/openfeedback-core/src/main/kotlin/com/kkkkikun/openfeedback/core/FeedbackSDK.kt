package com.kkkkikun.openfeedback.core

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import java.util.Locale

/**
 * How the SDK talks to one host app.
 *
 * [appId] is a public identifier, not a secret: the server uses it to route
 * feedback to the right project. It carries no credential, so it is safe to
 * ship inside an APK.
 */
data class FeedbackConfig(
    /** The app's registered id, for example `localpixt`. */
    val appId: String,

    /** The service base URL, for example `https://feedback.example.com`. */
    val endpoint: String,

    /** A human-readable name, shown in the form so the user knows the context. */
    val appName: String? = null,

    /** Whether the user can attach screenshots. */
    val enableScreenshot: Boolean = true,

    /** Whether device information is collected and sent. */
    val enableDeviceInfo: Boolean = true,

    /** The most screenshots one submission may carry. */
    val maxAttachments: Int = 3,

    /** The largest compressed image, in bytes. */
    val maxAttachmentBytes: Int = 2 * 1024 * 1024,

    /** The longest edge of a compressed image, in pixels. */
    val maxImageEdge: Int = 2048,

    /**
     * Optional diagnostics supplied by the host app.
     *
     * The provider is only called when the user ticks "attach diagnostics",
     * and the host app is responsible for removing anything sensitive. The
     * SDK does not read the host's database or logs on its own.
     */
    val diagnosticProvider: (() -> String?)? = null,
)

/**
 * The SDK's entry point.
 *
 * Call [initialize] once, from `Application.onCreate`. Everything else is
 * driven from the composables in `openfeedback-compose`.
 */
object FeedbackSDK {

    @Volatile
    private var state: State? = null

    /**
     * The SDK's current state.
     *
     * @throws IllegalStateException when the SDK was never initialised.
     */
    val current: State
        get() = state ?: throw IllegalStateException(
            "FeedbackSDK.initialize() must be called before using the SDK"
        )

    val isInitialized: Boolean get() = state != null

    /**
     * Initialises the SDK.
     *
     * Calling this more than once is a programming error: the second call
     * throws rather than silently replacing the configuration. Initialisation
     * never blocks the main thread.
     */
    @JvmStatic
    @JvmOverloads
    fun initialize(
        context: Context,
        config: FeedbackConfig,
        client: FeedbackApiClient? = null,
    ) {
        if (state != null) {
            throw IllegalStateException(
                "FeedbackSDK.initialize() may only be called once per process"
            )
        }
        val appContext = context.applicationContext
        state = State(
            client = FeedbackClient(
                context = appContext,
                config = config,
                apiClient = client ?: FeedbackApiClient(config.endpoint),
            )
        )
    }

    /** Test hook: resets the singleton. */
    @JvmStatic
    internal fun resetForTesting() {
        state = null
    }

    /** The live configuration and clients. */
    class State internal constructor(val client: FeedbackClient) {
        val config: FeedbackConfig get() = client.config
        val apiClient: FeedbackApiClient get() = client.apiClient
        val deviceContext: DeviceContext get() = client.deviceContext
        val submitter: FeedbackSubmitter get() = client.submitter
    }
}

/**
 * Collects the app and device context that rides along with a submission.
 *
 * The list is deliberately short. Nothing here can identify a person or
 * reach another app: no IMEI, no serial number, no MAC address, no
 * location, no account information.
 */
internal class DeviceContextCollector(
    private val context: Context,
    private val config: FeedbackConfig,
) {
    fun collect(): DeviceContext {
        if (!config.enableDeviceInfo) {
            return DeviceContext(sdkVersion = BuildConfig.SDK_VERSION)
        }

        val packageName = context.packageName
        val versionName = runCatching {
            @Suppress("DEPRECATION")
            context.packageManager.getPackageInfo(packageName, 0).versionName
        }.getOrNull()

        val versionCode = runCatching {
            @Suppress("DEPRECATION")
            val info = context.packageManager.getPackageInfo(packageName, 0)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                info.longVersionCode.toString()
            } else {
                @Suppress("DEPRECATION")
                info.versionCode.toString()
            }
        }.getOrNull()

        val label = runCatching {
            val info = context.packageManager.getPackageInfo(packageName, 0)
            info.applicationInfo?.loadLabel(context.packageManager)?.toString()
        }.getOrNull()

        return DeviceContext(
            appName = config.appName ?: label,
            appVersion = versionName,
            appBuild = versionCode,
            sdkVersion = BuildConfig.SDK_VERSION,
            androidVersion = Build.VERSION.RELEASE,
            apiLevel = Build.VERSION.SDK_INT,
            manufacturer = Build.MANUFACTURER,
            model = Build.MODEL,
            locale = Locale.getDefault().toLanguageTag(),
        )
    }
}
