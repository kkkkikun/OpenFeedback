package com.kkkkikun.openfeedback.compose

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.ui.graphics.asImageBitmap
import com.kkkkikun.openfeedback.core.Attachment
import com.kkkkikun.openfeedback.core.DeviceContext
import com.kkkkikun.openfeedback.core.FeedbackConfig
import com.kkkkikun.openfeedback.core.FeedbackSDK
import com.kkkkikun.openfeedback.core.FeedbackSubmission
import com.kkkkikun.openfeedback.core.FeedbackSubmitter
import com.kkkkikun.openfeedback.core.FeedbackType
import com.kkkkikun.openfeedback.core.SubmitOutcome
import com.kkkkikun.openfeedback.core.newSubmissionId
import kotlinx.coroutines.launch

/** What the host app is told after the sheet closes. */
sealed class FeedbackResult {
    /** The server stored the feedback. */
    data class Submitted(val feedbackId: Long) : FeedbackResult()

    /** The feedback is saved on the device and will be sent later. */
    data class Queued(val reason: String) : FeedbackResult()

    /** The server refused the feedback. */
    data class Rejected(val message: String) : FeedbackResult()
}

/**
 * The feedback form.
 *
 * The host app controls when it opens and closes it:
 *
 * ```
 * var show by remember { mutableStateOf(false) }
 * if (show) {
 *     FeedbackSheet(onDismiss = { show = false }, onSubmitted = { result -> ... })
 * }
 * ```
 */
