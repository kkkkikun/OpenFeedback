# 牵线（Rust / Makepad）接入 OpenFeedback

- 版本：1.0.0
- 最后更新：2026-11-05

## 为什么牵线不用 Android SDK

牵线的 Android 端是 **Rust + Makepad** 程序（`dev.aurorax.qianxian`），
不是 Kotlin/Compose。Kotlin 写的 `openfeedback-core` 在这里用不了，
所以牵线**直接实现同一套 wire format**。

wire format 很简单（见 [`../../docs/API.md`](../../docs/API.md)）：
一次 `multipart/form-data` POST，元数据是一个 JSON 字符串。

## 现状与边界

牵线的主交付物是 OctoSense 的 **Splash script-app**（`bundle/main.splash`），
它的 `manifest.json` 声明：

```json
"network": { "hosts": [] }
```

也就是**不发起任何网络请求**，`PRIVACY.md` 里明确承诺了这一点。
Android 端（`app-android/`）是独立的 Rust 程序，它的 `main.rs` 用
`include_str!("../../bundle/main.splash")` 把同一份脚本嵌进 Makepad 渲染。

**本次接入只做 Android 端**（按当前决定），Splash 侧的 `hosts` 与隐私承诺
保持不变。

## 接入位置

Android 端的宿主在 `app-android/src/main.rs`。它已经给 Splash 授了一组能力：

```rust
splash.set_host_caps(cx, vec![
    "octos.turn.start".to_string(),
    "qianxian.clipboard.read".to_string(),
    "qianxian.notify".to_string(),
    "qianxian.app.minimize".to_string(),
]);
```

有两个可选做法：

### 方案 A：Rust 侧直接发请求（推荐）

在 Rust 里加一个反馈入口和一个 HTTP 客户端，请求直接打到 OpenFeedback。

**优点**：不碰 `main.splash`，Splash 侧的 `hosts: []` 与隐私承诺完全不变；
请求不经过脚本层，边界清晰。

**代价**：需要给 Rust 工程加一个 HTTP 客户端依赖。当前 `Cargo.lock` 里
只有 `rustls`（间接依赖），没有 HTTP 客户端。加 `ureq`（体积小、同步 API、
支持 rustls）最省事：

```toml
[dependencies]
ureq = { version = "2", default-features = false, features = ["rustls"] }
```

> 网络受限的环境下，`cargo` 也需要走镜像。阿里云镜像上
> `swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/...` 可用；
> crates.io 本身可用时无需处理。

### 方案 B：给 Splash 加一个 host capability

Rust 宿主实现 `qianxian.feedback.submit`，脚本侧调用它。

**优点**：UI 写在脚本里，改起来快。
**代价**：`main.splash` 是脚本与 Android 端共用的，改动会同时影响
OctoSense 侧的发布物；那条路径的 `hosts` 仍然是空的，需要额外处理
「脚本在 OctoSense 里没有这个能力」的降级。

**结论**：走方案 A。

## 实现要点

### 1. 依赖

```toml
[dependencies]
ureq = { version = "2", default-features = false, features = ["rustls"] }
serde_json = "1.0"   # 已有
uuid = { version = "1", features = ["v4"] }
```

### 2. 数据结构

```rust
#[derive(serde::Serialize)]
struct FeedbackPayload {
    #[serde(rename = "appId")]
    app_id: &'static str,          // "qianxian"
    #[serde(rename = "submissionId")]
    submission_id: String,         // 每次提交生成一次，重试时不变
    #[serde(rename = "type")]
    kind: &'static str,            // "bug" | "feature" | "experience" | "other"
    #[serde(rename = "description")]
    description: String,
    #[serde(rename = "appVersion")]
    app_version: &'static str,
    #[serde(rename = "sdkVersion")]
    sdk_version: &'static str,     // 牵线自己的版本号
    #[serde(rename = "androidVersion")]
    android_version: Option<String>,
    #[serde(rename = "manufacturer")]
    manufacturer: Option<String>,
    #[serde(rename = "model")]
    model: Option<String>,
}
```

### 3. 提交

```rust
fn submit_feedback(endpoint: &str, payload: &FeedbackPayload) -> Result<(), String> {
    let json = serde_json::to_string(payload).map_err(|e| e.to_string())?;

    let form = ureq::builder()
        .multipart("form")
        .text("payload", json.as_str())
        .build();

    match form.post(&format!("{}/api/v1/feedback", endpoint.trim_end_matches('/'))) {
        Ok(_) => Ok(()),
        // 4xx 是请求本身不对，重试没用
        Err(ureq::Error::Status(code, _)) if (400..500).contains(&code) => {
            Err(format!("服务端拒绝了这个反馈（HTTP {code}）"))
        }
        // 其余是网络问题，值得重试
        Err(e) => Err(e.to_string()),
    }
}
```

### 4. 断网暂存

和 Android SDK 一样：**提交失败时不能告诉用户「提交成功」**。

建议的流程：

1. 生成 `submission_id`（UUID v4），写进本机 JSON 文件；
2. 立刻尝试上传；
3. 成功则删除本机文件；
4. 失败则保留文件，交给一个后台重试任务（Makepad 有 `widget_async`，
   可以用定时器轮询待发送队列）；
5. 重试时**复用同一个 `submission_id`**，服务端据此去重。

本机文件建议放在 app 的私有目录（Makepad 里对应 `sandbox_dir`，
Android 端就是 `filesDir`），例如：

```
<filesDir>/openfeedback/queue/<submission_id>.json
```

**不要**把待发送内容写进 `cases.json` 或其它业务数据文件里——
那是用户的活动数据，反馈是另一回事。

### 5. UI

牵线的 Makepad UI 用 `makepad_widgets`。反馈入口建议放在设置面板
（脚本侧已有 `settings_open` 状态，Rust 侧另开一个窗口也可以）。

最小可用形态：

- 一个文本输入框（多行）；
- 一个类型选择（四个）；
- 一个「提交」按钮；
- 一个状态标签（发送中 / 已收到 / 已暂存待发送）。

## 隐私边界

- **不附带**活动内容、成员名单、账目、群消息原文；
- **不附带**模型上下文、Prompt、工具调用参数；
- 诊断信息（如果提供）必须由牵线自己过滤，只给连接状态这类结论；
- 不带 IMEI、序列号、MAC 地址、位置；
- 截图能力第一版可以先不做（`attachments` 是可选字段）。

## 验收

1. 牵线 App 里提交一条反馈 → OpenFeedback 后台出现记录，`appId=qianxian`；
2. 断网提交 → 提示「已暂存」；
3. 恢复网络 → 自动补发 → 后台出现记录；
4. 重复补发 → 后台**只有一条**记录（`submissionId` 去重生效）。
