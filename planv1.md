# OpenFeedback：多应用统一反馈系统

## 工程实施方案 v1.0

**项目目标：** 为多个现有应用提供统一的应用内反馈能力。开发一套独立的 Android SDK、一套轻量反馈服务端和一个 Web 管理后台。用户在原 App 内提交反馈，开发者在统一后台查看和处理。

**部署环境：**

- 阿里云 ECS
- Ubuntu 24.04
- 2 vCPU / 2 GB RAM / 40 GB SSD
- 公网带宽 3 Mbps
- 初期只面向少量测试用户和朋友

# 一、项目目标与范围

## 1.1 接入应用

预先注册四个应用：

| appId          | 应用名称   | 接入方式                                                     |
| -------------- | ---------- | ------------------------------------------------------------ |
| oit-net-portal | 校园网助手 | Android SDK                                                  |
| schoolwall     | 校园墙     | 优先检查现有技术栈，原生 Android 使用 SDK，uni-app 使用 REST API |
| localpixt      | 显影       | Android SDK                                                  |
| qianxian       | 牵线       | Android SDK                                                  |

所有应用使用同一套服务端、同一个管理后台，通过 appId 区分数据。

## 1.2 第一版必须实现

1. App 内打开反馈窗口。
2. 支持 Bug、功能建议、体验问题、其他四种类型。
3. 支持标题和详细描述。
4. 支持用户主动选择截图。
5. 自动附带必要的 App 版本和设备信息。
6. 支持匿名提交，不要求注册。
7. 网络失败后能够保存并自动重试。
8. 服务端接收并持久化反馈。
9. 管理后台能够查看、搜索、筛选反馈。
10. 能够标记处理状态和添加内部备注。

## 1.3 第一版明确不做

- 不开发独立 Android App。
- 不开发用户注册、登录和个人中心。
- 不开发公开反馈社区。
- 不开发点赞、投票和评论。
- 不开发即时聊天和消息推送。
- 不接入 AI 自动分类。
- 不自动录屏或监听系统截图。
- 不自动上传用户照片、完整数据库、模型数据。
- 不自动采集完整 Logcat。
- 不接入 OSS。
- 不引入 Redis、Kafka、微服务。
- 不修改现有应用的主要架构。

这些功能以后有实际需求再增加。

# 二、整体技术架构

```
┌─────────────────────────────────────────┐
│              现有应用                    │
│                                         │
│  OIT-Net-Portal  LocalPixt  qianxian    │
│                                         │
│  SchoolWall（根据技术栈选择接入方式）     │
└───────────────────┬─────────────────────┘
                    │
          ┌─────────▼─────────┐
          │  OpenFeedback SDK │
          │                   │
          │ Compose UI        │
          │ 图片选择与压缩     │
          │ 设备信息收集       │
          │ 离线队列与重试     │
          │ HTTP API Client   │
          └─────────┬─────────┘
                    │ HTTPS
          ┌─────────▼─────────┐
          │  OpenFeedback API │
          │                   │
          │ FastAPI           │
          │ 数据校验           │
          │ 限流               │
          │ 反馈管理           │
          └─────────┬─────────┘
                    │
             ┌──────▼──────┐
             │   SQLite    │
             │             │
             │ 反馈记录     │
             │ 附件索引     │
             │ 应用信息     │
             │ 管理备注     │
             └─────────────┘
                    │
             ┌──────▼──────┐
             │ Web Admin   │
             │             │
             │ 反馈列表     │
             │ 反馈详情     │
             │ 状态管理     │
             │ 应用筛选     │
             └─────────────┘
```

所有组件初期部署在同一台 ECS。

# 三、项目仓库结构

建立独立 Git 仓库：

```
OpenFeedback
```

建议目录：

