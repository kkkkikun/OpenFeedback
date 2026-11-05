# 接入指南

- 版本：1.0.0
- 最后更新：2026-11-05

本文件说明如何把一个新应用接入 OpenFeedback。

## 通用约定

不管用什么技术栈，接入方都要遵守这几条：

1. **服务地址是唯一需要配置的东西。** 提交接口不需要任何客户端凭据，
   APK 里只有公开的 `appId` 和服务地址。
2. **`appId` 必须先在服务端注册。** 服务端启动时注册了四个应用：
   `oit-net-portal`、`localpixt`、`qianxian`、`schoolwall`。
   新应用需要在 `server/app/main.py` 的 `DEFAULT_APPS` 里加一行，
   或者直接往 `apps` 表插一行——**不需要改数据库结构**。
3. **每次提交带一个稳定的 `submissionId`。** 断网重试时必须是同一个值，
   否则服务端会当成两条反馈。
4. **不采集敏感信息。** 不带 IMEI、序列号、MAC 地址、位置、账号、密码、
   Cookie、Token。诊断信息必须由宿主自己脱敏后提供。
5. **不自动上传用户数据。** 不上传照片原件、数据库、模型文件、聊天记录。

## 提交格式

`POST <endpoint>/api/v1/feedback`，`multipart/form-data`：

- `payload`：一个 JSON 字符串，字段见 [API.md](API.md)；
- `attachments`：图片文件，可重复，最多 3 张。

Rust / Go / 任何语言都可以直接用 `curl` 等价的 multipart 拼装，
不需要引入 SDK。

## Android（Kotlin / Compose）

### 用 SDK 自带的反馈窗口

**1. 依赖**

`settings.gradle.kts`：

```kotlin
dependencyResolutionManagement {
    repositories {
        maven {
            name = "openfeedback"
            url = uri("https://<反馈服务地址>/maven/")
        }
        google()
        mavenCentral()
    }
}
```

`app/build.gradle.kts`：

```kotlin
dependencies {
    implementation("com.kkkkikun.openfeedback:openfeedback-compose:0.1.0")
}
```

版本必须写死，**不要用 `+`**。

**2. 初始化**

在 `Application.onCreate` 里：

```kotlin
FeedbackSDK.initialize(
    context = this,
    config = FeedbackConfig(
        appId = "localpixt",
        endpoint = "https://<反馈服务地址>",
        appName = "显影",
        enableScreenshot = true,
        enableDeviceInfo = true,
        diagnosticProvider = { MyDiagnostics.sanitizedSummary() },
    ),
)
```

`initialize` 只能调用一次，第二次会抛异常。它不阻塞主线程。

**3. 打开反馈窗口**

```kotlin
var showFeedback by remember { mutableStateOf(false) }

if (showFeedback) {
    FeedbackSheet(
        onDismiss = { showFeedback = false },
        onSubmitted = { result ->
            when (result) {
                is FeedbackResult.Submitted -> toast("反馈已收到")
                is FeedbackResult.Queued -> toast("已保存，联网后自动发送")
                is FeedbackResult.Rejected -> toast(result.message)
            }
        },
    )
}

// 或者用现成的入口
FeedbackLauncher(text = "意见反馈")
```

窗口跟随宿主的 `MaterialTheme`，支持深色模式。

### 宿主已有自己的表单

如果宿主已经有反馈 UI，只想换传输链路（统一后台、离线队列、截图），
就只依赖 core：

```kotlin
dependencies {
    implementation("com.kkkkikun.openfeedback:openfeedback-core:0.1.0")
}
```

```kotlin
val client = FeedbackClient(
    context = applicationContext,
    config = FeedbackConfig(appId = "oit-net-portal", endpoint = endpoint),
)

val outcome = client.submitter.submit(
    FeedbackSubmission(
        submissionId = newSubmissionId(),
        type = FeedbackType.BUG,
        title = null,
        description = text,
        contact = null,
        device = client.deviceContext,
        diagnostics = null,
    ),
)
```

`SubmitOutcome.Queued` 表示已存本机、联网后自动补发——
**这不是失败**，宿主应当把它当成成功展示给用户。

参考实现见 `OIT-Net-Portal/android/app/src/main/java/com/oitnetportal/core/OpenFeedbackBridge.kt`。

### 版本与兼容

| 项 | 值 |
|---|---|
| `minSdk` | 26 |
| `compileSdk` | 35 |
| Kotlin | 2.0.21 |
| Compose BOM | 2024.12.01 |
| AGP | 8.5.2（可被 8.7.x 消费） |

## SchoolWall（uni-app / Vue 3）

uni-app 不使用 Android SDK，直接调 REST 接口。

`frontend/src/utils/feedback.ts`：

```ts
export async function submitFeedback(payload: FeedbackPayload): Promise<void> {
  // uni.request 不支持 multipart，附件用 uni.uploadFile 单独上传，
  // 或本版先只支持纯文字反馈。
  await post('/feedback', payload)
}
```

要点：

- 小程序端用 `uni.uploadFile` 上传附件（`uni.request` 不支持 multipart）；
- H5 端可以用 `FormData` + `uni.request`；
- `app-plus`（Android 代码包）两种都支持。

现成的组件放在 `integrations/schoolwall/`。

## 牵线（Rust / Makepad）

牵线的 Android 端是 Rust 程序，不是 Kotlin/Compose，所以它**不用 Android SDK**，
而是直接实现同一套 wire format。

实现要点：

1. `net::reqwest` 或 `ureq` 发 `multipart/form-data`；
2. `payload` 字段是一个 JSON 字符串；
3. `submissionId` 在写入本机队列与重试之间保持不变；
4. 断网时把反馈写进 App 私有目录，联网后重试。

详细的接入说明与代码骨架见
[`integrations/qianxian/README.md`](../integrations/qianxian/README.md)。

## 本地开发

服务端：

```bash
cd server
python -m venv .venv && .venv/bin/pip install -r requirements.txt
OF_ADMIN_PASSWORD=dev-password .venv/bin/python -m uvicorn app.main:app --reload
```

SDK：

```bash
cd android-sdk
./gradlew assemble          # 构建
./gradlew test              # 单元测试
./gradlew publishReleasePublicationToLocalMavenRepository   # 发布到 maven-repo/
```

宿主 App 用本地仓库联调：

```bash
./gradlew -Poit.openfeedback.mavenUrl=file:///path/to/OpenFeedback/android-sdk/maven-repo ...
```
