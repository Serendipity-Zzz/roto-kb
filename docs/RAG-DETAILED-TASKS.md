# ROTO-KB RAG 详细子任务

| 属性 | 内容 |
|---|---|
| 文档版本 | v1.1 |
| 对齐文档 | `docs/PRD.md` v1.4、`docs/SDD.md` v1.2 |
| 参考输入 | `知识库服务子任务设计文档.md`（M1-M14、T1.1-T14.3） |
| 目标 | 将 RAG 服务做成可独立开发、可独立发布、可恢复、可通过 443 安全访问的服务 |
| 状态 | 任务设计，尚未开始实现 |

## 0. 执行规则

每个任务必须提交代码或配置、测试、运行证据和回滚说明。任务状态为 `todo -> doing -> review -> accepted`；失败回到 `doing`。不提交 API key、SSH 私钥、生成索引、Qdrant snapshot 或模型权重。

每个任务交付记录：

```markdown
Task: KB-xxx
Status: review
SDD refs: 章节号
Changed files:
Tests and outputs:
Contract/migration impact:
Security/isolation checks:
Rollback procedure:
Known limitations:
Next unlocked tasks:
```

阶段门：

```text
G0 文档与契约
 -> G1 空库和配置
 -> G2 离线摄取
 -> G3 向量/BM25/关系索引
 -> G4 API 和检索
 -> G5 release 构建、评测、激活、回滚
 -> G6 443 部署和运维
 -> G7 ROTO 主线联调
 -> G8 内容持续运营
```

G1-G4 可以先使用 fake provider 和 fixture；G6 需要用户明确允许服务器变更；G7 需要两仓契约冻结。普通内容补充不需要重新部署应用，只需要新 release。

## 1. G0：契约、来源和安全边界

### KB-000 文档基线冻结

- 依赖：无。
- 输入：PRD、SDD、参考 SDD、图谱部署清单。
- 输出：版本记录、差异清单、架构决策记录。
- 实现：确认独立 Qdrant Server 替代参考文档的嵌入式 Qdrant；确认阿里云 DashScope 为唯一模型供应商；确认内容可后补；确认 active/previous release。
- 验收：没有“嵌入式 Qdrant”“8700 公网”“无鉴权”“Windows 路径”进入生产方案。
- 回滚：仅文档回滚。

### KB-001 EvidencePackage v1 契约

- 依赖：KB-000。
- 输出：`contracts/evidence-package.v1.schema.json`、OpenAPI、success/empty/degraded/error fixtures。
- 实现：冻结 `query/index_release_id/results/degraded/degradation_reasons/no_match`；snippet 使用 `source_uri/source_hash/document_version/security_scope`；定义 `match_type`、citation、错误码和分页。
- 验收：ROTO 主线和 ROTO-KB 均可离线校验 fixture；禁止两边各自定义同名 v1。
- 回滚：破坏性字段进入 v2，保留 v1。

### KB-002 项目契约快照

- 依赖：KB-001。
- 输入：ROTO PRD/SDD/T02、相关 Schema 和测试。
- 输出：commit/SHA-256 记录或可发布的 `project-contracts` 包。
- 实现：服务器和 CI 不读取 `E:/Project/ROTO/...`；manifest 只记录本机外部路径作为开发来源。
- 验收：Linux 环境可以只依赖快照构建和运行契约测试。
- 回滚：恢复上一契约快照，保留 hash 记录。

### KB-003 资源与许可证门

- 依赖：KB-000。
- 输出：source manifest、attribution、checksum、license gate。
- 实现：active 仅允许 QUDT、IOF Core、W3C vocabularies、ROTO seed；CORA/PropNet 为 reference-only；MatOnto 为 link-and-map-only；API 数据源默认 disabled。
- 验收：每个 source 有 URL、revision、hash、license、attribution、security scope；未决许可不会进入 active。
- 回滚：内容 PR revert 或将 source 设为 quarantined/disabled。

### KB-004 仓库质量门

- 依赖：KB-000。
- 输出：branch protection、CI 必过、secret scanning、文件扫描规则。
- 验收：public `main` 需要 PR/CI；`.pem/.env`、模型权重、生成索引和 snapshot 被拒绝。
- 回滚：调整规则，不删除历史知识内容；若密钥曾提交，立即轮换。

## 2. G1：空库、配置和领域模型

### KB-101 项目脚手架

- 依赖：G0。
- 输出：Python 3.12 src layout、CLI、ASGI 空入口、锁定依赖、Ruff/mypy/pytest。
- 验收：干净环境安装成功；`python -m roto_kb --help`、服务启动和基础 CI 通过。
- 回滚：删除脚手架提交，无数据迁移。

### KB-102 Domain models 与 ports

