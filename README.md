# OpenFeedback

多应用统一反馈系统：一套轻量、可自托管的反馈服务，加上给各平台用的客户端。

用户在自己的 App 内提交反馈（可带截图），开发者在同一个后台查看、筛选、
改处理状态、写内部备注。

```
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ OIT-Net-Portal│   │  LocalPixt    │   │  SchoolWall   │
│ Kotlin/Compose│   │ Kotlin/Compose│   │  uni-app/Vue  │
└───────┬───────┘   └───────┬───────┘   └───────┬───────┘
        │  openfeedback-core/compose               │
        └──────────────┬───────────────┬──────────┘
                       │  HTTPS         │ REST
                       └───────┬───────┘
                       ┌───────▼────────┐
                       │ OpenFeedback   │
                       │ FastAPI+SQLite │
                       │ + Web 管理后台  │
                       └────────────────┘
```

## 特点

- **统一后台**：所有应用的反馈在一处看，按应用/状态/类型筛选，全文搜索。
- **可带截图**：用户主动挑选，自动压缩到 2 MB 以内并剥掉 EXIF。
- **断网不丢**：提交失败进本机队列，联网后自动重试；`submissionId` 保证不重复。
- **匿名提交**：不需要注册，不要求任何账号。
- **隐私克制**：不带 IMEI、序列号、MAC 地址、位置、账号、Token；
  客户端 IP 只存哈希。
- **轻量**：一个 FastAPI 进程 + 一个 SQLite 文件，2 vCPU / 2 GB 内存足够。
- **无第三方依赖的 Android 客户端**：只用框架自带的 `HttpURLConnection`，
  不会给宿主 App 引入 OkHttp / Retrofit 的版本冲突。

## 仓库结构

| 目录 | 内容 |
|---|---|
| `server/` | FastAPI 服务、SQLite 模型、迁移、管理后台、测试 |
| `android-sdk/` | Android SDK（`core` + `compose`），发布为 Maven 构件 |
| `integrations/schoolwall/` | 校园墙的 uni-app 反馈组件 |
| `integrations/qianxian/` | 牵线（Rust / Makepad）的接入说明与代码骨架 |
| `deploy/` | Docker Compose、Caddy、备份与构建脚本 |
| `docs/` | 架构、API、接入、部署文档 |

## 快速开始

### 服务端

```bash
cd server
python -m venv .venv
.venv/bin/pip install -r requirements.txt
OF_ADMIN_PASSWORD=change-me .venv/bin/python -m uvicorn app.main:app --reload
```

打开 <http://127.0.0.1:8080/admin> 登录。

### Android SDK

```bash
cd android-sdk
./gradlew assemble     # 构建
./gradlew test         # 单元测试
```

宿主 App 依赖：

```kotlin
// settings.gradle.kts
maven { url = uri("https://<反馈服务地址>/maven/") }

// app/build.gradle.kts
implementation("com.kkkkikun.openfeedback:openfeedback-compose:0.1.0")
```

用法见 [docs/INTEGRATION.md](docs/INTEGRATION.md)。

### 部署

```bash
export OF_DEPLOY_HOST=<服务器地址> OF_DEPLOY_PORT=22 OF_DEPLOY_USER=root
export OF_PUBLIC_HOST=https://<服务地址>
./deploy/deploy.sh
```

脚本会同步代码、生成 `.env`（管理员密码与 IP 盐值随机生成，只打印一次）、
构建镜像、拉起 Compose 栈，并等待服务健康。

**前置条件**：服务器上需要能访问容器镜像仓库与 PyPI（受限网络下用
`.env` 里的 `OF_BASE_IMAGE` / `OF_PIP_INDEX_URL` 指向镜像），
并且**公网能访问 80 与 443**，否则 Caddy 拿不到证书。

## 文档

| 文档 | 内容 |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 架构、数据模型、兼容性矩阵 |
| [docs/API.md](docs/API.md) | HTTP 接口与限制 |
| [docs/INTEGRATION.md](docs/INTEGRATION.md) | 怎么把一个新应用接进来 |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | 部署、备份、升级 |
| [docs/SECURITY.md](docs/SECURITY.md) | 安全边界与隐私约定 |

## 接入的应用

| 应用 | 平台 | 接入方式 |
|---|---|---|
| OIT-Net-Portal | Android（Kotlin/Compose） | `openfeedback-core`，保留自己的表单 |
| LocalPixt | Android（Kotlin/Compose） | `openfeedback-compose` |
| SchoolWall | uni-app（小程序 / H5 / App） | REST 组件 |
| 牵线 | Android（Rust/Makepad） | REST（Rust 侧实现） |

## 许可

MIT，见 [LICENSE](LICENSE)。
