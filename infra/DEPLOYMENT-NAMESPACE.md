# 远端隔离命名空间

| 项目 | ROTO-KB | 现有第三方知识库 |
|---|---|---|
| systemd | `roto-kb.service` | `kb-server.service` |
| App | `127.0.0.1:8710` | `127.0.0.1:8700` |
| Qdrant | embedded under `/data/roto-kb/index/qdrant` (no public port; optional server mode `127.0.0.1:6334`) | embedded legacy store |
| Public | `443 /roto-kb/` | `/` |
| Code | `/opt/roto-kb` (example) | `/opt/legacy-kb-server` (example) |
| Source | `/data/roto-kb/sources` | `/data/knowledge-base` |
| Index | `/var/lib/roto-kb/index` (example) | `/var/lib/legacy-kb-server/data` (example) |
| Logs | `/var/log/roto-kb` | `/var/log/legacy-kb-server.log` (example) |

部署、备份、reload、回滚和清理脚本必须拒绝解析到 `/data/knowledge-base`、`/var/lib/legacy-kb-server` 或 `/opt/legacy-kb-server` 的路径。

公网由 nginx 在 443 终止 TLS 后转发 `/roto-kb/` 到 `127.0.0.1:8710`，访问基址由本地配置提供。80 保留旧服务根路径，不代理 ROTO-KB；应用和 Qdrant 端口不得绑定 `0.0.0.0`；读取使用独立 read token，变更索引使用独立 admin token。

ROTO-KB 默认使用本机嵌入式 Qdrant（`QDRANT_MODE=embedded`），数据写入 `/data/roto-kb/index/qdrant`，不对公网或宿主机端口暴露。可选的独立 Docker Server 模式仍保留在 `infra/docker-compose.yml`（`127.0.0.1:6334->6333`），仅在明确切换 `QDRANT_MODE=server` 时使用，并要求独立 `QDRANT_API_KEY`。collection 前缀固定 `roto_kb_`，线上 alias 目标为 `roto_kb_active`。