@Composable
fun FeedbackSheet(
    onDismiss: () -> Unit,
    onSubmitted: (FeedbackResult) -> Unit = {},
    config: FeedbackConfig = FeedbackSDK.current.config,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val submitter = remember { FeedbackSubmitter(context) }

    var type by rememberSaveable { mutableStateOf(FeedbackType.BUG) }
    var title by rememberSaveable { mutableStateOf("") }
    var description by rememberSaveable { mutableStateOf("") }
    var contact by rememberSaveable { mutableStateOf("") }
    var withDiagnostics by rememberSaveable { mutableStateOf(false) }

    var isSubmitting by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var showDiscardWarning by remember { mutableStateOf(false) }

    // Snapshot state lists are mutated in place rather than reassigned, so
    // they are not used with property delegation.
    val attachedImages = remember { mutableStateListOf<AttachedImage>() }
    val pendingUris = remember { mutableStateListOf<android.net.Uri>() }

    val attachmentLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.PickMultipleVisualMedia(MAX_PICK_COUNT),
    ) { uris ->
        pendingUris.addAll(uris)
    }

    // Turning the picked URIs into upload-ready images is slow enough to
    // need its own step, so it runs off the composition.
    LaunchedEffect(pendingUris.size) {
        if (pendingUris.isEmpty()) return@LaunchedEffect
        val toPrepare = pendingUris.toList()
        pendingUris.clear()
        for (uri in toPrepare) {
            if (attachedImages.size >= config.maxAttachments) break
            val prepared = ImagePreparer.prepare(
                context = context,
                uri = uri,
                maxEdge = config.maxImageEdge,
                maxBytes = config.maxAttachmentBytes,
            )
            if (prepared != null) {
                attachedImages.add(
                    AttachedImage(
                        bytes = prepared.bytes,
                        mimeType = prepared.mimeType,
                    )
                )
            }
        }
    }

    val hasContent = description.isNotBlank() || title.isNotBlank() || attachedImages.isNotEmpty()

    fun attemptSubmit() {
        if (description.isBlank()) {
            errorMessage = "请描述一下遇到的问题"
            return
        }
        isSubmitting = true
        errorMessage = null

        scope.launch {
            val device: DeviceContext = FeedbackSDK.current.deviceContext
            val diagnostics = if (withDiagnostics) {
                config.diagnosticProvider?.invoke()
            } else {
                null
            }

            val submission = FeedbackSubmission(
                submissionId = newSubmissionId(),
                type = type,
                title = title.trim().takeIf { it.isNotBlank() },
                description = description.trim(),
                contact = contact.trim().takeIf { it.isNotBlank() },
                device = device,
                diagnostics = diagnostics,
                attachments = attachedImages.map {
                    Attachment(
                        fileName = "screenshot.jpg",
                        mimeType = it.mimeType,
                        bytes = it.bytes,
                    )
                },
            )

            when (val outcome = submitter.submit(submission)) {
                is SubmitOutcome.Success -> {
                    isSubmitting = false
                    onSubmitted(FeedbackResult.Submitted(outcome.result.feedbackId))
                    onDismiss()
                }

                is SubmitOutcome.Queued -> {
                    isSubmitting = false
                    onSubmitted(FeedbackResult.Queued(outcome.reason))
                    onDismiss()
                }

                is SubmitOutcome.Rejected -> {
                    isSubmitting = false
                    errorMessage = outcome.message
                }
            }
        }
    }

    AlertDialog(
        onDismissRequest = {
            if (!isSubmitting) {
                if (hasContent) showDiscardWarning = true else onDismiss()
            }
        },
        title = {
            Text(
                text = "意见反馈",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.SemiBold,
            )
        },
        text = {
            Column(
                modifier = Modifier
                    .verticalScroll(rememberScrollState())
                    .heightIn(max = 480.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Text(
                    text = "遇到问题或有想法都可以提在这里。作者会集中处理。",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )

                // --- type ---
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(
                        text = "反馈类型",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Medium,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FeedbackType.entries.forEach { option ->
                            FilterChip(
                                selected = type == option,
                                onClick = { type = option },
                                label = { Text(option.label) },
                            )
                        }
                    }
                }

                // --- title ---
                OutlinedTextField(
                    value = title,
                    onValueChange = { title = it },
                    label = { Text("标题（选填）") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )

                // --- description ---
                OutlinedTextField(
                    value = description,
                    onValueChange = { description = it },
                    label = { Text("详细描述") },
                    placeholder = { Text("具体发生了什么？") },
                    minLines = 3,
                    modifier = Modifier.fillMaxWidth(),
                    isError = errorMessage != null && description.isBlank(),
                )

                // --- screenshots ---
                if (config.enableScreenshot) {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(
                            text = "截图（选填，最多 ${config.maxAttachments} 张）",
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.Medium,
                        )

                        Row(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            if (attachedImages.size < config.maxAttachments) {
                                Box(
                                    modifier = Modifier
                                        .size(72.dp)
                                        .clip(RoundedCornerShape(10.dp))
                                        .background(MaterialTheme.colorScheme.surfaceVariant)
                                        .clickable {
                                            attachmentLauncher.launch(
                                                PickVisualMediaRequest(
                                                    ActivityResultContracts.PickVisualMedia.ImageOnly
                                                )
                                            )
                                        },
                                    contentAlignment = Alignment.Center,
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.Add,
                                        contentDescription = "添加截图",
                                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                            }

                            attachedImages.forEachIndexed { index, image ->
                                AttachedImageChip(
                                    image = image,
                                    onRemove = { attachedImages.removeAt(index) },
                                )
                            }
                        }
                    }
                }

                // --- contact ---
                OutlinedTextField(
                    value = contact,
                    onValueChange = { contact = it },
                    label = { Text("联系方式（选填）") },
                    placeholder = { Text("邮箱或其他联系方式") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )

                // --- diagnostics ---
                if (config.diagnosticProvider != null) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "附带诊断信息",
                                style = MaterialTheme.typography.bodyMedium,
                            )
                            Text(
                                text = "仅包含应用自身的运行状态，不含账号信息",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        Switch(checked = withDiagnostics, onCheckedChange = { withDiagnostics = it })
                    }
                }

                // --- what is sent ---
                DeviceInfoNotice(device = FeedbackSDK.current.deviceContext)

                errorMessage?.let { message ->
                    Text(
                        text = message,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
        },
        confirmButton = {
            Button(
                onClick = { attemptSubmit() },
                enabled = !isSubmitting,
            ) {
                if (isSubmitting) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        strokeWidth = 2.dp,
                        color = MaterialTheme.colorScheme.onPrimary,
                    )
                    Spacer(Modifier.width(8.dp))
                    Text("提交中")
                } else {
                    Text("提交")
                }
            }
        },
        dismissButton = {
            TextButton(onClick = { onDismiss() }, enabled = !isSubmitting) {
                Text("取消")
            }
        },
    )

    if (showDiscardWarning) {
        AlertDialog(
            onDismissRequest = { showDiscardWarning = false },
            title = { Text("放弃这条反馈？") },
            text = { Text("填写的内容还没有提交，关闭后会丢失。") },
            confirmButton = {
                TextButton(onClick = {
                    showDiscardWarning = false
                    onDismiss()
                }) { Text("放弃") }
            },
            dismissButton = {
                TextButton(onClick = { showDiscardWarning = false }) { Text("继续填写") }
            },
        )
    }
}