- 依赖：KB-001。
- 输出：Source、Document、Chunk、Relation、LintReport、IndexRelease、EvidencePackage、BuildJob；provider/index/catalog ports。
- 实现：稳定 ID/hash；额外字段策略显式；domain 不依赖 FastAPI、Qdrant SDK 或文件系统。
- 验收：JSON round-trip、非法状态、未知字段、稳定 ID golden tests 通过。

### KB-103 `rel_empty` 与空库 API

- 依赖：KB-102。
- 输出：`rel_empty` runtime、空 browse/search/fetch/graph fixtures。
- 验收：health 200；content_status=empty；search 200 且 `results=[]/no_match=true`；不存在文档稳定 404；不产生工程默认值。

### KB-104 Settings、secret 和 PathPolicy

- 依赖：KB-102。
- 输出：不可变 Settings、`.env.example`、路径策略。
- 实现：环境变量 > server env file > 非秘密默认值；read/admin/Qdrant 三 token 独立；禁止旧知识目录、父目录、符号链接逃逸。
- 验收：测试模式无 key 启动；生产缺 key fail fast；错误和日志不泄密。

## 3. G2：扫描、解析、切片和质量

### KB-201 Source catalog 与增量计划

- 依赖：KB-102、KB-104。
- 输出：SQLite catalog、source/document/release/build registry、manifest importer。
- 实现：WAL、外键、单写者；mtime 与 SHA-256 双重检测；新增/未变/修改/disabled/retired 差异计划。
- 验收：同一 manifest 重跑幂等；越界路径拒绝；只处理变化 source。

### KB-202 文件扫描与 domain 映射

- 依赖：KB-201。
- 输出：可配置扩展名、排除目录、min_chars、binary 检测、domain_path_map。
- 实现：Markdown/TXT/HTML/PDF/RDF/OWL/TTL 可路由；Java/Go/Python 默认只登记不切片；扫描件 PDF 标 warning；不扫描旧库。
- 验收：路径映射可覆盖 10 个默认 domain；未知扩展名进入 lint info。

### KB-203 Markdown/TXT/HTML parser

- 依赖：KB-202。
- 输出：统一 DocumentRecord、章节树、代码块、链接、原文和行号。
- 验收：H1-H6 树可重建；中英混排、代码块、表格、链接保持；原文 fetch 可回放。

### KB-204 PDF parser

- 依赖：KB-202。
- 输出：页码、文本、提取质量、扫描件状态。
- 实现：PyMuPDF；论文原文保留 provenance；V1 不 OCR，不把论文原文默认当工程参数真值。
- 验收：损坏/扫描 PDF 不阻塞整个 batch，记录可定位 warning。

### KB-205 RDF/OWL/TTL parser 与图谱白名单

- 依赖：KB-202、KB-003。
- 输出：label/comment/URI/显式关系、namespace 和 source_ref。
- 实现：rdflib 离线解析；DTD/XXE 禁用；`owl:imports` 只记 metadata，不联网；只读取 deployment manifest 白名单。
- 验收：RDF/XML/TTL/JSONL、重复 URI、悬空端点、三元组上限和 no-network 测试通过。

### KB-206 结构感知切片

- 依赖：KB-203、KB-204、KB-205。
- 输出：ChunkRecord、检索前缀、展示原文分离。
- 实现：章节/函数/配置块/材料实体优先；目标 400、重叠 50、最小 50；代码块、表格行、RDF 实体不从中间截断。
- 验收：chunk ID 稳定；metadata 完整率 100%；长章节和无标题文档有 golden tests。

### KB-207 Chunk lint 与 source lint

- 依赖：KB-206。
- 输出：断链、缺摘要、孤立、格式、编码、PDF 提取质量报告。
- 验收：severity 为 error/warning/info；blocking gate 与 warning 区分；报告可重放。

## 4. G3：Provider、索引和图关系

### KB-301 DashScope Embedding adapter

- 依赖：KB-104、KB-206。
- 输出：probe、批量 embedding、query embedding、cache、usage 指标。
- 实现：OpenAI-compatible endpoint；401/403 不重试；429/5xx/timeout 指数退避；维度由 probe 和配置共同校验。
- 验收：fake server 覆盖 200/401/429/500/timeout、乱序、数量错误、维度错误；日志脱敏。

### KB-302 Qdrant release adapter

- 依赖：KB-301。
- 输出：独立 Docker Qdrant collection、alias、upsert/query/delete/snapshot adapter。
- 实现：`roto_kb_<release>`；Cosine；payload filter；只写 staging；Qdrant REST 仅 loopback 6334。
- 验收：维度、collection、alias、snapshot 和网络中断测试通过；不接触旧 collection。

