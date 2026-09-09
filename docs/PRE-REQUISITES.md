# ROTO-KB 前置条件清单

仓库已创建，当前不需要再新建仓库。RAG 与 ROTO Loop Engineering 可以继续拆仓并行；只有契约和真实 HTTP 联调需要在后续汇合。

## 现在必须完成

| 前置项 | 当前状态 | 通过标准 |
|---|---|---|
| EvidencePackage v1 字段冻结 | 未完成，存在字段漂移 | 两仓对 `source_uri/source_hash/document_version/security_scope`、`no_match`、`degradation_reasons[]` 达成一致 |
| 跨仓契约包 | 未完成 | `contracts/` 中有 JSON Schema、OpenAPI、success/empty/degraded/error fixtures；两仓 CI 可离线运行 |
| 项目契约交付 | 未完成 | ROTO PRD/SDD/T02 以及实现所需 Schema 有 commit/SHA-256 快照；服务器不依赖 `E:/Project/ROTO/...` |
| GitHub 质量门 | 未完成 | public `main` 启用 PR、CI 必过、secret scanning；无 `.pem`、`.env`、权重和生成索引 |

## 首次真实索引前

- 不需要现在手工安装 Qdrant；G1-G4 可使用 fake/fixture 完成，首次本地真实索引再由 Compose 启动固定版本 Qdrant，服务器部署时才需要 Docker。
- 确认 DashScope API key 所属地域、endpoint、Embedding 模型和维度；默认候选为 `text-embedding-v4`，维度必须由 capability probe 校验。
- 决定是否开启 DashScope LLM 摘要/关系抽取；建议 V1 保持关闭。
- 准备 `ROTO_KB_READ_TOKEN`、`ROTO_KB_ADMIN_TOKEN`、`QDRANT_API_KEY` 三套不同 secret；不提交聊天、Git 或知识目录。
- 完成跨仓 contract test 后，才能把 KB-002/KB-601 标记为 ready。

## 服务器部署前

- 明确允许对 `54.172.101.190` 做 Docker、nginx、systemd、目录和防火墙变更。
- 只读检查 Docker、nginx、磁盘、端口和目标目录；记录旧 `kb-server` 的 health/进程/端口基线，不读取其知识内容。
- 创建 `/home/ec2-user/roto-kb`、`/data/roto-kb`、`/etc/roto-kb`、`/var/log/roto-kb` 独立命名空间，并通过隔离脚本验收。
- 修复部署用 SSH 私钥 ACL：当前 `ladder.pem` 对 `Authenticated Users` 可读，Windows OpenSSH 会拒绝使用；原文件不要提交仓库。

## 公网生产前

- 提供域名并启用 HTTPS；IP + HTTP 仅用于受限临时验收，不能长期承载 Bearer Token。
- 完成 Qdrant snapshot、source/manifest、BM25/relations、registry 的同 release 备份和恢复演练。
- 完成新旧服务独立停止、reload、activate、rollback 验收；旧服务数据、进程、端口、目录和日志不变。

## 可以后补

- CORA、PropNet、MatOnto 的实际文件导入：三者已在 manifest 保留，其中 MatOnto 仅链接和映射；都不是 V1 active 启动依赖。
- 材料牌号/实验属性离线批次：必须带状态、温度、单位、来源、hash 和许可。
- SciBERT、MatSciBERT 权重及 Hunyuan3D：不属于 V1 RAG 部署。