```
OpenFeedback/
├── android-sdk/
│   ├── openfeedback-core/
│   ├── openfeedback-compose/
│   ├── openfeedback-testing/
│   └── build.gradle.kts
│
├── server/
│   ├── app/
│   │   ├── api/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── auth/
│   │   └── main.py
│   ├── migrations/
│   ├── tests/
│   └── requirements.txt
│
├── admin/
│   ├── templates/
│   ├── static/
│   └── README.md
│
├── integrations/
│   ├── android/
│   └── schoolwall/
│
├── deploy/
│   ├── docker-compose.yml
│   ├── Dockerfile
│   ├── Caddyfile
│   ├── .env.example
│   ├── backup.sh
│   └── deploy.sh
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── API.md
│   ├── ANDROID_SDK.md
│   ├── INTEGRATION.md
│   ├── DEPLOYMENT.md
│   ├── SECURITY.md
│   └── CHANGELOG.md
│
├── .gitignore
├── LICENSE
└── README.md
```

可以根据实际工程情况调整，但客户端、服务端、部署和文档必须保持清晰分离。

# 四、Android SDK 设计

## 4.1 技术要求

- Kotlin。
- Jetpack Compose。
- AndroidX。
- Kotlin Coroutines。
- OkHttp 或与项目兼容的 HTTP 客户端。
- WorkManager。
- Android Photo Picker。

必须先检查三个原生项目的 Kotlin、AGP、Compose Compiler、compileSdk 和 minSdk 版本。

不要为了接入 SDK 而随意升级原有项目依赖。

SDK 不应依赖 LocalPixt 的 Room 数据库，也不应要求宿主应用修改自己的数据库结构。

## 4.2 初始化接口

提供统一配置：

```
FeedbackSDK.initialize(
    context = applicationContext,
    config = FeedbackConfig(
        appId = "localpixt",
        endpoint = "https://反馈服务地址",
        appName = "显影",
        enableScreenshot = true,
        enableDeviceInfo = true
    )
)
```

要求：

- initialize 只能初始化一次。
- appId 用于区分应用，不是秘密密钥。
- 不在 APK 中放置管理员密码、服务端密钥。
- endpoint 可以通过构建配置区分测试和正式环境。
- 支持应用启动时初始化，不阻塞主线程。

## 4.3 Compose 调用接口

建议提供两种调用方式。

方式 A：直接打开反馈窗口。

```
FeedbackSheet(
    onDismiss = { },
    onSubmitted = { }
)
```

方式 B：由 SDK 提供按钮。

```
FeedbackLauncher(
    text = "意见反馈",
    onClick = {
        // 打开反馈窗口
    }
)
```

实际 API 以最终设计为准，但必须保证宿主 App 可以自由控制窗口的打开和关闭。

## 4.4 反馈窗口设计

使用 Material 3 风格，默认遵循宿主 App 的 MaterialTheme。

表单字段：

| 字段     | 必填 | 说明                             |
| -------- | ---- | -------------------------------- |
| 反馈类型 | 是   | Bug / 功能建议 / 体验问题 / 其他 |
| 标题     | 否   | 简短问题标题                     |
| 详细描述 | 是   | 具体问题                         |
| 截图     | 否   | 最多 3 张                        |
| 联系方式 | 否   | 邮箱或其他联系方式               |

交互要求：

1. 页面简洁，避免长表单。
2. 提交按钮有明确加载状态。
3. 关闭时提示是否放弃未提交内容。
4. 提交成功显示明确结果。
5. 网络不可用时明确提示已经本地保存、等待重试。
6. 支持中文。
7. 适配深色模式。
8. 适配小屏幕和键盘弹出。
9. 不使用与宿主 App 风格冲突的固定颜色。

## 4.5 截图附件

采用 Android Photo Picker。

要求：

- 不申请整个相册的读取权限。
- 用户主动选择图片。
- 最多 3 张。
- 单张压缩后不超过 2 MB。
- 最长边建议不超过 2048px。
- 采用 JPEG 或 WebP。
- 移除 EXIF 等不必要的元数据。
- 取消选择后删除临时文件。
- 不自动截取整个 App 屏幕。

允许宿主 App 将自己主动生成的截图 Uri 传给 SDK，但不能默认捕获用户界面。

## 4.6 设备信息

自动附带：

- App 名称。
- App 版本名称。
- App versionCode。
- SDK 版本。
- Android 版本。
- Android API Level。
- 设备制造商。
- 设备型号。
- 系统语言。