### KB-303 BM25 tokenizer/index

- 依赖：KB-206。
- 输出：rank-bm25、jieba/工程标识符 tokenizer、语料 hash。
- 验收：中文、英文、混合查询；`traction_bcs/vol_frac/filter_radius` 精确命中；损坏产物可检测；不反序列化不可信 pickle。

### KB-304 Relations compiler

- 依赖：KB-201、KB-205、KB-206。
- 输出：entity/relation/rule SQLite，depth=1 双向查询。
- 实现：QUDT/IOF/W3C/ROTO seed 规范化；extracted/inferred/ambiguous；材料数值不能由概念图推导；LLM 默认关闭。
- 验收：无任何图谱 API key 也可编译；未知 source_ref、悬空端点、越权 security scope fail。

### KB-305 RRF 与文档聚合

- 依赖：KB-302、KB-303、KB-304。
- 输出：vector/BM25/graph 候选、RRF、文档级结果和 related_hint。
- 实现：默认各路 top20、RRF k=60、最终 top6、最多 3 个去重 snippet；每个响应绑定 active release。
- 验收：公式 golden tests；单路故障和无命中可区分；排序稳定。

## 5. G4：HTTP API、鉴权和渐进式加载

### KB-401 查询用例服务

- 依赖：KB-305、KB-201。
- 输出：browse/search/fetch/graph application services。
- 实现：分页、domain/security_scope 过滤、章节 fetch、响应大小限制；只经 ports 访问存储。
- 验收：fake ports 可完成单元测试；不返回 SDK/SQLite 对象、内部绝对路径或 traceback。

### KB-402 FastAPI 路由与错误协议

- 依赖：KB-401、KB-102。
- 输出：health/browse/search/fetch/graph/help/lint/reload/build/release routes。
- 实现：read/admin scopes、常量时间比较、request ID、统一 `{error:{code,message,request_id}}`；管理限流。
- 验收：200/202/400/401/403/404/409/422/429/503/OpenAPI snapshot 全通过。

### KB-403 help/feedback/evolve API

- 依赖：KB-402、KB-013。
- 输出：`/help`、`/feedback`、5 个 `/evolve/*` 路由。
- 实现：help 机器可读；feedback 只记审计；suggestion apply/dismiss 需 admin；响应字段与任务报告一致。
- 验收：接口权限、重复 dismiss、source hash 重新评估和日志审计通过。

### KB-404 降级和客户端超时

- 依赖：KB-402、KB-305。
- 输出：degraded/no-match/error fixtures、RemoteRagClient 行为。
- 实现：Embedding 失败可退 BM25/graph；Qdrant 失败可退 BM25；BM25 失败可退 vector；全不可用返回 503；正常无命中返回 200。
- 验收：主线不会把降级或空结果转换为关键工程默认值。

## 6. G5：构建、评测、激活和自进化

### KB-501 Build job 与 lease

- 依赖：KB-402、G2、G3。
- 输出：incremental/full/fast refresh job、idempotency、checkpoint、heartbeat、cancel/resume。
- 验收：同 key 幂等；单 build；重启后 interrupted；失败不改 active；只清理已确认的 staging。

### KB-502 Lint/eval ready gate

- 依赖：KB-501。
- 输出：manifest/license/parser/index/eval/citation/isolation/disk 报告。
- 实现：hit@k、MRR、keyword hit、coverage、citation accuracy、p95；阈值版本化。
- 验收：任一 blocking gate 失败不得 ready/activate；warning 不静默。

### KB-503 Activation/rollback/recovery

- 依赖：KB-502、KB-302。
- 输出：alias switch、runtime bundle 原子交换、activation intent、启动 reconcile。
- 验收：任何故障最终回到最后完整 active；请求内 release 不漂移；rollback 不手工改 SQLite/Qdrant。

### KB-504 五步自进化 pipeline

- 依赖：KB-501、KB-503、KB-403。
- 输出：detect/identify/compile/verify/persist；merge/split suggestion。
- 实现：0.92 duplicate、0.88+0.60 merge、0.20 summary refresh、15000/3 split、0.70 summary verification；波纹传播最多 depth=1。
- 验收：LLM 不可用时 deterministic fast refresh；恢复后补执行 pending tasks；人工 apply 才生成新 release。

## 7. G6：443 部署与运维

### KB-601 服务器只读预检

