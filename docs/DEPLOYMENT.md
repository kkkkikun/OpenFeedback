# 部署与运维

- 版本：1.0.0
- 最后更新：2026-11-05

## 目标环境

| 项 | 值 |
|---|---|
| 系统 | Ubuntu 24.04 |
| 规格 | 2 vCPU / 2 GB 内存 / 40 GB 磁盘 |
| 网络 | 3 Mbps 公网带宽 |

2 GB 内存下跑得下一个 FastAPI 进程（限 512 MB）+ Caddy（限 128 MB）。

## 组件

```
Caddy ──TLS──▶ FastAPI (1 worker) ──▶ SQLite (WAL)
  │                                        │
  ├── /maven/ 静态 SDK 仓库                 └── /data/attachments
  └── /admin  管理后台
```

- **一个 uvicorn worker 是刻意的**：SQLite 加上进程内的限流计数器，
  只有在单写入者下才是正确的。
- Caddy 负责 TLS、静态文件与反向代理。FastAPI 的端口**不发布到宿主机**。

## 首次部署

```bash
export OF_DEPLOY_HOST=<服务器地址>
export OF_DEPLOY_PORT=22
export OF_DEPLOY_USER=root
export OF_PUBLIC_HOST=https://<服务地址>
export ACME_EMAIL=<你的邮箱>

./deploy/deploy.sh
```

脚本会：

1. 同步代码到 `/opt/openfeedback`；
2. 生成 `.env`（管理员密码与 IP 盐值随机生成，**管理员密码只打印一次**）；
3. 同步 SDK 的 Maven 仓库；
4. 下载 Caddy 发行包并构建镜像；
5. 拉起 Compose 栈；
6. 等待 API 健康，并报告公网地址是否已可访问。

### 网络受限的环境

```bash
# .env 里指定镜像
OF_BASE_IMAGE=public.ecr.aws/docker/library/python:3.12-slim
OF_CADDY_BASE_IMAGE=public.ecr.aws/docker/library/alpine:3.20
OF_PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
```

Caddy 的发行包由**宿主机**下载后拷进镜像（`deploy/deploy.sh` 的第 4 步），
所以镜像构建本身不需要访问 GitHub。

### 公网 HTTPS

Caddy 用 Let's Encrypt 的 `shortlived` profile 签发证书。
IP 地址证书**必须**是短期的，这是 Let's Encrypt 的策略。

**前置条件：公网能访问 80 与 443。** 否则验证器会报
`Timeout during connect (likely firewall problem)`，证书拿不到。
Caddy 会自己重试，端口放通后通常几分钟内自动签发成功。

如果后面加了域名，改 `.env` 里的 `OF_PUBLIC_HOST` 再重新部署即可；
短周期证书对域名同样有效。

## 日常运维

### 查看状态

```bash
ssh root@<服务器> 'cd /opt/openfeedback/deploy && docker compose ps'
ssh root@<服务器> 'cd /opt/openfeedback/deploy && docker compose logs -f api'
```

### 升级

```bash
./deploy/deploy.sh
```

脚本是幂等的：`.env` 里已有的密码与盐值会被保留。

### 备份

```bash
ssh root@<服务器> 'bash /opt/openfeedback/deploy/backup.sh'
```

- 用 SQLite 自己的 `.backup` API 拿一致性副本（服务在写的时候也安全）；
- 附件目录一起打包；
- 默认保留最近 7 份每日备份。

**数据库和附件必须作为一个整体备份**：附件表里的一行如果找不到对应的文件，
就是一条坏记录。

### 恢复

```bash
ssh root@<服务器> 'cd /opt/openfeedback/deploy && docker compose stop api'
ssh root@<服务器> 'cd /var/backups/openfeedback && tar -xzf openfeedback-<时间戳>.tar.gz'
ssh root@<服务器> 'cd /opt/openfeedback && cp -r <时间戳>/openfeedback.db ofdata/openfeedback.db && cp -r <时间戳>/attachments/. ofdata/attachments/'
ssh root@<服务器> 'cd /opt/openfeedback/deploy && docker compose start api'
```

恢复后要检查附件目录里的文件属主与容器里的 `openfeedback` 用户一致。

### 磁盘

```bash
ssh root@<服务器> 'du -sh /var/lib/docker/volumes/openfeedback_ofdata'
```

附件容量预警阈值 5 GB。反馈记录本身不自动清理。

## 资源限制

| 服务 | 内存上限 | CPU |
|---|---|---|
| api | 512 MB | 1.0 |
| caddy | 128 MB | 0.5 |

容器都带 `no-new-privileges:true` 和 `cap_drop: ALL`。

## 监控

```bash
# 服务存活
curl -fsS https://<服务地址>/api/v1/health

# 磁盘
ssh root@<服务器> 'df -h /'

# 容器资源
ssh root@<服务器> 'docker stats --no-stream'
```

## 停用某个应用

不想再收某个应用的反馈时，把 `apps` 表里那一行 `enabled` 置为 false：

```bash
ssh root@<服务器> "cd /opt/openfeedback/deploy && docker compose exec -T api python -c \"
import sqlite3
db = sqlite3.connect('/data/openfeedback.db')
db.execute(\\\"UPDATE apps SET enabled = 0 WHERE app_id = 'schoolwall'\\\")
db.commit()
print('disabled')
\""
```

客户端会收到 403「该应用已停用接收反馈」。