/**
 * A ready-made entry point.
 *
 * The host app shows this wherever a feedback link belongs:
 *
 * ```
 * FeedbackLauncher(text = "意见反馈")
 * ```
 */
@Composable
fun FeedbackLauncher(
    text: String = "意见反馈",
    modifier: Modifier = Modifier,
    onResult: (FeedbackResult) -> Unit = {},
) {
    var showSheet by remember { mutableStateOf(false) }

    TextButton(
        onClick = { showSheet = true },
        modifier = modifier,
    ) {
        Text(text)
    }

    if (showSheet) {
        FeedbackSheet(
            onDismiss = { showSheet = false },
            onSubmitted = onResult,
        )
    }
}

@Composable
private fun AttachedImageChip(
    image: AttachedImage,
    onRemove: () -> Unit,
) {
    Box(modifier = Modifier.size(72.dp)) {
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(10.dp),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        ) {
            Box(
                modifier = Modifier
                    .size(72.dp)
                    .background(MaterialTheme.colorScheme.surfaceVariant),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    text = "${image.bytes.size / 1024} KB",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        Box(
            modifier = Modifier
                .align(Alignment.TopEnd)
                .size(22.dp)
                .clip(RoundedCornerShape(11.dp))
                .background(MaterialTheme.colorScheme.scrim.copy(alpha = 0.55f))
                .clickable(onClick = onRemove),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = Icons.Default.Close,
                contentDescription = "移除截图",
                tint = Color.White,
                modifier = Modifier.size(14.dp),
            )
        }
    }
}

/**
 * Tells the user exactly what is attached to the feedback.
 *
 * The device information is not hidden: the user can see the app version,
 * the Android version, and the device model before sending.
 */
@Composable
private fun DeviceInfoNotice(device: DeviceContext) {
    if (device.appVersion == null && device.model == null) return

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.4f)
        ),
        shape = RoundedCornerShape(10.dp),
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                text = "将随反馈附带",
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Medium,
            )
            Text(
                text = buildString {
                    if (device.appVersion != null) {
                        append("App 版本 ${device.appVersion}")
                        if (device.appBuild != null) append(" (${device.appBuild})")
                    }
                    if (device.androidVersion != null) {
                        if (isNotEmpty()) append(" · ")
                        append("Android ${device.androidVersion}")
                    }
                    if (device.manufacturer != null || device.model != null) {
                        if (isNotEmpty()) append(" · ")
                        append(listOfNotNull(device.manufacturer, device.model).joinToString(" "))
                    }
                    if (device.locale != null) {
                        if (isNotEmpty()) append(" · ")
                        append(device.locale)
                    }
                },
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                text = "不含 IMEI、序列号、位置或账号信息。",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/** An image the user picked, already compressed. */
private data class AttachedImage(
    val bytes: ByteArray,
    val mimeType: String,
) {
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is AttachedImage) return false
        return mimeType == other.mimeType && bytes.contentEquals(other.bytes)
    }

    override fun hashCode(): Int = 31 * bytes.contentHashCode() + mimeType.hashCode()
}

private const val MAX_PICK_COUNT = 5
