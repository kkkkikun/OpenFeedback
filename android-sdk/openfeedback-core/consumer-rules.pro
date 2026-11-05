# The SDK talks to the server with plain JSON over HttpURLConnection, so no
# reflection-based serialization needs to survive shrinking. The rules below
# keep the public API surface of the SDK intact for host apps that use R8.
-keep public class com.kkkkikun.openfeedback.core.** { public *; }
-keep public class com.kkkkikun.openfeedback.compose.** { public *; }

# WorkManager instantiates the worker by name.
-keep class com.kkkkikun.openfeedback.core.FeedbackUploadWorker { *; }