禁止采集：

- IMEI。
- 手机序列号。
- MAC 地址。
- GPS 位置。
- 用户账号密码。
- Wi-Fi 密码。
- 无关的系统标识符。

设备信息应在反馈页面明确告知用户。

## 4.7 诊断日志

第一版不自动收集 Logcat。

SDK 预留一个可选诊断信息接口：

```
diagnosticProvider = {
    // 由宿主 App 提供经过脱敏的诊断信息
}
```

只有用户主动勾选附带诊断信息时才执行。

宿主 App 必须负责过滤密码、Cookie、Token、个人数据等敏感内容。

## 4.8 离线提交

这是必须认真实现的功能。

推荐流程：

1. 用户点击提交。
2. SDK 生成唯一 submissionId。
3. 优先尝试立即上传。
4. 上传成功，显示成功。
5. 上传失败，将表单和附件保存到 App 私有目录。
6. 使用 WorkManager 创建带网络约束的任务。
7. 网络恢复后自动重试。
8. 服务端通过 submissionId 防止重复创建反馈。
9. 成功上传后删除本地临时数据。

本地队列：

- 使用 App 私有目录或 noBackupFilesDir。
- 不要求宿主 App 使用 Room。
- 不将图片字节直接塞入 WorkManager Data。
- 附件文件路径与 JSON 元数据分开保存。
- 指数退避重试。
- 设置合理的队列容量。
- 允许用户取消未发送的反馈。

不能在服务器尚未收到反馈时显示“提交成功”。

# 五、服务端设计

## 5.1 技术栈

| 模块       | 技术                           |
| ---------- | ------------------------------ |
| API        | Python FastAPI                 |
| 数据验证   | Pydantic                       |
| ORM        | SQLAlchemy                     |
| 数据库     | SQLite                         |
| 数据库迁移 | Alembic                        |
| Web 后台   | FastAPI + Jinja2 + 原生 JS/CSS |
| 反向代理   | Caddy                          |
| 部署       | Docker Compose                 |

初期不使用 PostgreSQL、Redis、对象存储和独立消息队列。

SQLite 开启 WAL 模式，并做好数据库备份。

## 5.2 数据库设计

### apps

```
id
app_id
name
platform
enabled
created_at
```

### feedback

```
id
submission_id
app_id
type
title
description
contact
app_version
app_build
sdk_version
android_version
device_manufacturer
device_model
locale
status
created_at
updated_at
```

### feedback_attachments

```
id
feedback_id
filename
storage_path
mime_type
file_size
sha256
created_at
```

### feedback_notes

```
id
feedback_id
content
created_at
```

### feedback_status_history

```
id
feedback_id
old_status
new_status
created_at
```

### admin_users

```
id
username
password_hash
created_at
last_login_at
```

必须建立适当索引，尤其是 app_id、status、created_at。

## 5.3 应用初始化数据

服务启动时注册：

```
oit-net-portal
schoolwall
localpixt
qianxian
```

每个应用独立启用或停用。

新增应用不能要求修改数据库代码。

## 5.4 API 设计

公共接口：

```
GET /api/v1/health
POST /api/v1/feedback
```

管理接口：

```
POST /api/v1/admin/login
POST /api/v1/admin/logout

GET /api/v1/admin/apps

GET /api/v1/admin/feedback
GET /api/v1/admin/feedback/{id}

PATCH /api/v1/admin/feedback/{id}

POST /api/v1/admin/feedback/{id}/notes

GET /api/v1/admin/attachments/{id}
```

反馈提交使用 multipart/form-data，包含：

- JSON 格式的反馈元数据。
- 可选图片附件。
- 唯一 submissionId。

服务端需要验证：

- appId 是否存在且启用。
- 必填字段是否合法。
- 内容长度是否符合限制。
- 文件类型是否合法。
- 文件实际格式是否与 MIME 一致。
- 图片大小和数量是否超限。
- submissionId 是否重复。

重复提交返回原反馈的结果，不创建重复记录。

## 5.5 反馈状态

第一版采用四种状态：

