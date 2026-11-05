# OpenFeedback API

- 版本：1.0.0
- 基地址：`https://<反馈服务地址>`

## 公共接口

### `GET /api/v1/health`

存活探针，不访问数据库。

```json
{ "status": "ok", "service": "openfeedback" }
```

### `POST /api/v1/feedback`

提交一条反馈。使用 `multipart/form-data`。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `payload` | string (JSON) | 是 | 反馈元数据 |
| `attachments` | file | 否 | 截图，最多 3 张 |

`payload` 的字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `appId` | string | 是 | 应用标识，最长 64 |
| `submissionId` | string | 是 | 客户端生成的唯一标识，8–64 字符 |
| `type` | string | 是 | `bug` / `feature` / `experience` / `other` |
| `title` | string | 否 | 最长 255 |
| `description` | string | 是 | 最长 8000，不能为空白 |
| `contact` | string | 否 | 最长 255 |
| `appVersion` | string | 否 | 最长 64 |
| `appBuild` | string | 否 | 最长 64 |
| `sdkVersion` | string | 否 | 最长 64 |
| `androidVersion` | string | 否 | 最长 32 |
| `apiLevel` | int | 否 | 1–99 |
| `manufacturer` | string | 否 | 最长 64 |
| `model` | string | 否 | 最长 128 |
| `locale` | string | 否 | 最长 32 |
| `diagnostics` | string | 否 | 最长 8000，需宿主自行脱敏 |

**兼容旧分类**：`issue` → `bug`，`suggestion` → `feature`，`ux` → `experience`，
`problem` → `bug`。未知分类报 422。

请求示例：

```bash
curl -X POST https://feedback.example.com/api/v1/feedback \
  -F 'payload={"appId":"localpixt","submissionId":"0f7a...","type":"bug","title":"闪退了","description":"打开设置页就闪退","appVersion":"1.0.0"}' \
  -F 'attachments=@screenshot.png;type=image/png'
```

成功响应 `200`：

```json
{
  "ok": true,
  "feedback_id": 42,
  "submission_id": "0f7a...",
  "duplicate": false,
  "created_at": "2026-11-05T07:25:00Z"
}
```

`duplicate: true` 表示这个 `submissionId` 之前已经收到过，返回的是原记录。

错误码：

| 状态码 | 含义 |
|---|---|
| 400 | `payload` 不是合法 JSON |
| 403 | 该应用已停用接收反馈 |
| 404 | 未知 `appId` |
| 413 | 请求体过大 |
| 422 | 字段不合法、附件不是允许的图片、附件超限或超数量 |
| 429 | 提交过于频繁（每 `appId`+IP 每小时 10 条） |

## 管理接口

全部需要管理员会话（Cookie），改状态的接口还需要 `X-CSRF-Token` 头。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/admin/login` | 登录，返回 `csrfToken` |
| POST | `/api/v1/admin/logout` | 退出 |
| GET | `/api/v1/admin/session` | 当前登录者与 CSRF token |
| GET | `/api/v1/admin/apps` | 应用列表 |
| GET | `/api/v1/admin/feedback` | 反馈列表，支持 `appId` / `status` / `type` / `q` / `page` |
| GET | `/api/v1/admin/feedback/{id}` | 反馈详情（含附件、备注、状态历史） |
| PATCH | `/api/v1/admin/feedback/{id}` | 改状态，body `{"status":"RESOLVED"}` |
| POST | `/api/v1/admin/feedback/{id}/notes` | 加内部备注，body `{"content":"..."}` |

列表与详情都带 `submission_id`（客户端生成的提交标识）。它是去重的依据：
客户端离线补发时带同一个 `submissionId`，服务端据此返回原记录而不新建。
后台能看到它，才能判断两条记录是不是同一次提交的重复。
| GET | `/api/v1/admin/attachments/{id}` | 下载截图（只有登录后可用） |

登录：

```bash
curl -X POST https://feedback.example.com/api/v1/admin/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"..."}' -c cookies.txt
```

## Web 管理后台

| 路径 | 说明 |
|---|---|
| `/admin` | 反馈列表、筛选、搜索、分页 |
| `/admin/feedback/{id}` | 详情、状态、备注、截图 |
| `/admin/login` | 登录页 |

后台是服务端渲染的模板，没有独立的前端构建产物。

## 限制一览

| 项 | 值 |
|---|---|
| 单条反馈描述 | 8000 字符 |
| 标题 | 255 字符 |
| 单张附件 | 2 MB |
| 附件数量 | 3 张 |
| 请求体 | 12 MB |
| 提交频率 | 每 `appId`+IP 每小时 10 条 |
| 附件格式 | JPEG / PNG / WebP（按魔数判定） |