- 依赖：KB-402、用户授权。
- 输出：Docker/nginx/systemd/python/disk/port/目录基线。
- 当前证据（2026-09-09）：旧 `kb-server.service` health 为 `ok`（498 docs/21684 chunks），应用监听 `127.0.0.1:8700`；nginx 现有 `/etc/nginx/conf.d/kb-server.conf` 仅监听 80 并代理旧根路径；443/8710/6334 未监听；Docker 未运行；根分区可用约 11 GB。AWS CLI 无凭据，ec2-user 无免密 sudo，因此 Security Group、UFW 和 nginx 变更留到 KB-603 的授权部署窗口。
- 验收：不读取旧知识内容；记录旧服务 health/count/process/port/path；目标端口为 443、8710、6334；目标目录不存在冲突；输出 AWS Security Group/UFW 当前规则和 nginx 监听归属。

### KB-602 Qdrant、systemd 和目录初始化

- 依赖：KB-601、KB-503。
- 输出：固定 digest Compose、`roto-kb.service`、`roto-kb-lint.service`、`roto-kb-lint.timer`、`/home/ec2-user/roto-kb`、`/data/roto-kb`、`/etc/roto-kb`、`/var/log/roto-kb`；timer 使用 `OnCalendar=weekly`，执行前校验目标路径。
- 验收：旧服务目录、unit、端口、collection 不被触碰；Qdrant 只 loopback。

### KB-603 nginx 443/TLS 与防火墙

- 依赖：KB-602、IP-SAN 证书或明确的临时自签名验收方式。
- 输出：`/etc/nginx/sites-available/roto-kb.conf`、对应 `sites-enabled` 链接、`server_name 54.172.101.190` 的 443 server block、80 保留旧服务的策略、TLS policy、firewall/security-group 规则、证书替换 hook。
- 验收：生产基址为 `https://54.172.101.190/roto-kb/`；TLS 1.2+、证书 SAN 包含 IP、HSTS、body/timeout/rate limits；80 不代理带 Authorization 的业务请求且旧根路径不变；`/roto-kb/health` 可探活；AWS/UFW 不暴露 8710/6334。自签名证书只能标记为临时验收，不得标记生产完成。
- 回滚：移除仅 ROTO-KB nginx include，旧根路径不变。

### KB-604 Backup/restore 与 isolation check

- 依赖：KB-503、KB-603。
- 输出：source/manifest/BM25/relations/registry/Qdrant snapshot 同 release 备份、恢复 runbook、隔离脚本。
- 验收：hash/维度/chunk/eval smoke 全通过；新服务 stop/reload/rollback 不改变旧服务；恢复演练可复现。

### KB-605 定时巡检与可观测性

- 依赖：KB-403、KB-604。
- 输出：`roto-kb-lint.timer` 每 7 天 lint/inspection、metrics、结构化日志和告警；记录 timer 最近成功/失败时间和证书续期状态。
- 验收：巡检不阻塞查询；记录 build/release/fallback/no-match/disk/certificate 状态；不记录 token、全文和完整 query。

## 8. G7：ROTO 主线联调

### KB-701 FakeRagService 与 RemoteRagClient

- 依赖：KB-001、KB-401、KB-004。
- 输出：主线 Fake/Remote client 和 consumer contract tests。
- 验收：相同 fixture 通过；ROTO 不依赖 Qdrant/BM25 内部对象。

### KB-702 故障与事件联调

- 依赖：KB-701、KB-503、KB-603。
- 输出：timeout/401/403/429/503/no-match/degraded/release change 报告。
- 验收：citation、index_release_id、fallback 进入主线事件；RAG 失败不阻塞 loop；命中不直接触发 solver。

## 9. G8：内容持续运营

### KB-801 新批次登记

- 依赖：G2。
- 输出：source batch、manifest、checksum、license/attribution、eval case。
- 验收：每批至少一个检索 case；不提交生成索引；不确定来源进入 quarantined。

### KB-802 更新、停用和退役

- 依赖：KB-801、G5。
- 输出：source hash/version 变化、disabled/replacement/audit、regression report。
- 验收：历史 release 不被静默修改；disabled 不召回；alias 可回旧 release。

### KB-803 Release 运营清单

- 依赖：KB-802、KB-502、KB-503、KB-604。
- 输出：build/eval/approve/activate/snapshot/smoke 证据包。
- 验收：active 可追溯至唯一代码 commit、内容 commit、pipeline、模型、维度、评测和审批记录。

## 10. 交付顺序

推荐执行顺序：

```text
KB-000..004
  -> KB-101..104
  -> KB-201..207
  -> KB-301..305
  -> KB-401..404
  -> KB-501..504
  -> KB-601..605
  -> KB-701..702
  -> KB-801..803
```

可并行：KB-203/204、KB-303/304、KB-603/605、KB-701。不可并行：契约冻结前不得实现跨仓联调；服务器 443 变更前不得配置生产 secret；active release 评测前不得开放公网写接口。公网基址固定为 `https://54.172.101.190/roto-kb/`，不依赖域名。