| 状态        | 含义   |
| ----------- | ------ |
| NEW         | 待处理 |
| IN_PROGRESS | 处理中 |
| RESOLVED    | 已解决 |
| CLOSED      | 已关闭 |

管理员可以在后台修改状态、添加内部备注。

第一版不实现用户与管理员的即时对话。

# 六、Web 管理后台

管理后台采用简洁的桌面优先设计，同时兼容手机浏览器。

## 6.1 反馈列表

显示：

- 反馈标题。
- 应用名称。
- 反馈类型。
- 提交时间。
- App 版本。
- 当前状态。

提供：

- 按 App 筛选。
- 按状态筛选。
- 按反馈类型筛选。
- 按时间排序。
- 标题和描述搜索。
- 分页。

## 6.2 反馈详情

点击一条反馈后显示：

1. 完整描述。
2. 反馈类型。
3. 所属应用。
4. 提交时间。
5. App 版本。
6. 设备信息。
7. 截图预览。
8. 联系方式。
9. 状态修改。
10. 内部备注。
11. 状态变化历史。

附件只能通过管理员鉴权接口访问，不能直接公开访问文件路径。

## 6.3 首页统计

只需要简单统计：

- 总反馈数。
- 待处理数量。
- 处理中数量。
- 已解决数量。
- 各 App 反馈数量。

不需要复杂图表。

# 七、安全和隐私

第一版也必须具备基本安全能力。

## 7.1 公共接口

- appId 是公开标识，不是安全凭证。
- 不把管理员密钥写入 APK。
- 对每个 appId 和 IP 设置请求频率限制。
- 初始可以设置每 IP、每 App 每小时最多 10 条，后续可配置。
- 限制请求体大小。
- 严格验证附件。
- 防止重复提交。
- 不允许用户指定服务端存储路径。
- 过滤危险文件名。

## 7.2 管理后台

- 必须登录。
- 初始管理员密码从环境变量初始化。
- 密码使用 Argon2id 或安全的密码哈希算法。
- 使用 HttpOnly、Secure、SameSite Cookie。
- 登录接口限流。
- 使用 CSRF 防护。
- 不提供公开注册入口。
- 管理 API 不得被匿名用户访问。

## 7.3 数据保护

- 不默认上传照片原件。
- 不默认上传数据库。
- 不默认上传模型文件和向量索引。
- 不默认上传完整聊天记录。
- 不自动采集密码、Cookie、Token。
- 不将附件暴露在公开静态目录。
- 不在日志中记录用户完整反馈内容和敏感信息。

# 八、阿里云部署

## 8.1 服务器环境

现有 ECS：

```
Ubuntu 24.04
2 vCPU
2 GB RAM
40 GB SSD
3 Mbps 公网带宽
```

第一版只部署：

```
Caddy
FastAPI
SQLite
Web Admin
Attachments
```

全部使用 Docker Compose 管理。

## 8.2 资源限制

- FastAPI 仅启动一个 Worker。
- 不启动多个冗余进程。
- 不引入 PostgreSQL。
- 不引入 Redis。
- 管理后台使用服务端模板，不运行独立 Node 服务。
- 附件压缩后保存。
- 配置 Docker 日志轮转。
- 定期检查磁盘使用情况。
- 限制容器资源占用，但预留足够系统内存。

建议初期设置：

- 单个附件最大 2 MB。
- 单条反馈最多 3 个附件。
- 附件总容量预警阈值 5 GB。
- 上传请求体大小设置合理上限。
- 暂不自动删除反馈记录。

## 8.3 网络与 HTTPS

优先检查现有域名是否支持配置独立反馈子域名，例如：

```
feedback.kkkkikun.dpdns.org
```

不能假设这个子域名已经可用，必须先检查 DNS 控制能力。

部署 Caddy，配置自动 HTTPS。

不要修改现有博客的 DNS 记录。

公网仅开放必要端口：

```
22   SSH（尽量限制来源）
80   HTTP
443  HTTPS
```

FastAPI 内部端口不能直接暴露公网。

正式向公网开放前，核对阿里云实例的备案和接入要求；开发阶段不需要因此阻塞本地开发。

