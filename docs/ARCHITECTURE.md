# OpenFeedback 架构

- 版本：1.0.0
- 最后更新：2026-11-05

## 目标

给多个既有应用提供一套统一的、应用内的反馈能力：用户在原 App 内提交，
开发者在同一个后台查看和处理。系统本身轻量、可自托管、不引入重型依赖。

## 组成

```
┌──────────────────────────────────────────────────────┐
│ 宿主应用                                              │
│                                                      │
│  OIT-Net-Portal (Kotlin/Compose)   LocalPixt (同)      │
│  SchoolWall (uni-app/Vue3)        牵线 (Rust/Makepad) │
│         │                            │               │
│         └──────────┬─────────────────┘               │
│                    │                                 │
│      ┌─────────────▼──────────────┐                  │
│      │  openfeedback-core         │                  │
│      │  · HTTP 客户端              │                  │
│      │  · 本机离线队列             │                  │
│      │  · WorkManager 重试         │                  │
│      ├─────────────────────────────┤                  │
│      │  openfeedback-compose       │                  │
│      │  · Compose 反馈窗口         │                  │
│      └─────────────┬──────────────┘                  │
└────────────────────┼─────────────────────────────────┘
                     │ HTTPS  multipart/form-data
          ┌──────────▼───────────┐
          │  OpenFeedback API    │
          │  FastAPI + SQLite    │
          │  + Web 管理后台      │
          └──────────────────────┘
```

## 服务端

| 模块 | 技术 |
|---|---|
| API | Python FastAPI |
| 数据验证 | Pydantic v2 |
| ORM | SQLAlchemy 2.0（同步） |
| 数据库 | SQLite（WAL 模式） |
| 迁移 | Alembic |
| Web 后台 | Jinja2 + 原生 JS/CSS |
| 反向代理 | Caddy（自动 HTTPS） |
| 部署 | Docker Compose |

**一个 uvicorn worker 是刻意的**：SQLite 加上进程内的限流计数器，
只有在单写入者下才是正确的。

### 数据模型

| 表 | 作用 |
|---|---|
| `apps` | 应用注册表。`app_id` 是公开标识，不是凭据 |
| `feedback` | 反馈本体。`(app_id, submission_id)` 唯一，保证幂等 |
| `feedback_attachments` | 截图索引。文件名由服务端生成，客户端不能指定路径 |
| `feedback_notes` | 内部备注，只有管理员可见 |
| `feedback_status_history` | 状态流转历史 |
| `admin_users` | 后台账号，Argon2id 密码哈希 |
| `admin_sessions` | 服务端会话，token 只存哈希 |

### 反馈状态

`NEW`（待处理）→ `IN_PROGRESS`（处理中）→ `RESOLVED`（已解决）/ `CLOSED`（已关闭）

### 幂等

客户端为每次提交生成一个 `submissionId`（UUID），在入队与上传之间保持不变。
服务端对 `(app_id, submission_id)` 建唯一约束：

- 重复提交返回原记录并带 `duplicate: true`，不新建行；
- 因此「上传成功但响应丢失 → 客户端重试」不会产生重复反馈。

### 安全边界

- `appId` 是公开标识；APK 里没有任何服务端凭据。
- 客户端 IP 只存哈希（加盐 SHA-256），用于限流。
- 限流：每 `(appId, IP)` 每小时 10 条，可配置。
- 附件按**魔数**校验（只接受 JPEG / PNG / WebP），不信 MIME 与扩展名；
  单张上限 2 MB，最多 3 张，总请求体上限 12 MB。
- 附件存在私有目录，文件名随机生成；只有通过管理员鉴权才能下载。
- 后台会话：HttpOnly + Secure + SameSite Cookie，服务端只存 token 哈希；
  改状态/加备注需要 CSRF token。
- 密码 Argon2id；登录接口限流。
- 反馈内容不进日志（日志只记 id、app、类型、附件数）。

## 客户端

### Android SDK

| 模块 | 依赖 | 用途 |
|---|---|---|
| `openfeedback-core` | 无第三方依赖（只用 `HttpURLConnection`） | 传输、离线队列、重试 |
| `openfeedback-compose` | Compose | 反馈窗口 |
| `openfeedback-testing` | — | 宿主 App 的契约测试辅助 |

**为什么用 `HttpURLConnection`**：它是 Android 框架自带的，
接入 SDK 不会给宿主 App 增加任何第三方依赖，也就不会和宿主已有的
OkHttp / Retrofit 产生版本冲突。

**为什么拆 core 与 compose**：只想换传输链路的宿主（例如已有自己 UI 的
OIT-Net-Portal）只依赖 core；要用 SDK 自带反馈窗口的宿主才依赖 compose。

### 离线队列

```
noBackupFilesDir/openfeedback/queue/<submissionId>/
    submission.json     元数据
    attachment-0        截图文件
```

- 图片字节**不放** WorkManager 的 `Data`（只有几 KB 限制）。
- 元数据与附件分开存，附件路径与 JSON 分开。
- 上传成功后删除本地副本。
- 队列有容量上限（默认 20），超出时丢弃最旧的一条，避免占满磁盘。
- WorkManager 任务带 `NetworkType.CONNECTED` 约束与指数退避。

### uni-app 组件

`SchoolWall` 用同一套 REST 接口，组件是纯 JS + Vue3，
不依赖 uni-app 之外的任何东西。

### Rust 客户端

牵线的 Android 端是 Rust/Makepad，不是 Kotlin/Compose，
所以它直接实现同一套 wire format（multipart + `payload` JSON），
不依赖 Android SDK。

## 兼容性矩阵

| 应用 | 技术栈 | 接入方式 | SDK 版本约束 |
|---|---|---|---|
| OIT-Net-Portal | Kotlin + Compose，AGP 8.7.3，Kotlin 2.0.21，compileSdk 35，minSdk 26 | `openfeedback-core` | 保留自己的表单 |
| LocalPixt | Kotlin + Compose，AGP 8.5.2，Kotlin 2.0.21，compileSdk 35，minSdk 28 | `openfeedback-compose` | SDK `minSdk 26` |
| SchoolWall | uni-app + Vue 3 | REST 组件 | 无 |
| 牵线 | Rust + Makepad | REST（Rust 侧实现） | 无 |

SDK 以 AGP 8.5.2、Kotlin 2.0.21、Compose BOM 2024.12.01 构建，
两个 Kotlin 宿主都能消费。

## 部署

单台 ECS：

```
Caddy  ──TLS──▶  FastAPI (1 worker)  ──▶  SQLite (WAL)
  │                                          │
  └──── /maven/ 静态 SDK 仓库                 └── /data/attachments
```

- Caddy 用 Let's Encrypt 的 `shortlived` profile 签发 IP 证书
  （IP 证书必须是短期的，这是 Let's Encrypt 的策略）。
- 数据与附件放在同一个卷里，备份时一起打包。
- 每日备份保留 7 份。

## 明确不做

- 不做独立 App、用户注册、公开社区、点赞投票、即时聊天。
- 不接入 AI 自动分类。
- 不自动录屏、不监听系统截图、不自动采集 logcat。
- 不自动上传照片原件、数据库、模型文件、向量索引、聊天记录。
- 不引入 Redis / Kafka / PostgreSQL / 对象存储 / 微服务。