## 8.4 数据备份

实现简单的定时备份：

- SQLite 数据库一致性备份。
- 附件目录备份。
- 保留最近 7 份每日备份。
- 提供手动导出命令。
- 定期验证备份可恢复。

数据库和附件必须作为一个整体备份。

# 九、SDK 发布与版本管理

SDK 是独立项目，需要能够被多个 Android 仓库复用。

建议使用 Gradle Maven Publish：

```
groupId: com.kkkkikun.openfeedback
artifactId: openfeedback-compose
version: 0.1.0
```

开发阶段允许使用本地 Maven 仓库或 Gradle includedBuild。

稳定后，在现有 ECS 上提供一个只读静态 Maven 仓库，使用 HTTPS 下载 SDK。

各项目必须固定 SDK 版本：

```
implementation(
    "com.kkkkikun.openfeedback:openfeedback-compose:0.1.0"
)
```

禁止使用动态版本 `+`。

每次更新 SDK：

1. 修改版本号。
2. 更新 CHANGELOG。
3. 执行 SDK 单元测试。
4. 执行示例集成测试。
5. 发布新版本。
6. 各 App 独立升级。
7. 不自动升级全部项目。

# 十、四个项目的接入计划

## 10.1 OIT-Net-Portal

- 检查当前 Kotlin/Compose 结构。
- 在设置页或关于页面加入「意见反馈」入口。
- 集成 OpenFeedback SDK。
- 不附带校园网账号、密码、Cookie。
- 不自动收集认证日志。
- 真机验证提交和后台接收。

## 10.2 LocalPixt（显影）

- 在设置页加入「意见反馈」。
- 使用统一 Compose 窗口。
- 不上传原始照片。
- 不上传完整 Room 数据库。
- 不上传 RN50、ViT 模型或 HNSW 索引。
- 不自动附带照片路径和用户搜索历史。
- 用户主动授权后才附带脱敏诊断信息。

## 10.3 qianxian（牵线）

- 在设置页或关于页面加入反馈入口。
- 支持 Bug 和功能建议。
- 不默认上传完整对话。
- 不默认上传 Prompt、模型上下文和工具执行参数。
- 诊断信息必须由宿主应用过滤敏感内容后提供。

## 10.4 SchoolWall（校园墙）

先检查当前项目实际技术栈。

如果当前前端为 uni-app 或小程序：

- 不强行接入 Android Compose SDK。
- 复用相同的 REST API。
- 编写轻量 JS/uni-app 反馈组件。
- 保持统一 appId。
- 统一上传规则和数据格式。

如果存在原生 Android 客户端，再单独使用 Android SDK。

# 十一、测试计划

## 11.1 服务端测试

必须覆盖：

- 正常提交。
- 非法 appId。
- 空内容。
- 超长内容。
- 非法附件。
- 超大附件。
- 重复 submissionId。
- 匿名访问管理接口。
- 管理员登录。
- 未授权查看附件。
- 状态修改。
- 内部备注。
- 数据库重启持久性。
- 备份恢复。

## 11.2 Android SDK 测试

必须覆盖：

- SDK 初始化。
- Compose 页面正常显示。
- 四种反馈类型。
- 必填字段校验。
- 图片选择。
- 图片压缩。
- 上传成功。
- 服务端错误。
- 断网提交。
- 网络恢复重试。
- 重复请求不重复创建记录。
- 页面关闭和重新打开。
- 深色模式。
- 屏幕旋转和进程重建时的数据安全。

## 11.3 真机验收

先在一个现有 App 中接入。

完整流程：

1. 手机安装测试 APK。
2. 打开现有 App。
3. 进入意见反馈。
4. 输入一条测试反馈。
5. 附加截图。
6. 提交。
7. 在管理后台看到对应记录。
8. 查看截图和设备信息。
9. 修改状态为处理中。
10. 添加内部备注。
11. 重新打开后台，确认数据持久化。
12. 断网提交一条新反馈。
13. 恢复网络，验证自动重试。
14. 检查没有重复记录。

完成后再接入其余三个项目。

# 十二、分阶段实施顺序

## P0：项目审查与架构确定

- 检查四个现有项目的技术栈。
- 检查 Kotlin、Compose 和 Gradle 版本。
- 确认 SchoolWall 的实际接入方式。
- 创建 OpenFeedback 仓库。
- 完成 API 数据结构和 SDK 接口设计。
- 输出架构文档。

验收：架构和兼容性问题明确，不修改现有 App。

## P1：服务端 MVP

- 实现 FastAPI。
- 实现 SQLite 数据库。
- 实现应用注册。
- 实现反馈提交。
- 实现附件上传。
- 实现重复请求保护。
- 实现管理后台。
- 实现登录鉴权和权限检查。

验收：可以通过 HTTP 测试工具提交反馈，并在后台查看。

## P2：Android SDK

- 实现 Compose 反馈窗口。
- 实现表单验证。
- 实现图片选择与压缩。
- 实现设备信息采集。
- 实现 API Client。
- 实现离线队列。
- 实现 WorkManager 自动重试。
- 实现主题适配。
- 发布 0.1.0 测试版本。

验收：独立 SDK 能够正常集成到现有 Android 项目。

## P3：服务器部署

- 检查 ECS。
- 安装或检查 Docker。
- 配置 Caddy。
- 配置 HTTPS。
- 部署 API 和管理后台。
- 初始化管理员。
- 配置数据卷。
- 配置备份和日志轮转。
- 完成公网连通性测试。

验收：服务能够持续运行，重启后数据不丢失。

## P4：现有 App 接入

- 先选择一个最适合的现有 App。
- 完成完整真机测试。
- 修复 SDK 兼容性问题。
- 发布稳定 SDK。
- 依次接入其他项目。
- SchoolWall 根据实际技术栈使用 SDK 或 REST API。

验收：所有目标项目均可以提交反馈。

## P5：稳定性与文档

- 完整测试离线队列。
- 检查服务端资源占用。
- 检查附件存储。
- 验证备份恢复。
- 完成 SDK 使用文档。
- 完成服务端运维文档。
- 完成接入示例。
- 整理 Git 提交和版本标签。

# 十三、Agent 执行规则

这是一个独立的长期工程，请遵循以下要求：

1. 先检查现有项目，再制定兼容性方案，不要凭猜测修改依赖。
2. 所有开发工作集中在独立 OpenFeedback 仓库。
3. 不要为了测试创建新的 Android 应用。
4. 不要擅自重构四个现有项目。
5. 第一阶段先完成服务端和 SDK，再进行实际项目接入。
6. 不要将用户数据、照片、日志、数据库上传到外部第三方服务。
7. 不要把管理员密钥、SSH 密钥、密码提交到 Git。
8. 不要把秘密写入 APK。
9. 所有接口必须有错误处理和测试。
10. 所有关键阶段必须有 Git 提交。
11. 每个阶段完成后更新文档和测试结果。
12. 不能用 Mock 测试结果代替真实服务器和真机验收。
13. 不得宣称未实际执行的部署或测试已经完成。
14. 如果遇到需要购买资源、扩大权限、修改 DNS 或开放额外网络端口的情况，先报告，不擅自操作。
15. 发现服务器内存不足时，优先优化架构，不要直接购买第二台服务器。

## 最终交付物

必须交付：

- 独立 OpenFeedback Git 仓库。
- 可构建的 Android SDK。
- 可部署的 FastAPI 服务端。
- 可用的 Web 管理后台。
- Docker Compose 部署配置。
- 数据库迁移和备份脚本。
- API 文档。
- Android SDK 集成文档。
- 四个 App 的接入记录。
- 自动化测试报告。
- 至少一个现有 App 的真实设备验收记录。
- 完整 Git 提交记录和稳定版本标签。

**最终完成标准：**

从任意一个已接入的 App 内提交反馈，服务端真实收到并保存，开发者能够在统一后台查看反馈、附件、设备信息，修改处理状态；断网情况下反馈不会丢失，网络恢复后能够自动重试。

只有真实完成以上闭环，OpenFeedback 1.0 才算交付。