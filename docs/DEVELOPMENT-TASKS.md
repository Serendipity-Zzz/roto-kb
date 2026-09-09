# ROTO-KB SDD 驱动开发子任务

| 属性 | 内容 |
|---|---|
| 文档版本 | v1.1 |
| 日期 | 2026-09-09 |
| 对齐 | `docs/PRD.md` v1.4、`docs/SDD.md` v1.2 |
| 当前状态 | 粗粒度实施索引；详细 RAG 任务以 [`docs/RAG-DETAILED-TASKS.md`](./RAG-DETAILED-TASKS.md) 为准 |

> 本文保留早期 KB-001..703 的实施索引；新增的 G0-G8 任务、端口/证书/隔离验收和回滚细节以 `RAG-DETAILED-TASKS.md`、`PRD.md` 和 `SDD.md` 为真源。

## 0. 使用方式

每个任务必须独立产生可审查交付物。任务状态只允许 `todo -> doing -> review -> accepted`，失败退回 `doing`；不能用“代码已写”代替验收。任务开始前固定 SDD 引用和输入 fixture，完成时附测试命令、关键输出、已知限制和回滚方式。

任务完成定义：代码、测试、类型/格式检查、配置示例、必要文档和验收证据同时存在；不提交 secret、索引生成物或模型权重。

## 1. 总体依赖与阶段门

```text
G0 文档基线（当前）
  -> G1 基础与空库：KB-001 -> KB-002 -> KB-003
  -> G2 摄取：KB-101 -> KB-102 -> KB-103
  -> G3 索引：KB-201 -> KB-202/203/204
  -> G4 检索/API：KB-301 -> KB-302 -> KB-303
  -> G5 Release：KB-401 -> KB-402 -> KB-403
  -> G6 运维：KB-501/502 -> KB-503
  -> G7 联调：KB-601 -> KB-602
  -> 持续内容：KB-701 -> KB-702 -> KB-703（每批循环）
```

允许并行：KB-202/203/204 在 KB-201 接口稳定后并行；KB-501/502 可在 API 契约稳定后并行；ROTO 主线可基于 KB-601 fixture 提前开发 Fake client。任何生产部署任务必须等待用户后续明确启动。

## 2. G1：基础与空库契约

### KB-001 项目脚手架、依赖和质量门

| 项目 | 内容 |
|---|---|
| 依赖 | G0 文档 accepted |
| 修改范围 | `pyproject.toml`、`src/roto_kb/`、`tests/`、Ruff/mypy/pytest 配置 |
| 输出 | 可安装 Python 包、CLI/ASGI 空入口、锁定依赖、基础 CI |
| 实现 | Python 3.12；src layout；开发/测试/部署 extras；所有外部 SDK 放 adapter 层 |
| 测试 | 干净虚拟环境安装；import；CLI help；Ruff、mypy、pytest 空基线 |
| 验收 | 本地和 CI 使用同一命令通过；无业务实现、无 secret |
| 回滚 | 删除脚手架提交即可，不涉及数据迁移 |

### KB-002 Domain schema、ports 与 `rel_empty`

| 项目 | 内容 |
|---|---|
| 依赖 | KB-001 |
| 修改范围 | `domain/models.py`、`domain/ports.py`、`domain/release.py`、JSON Schema fixtures |
| 输出 | Source/Document/Chunk/Release/EvidencePackage v1 模型；provider/index/catalog ports |
| 实现 | 严格 Pydantic schema；额外字段策略显式；稳定 ID/hash；release 状态机；`rel_empty` |
| 测试 | JSON round-trip、非法状态转换、未知字段、空结果、稳定 ID golden tests |
| 验收 | Schema 与 ROTO T02 EvidencePackage fixture 一致；domain 不导入外部基础设施包 |
| 回滚 | schema 变更必须提升 schema version，不覆盖已发布 fixture |

### KB-003 Settings、secret 和路径策略

| 项目 | 内容 |
|---|---|
| 依赖 | KB-001、KB-002 |
| 修改范围 | `config.py`、`.env.example`、`ops/path_policy.py` |
| 输出 | 不可变 Settings、启动校验、允许/拒绝路径策略 |
| 实现 | DashScope/Qdrant/read/admin 配置；环境优先级；secret 类型；token 不同；路径 realpath guard |
| 测试 | 缺配置、HTTP endpoint、维度空值、token 重复、路径穿越、旧知识库路径拒绝 |
| 验收 | 测试/空库模式可无真实 key 启动；生产模式缺 secret fail fast；异常不泄密 |
| 回滚 | 仅配置层，无外部状态 |

G1 出口：空库应用可用 fake adapter 启动，`rel_empty` 契约测试通过，尚不要求 Qdrant 或 DashScope。

## 3. G2：知识摄取

### KB-101 Source catalog 与增量计划

| 项目 | 内容 |
|---|---|
| 依赖 | KB-002、KB-003 |
| 修改范围 | `ingestion/catalog.py`、`indexes/catalog_sqlite.py`、迁移脚本 |
| 输出 | source/document/release/build registry；manifest importer；增量差异计划 |
| 实现 | SQLite WAL/外键；source ID 稳定；采集状态和 ingestion 状态分离；单写者事务 |
| 测试 | 新增、未变、修改、disabled、retired、mtime 变化但 hash 未变、并发写冲突 |
| 验收 | 同一 manifest 重跑幂等；不读取允许根目录之外的文件 |
| 回滚 | SQLite migration 有向前恢复说明；不做 destructive downgrade |

### KB-102 多格式 parser

| 项目 | 内容 |
|---|---|
| 依赖 | KB-101 |
| 修改范围 | `ingestion/parsers/`、parser fixtures |
| 输出 | Markdown/Text/HTML/PDF/RDF parser 和统一 DocumentRecord |
| 实现 | Markdown AST；HTML 主体净化；PDF 页码；RDF label/comment/URI；V1 扫描 PDF 标记不 OCR |
| 测试 | 中英混排、代码块、表格、损坏 PDF、空 HTML、非法 RDF、编码替换率 |
| 验收 | 当前 seed 每类至少一个 fixture 可重复解析；原始 source 零修改 |
| 回滚 | parser version 变化提升 pipeline version |

### KB-103 结构感知 chunker 与 lint

| 项目 | 内容 |
|---|---|
| 依赖 | KB-102 |
| 修改范围 | `ingestion/chunkers/`、`ingestion/lint.py` |
| 输出 | ChunkRecord、上下文前缀、chunk lint report |
| 实现 | 400 target/50 overlap/50 min；章节/代码块/表格/RDF 实体优先；展示原文与检索文本分离 |
| 测试 | 边界长度、超长章节、无标题文档、表格/代码不被破坏、chunk ID 稳定性 |
| 验收 | metadata 完整率 100%；相同输入和 pipeline version 产生相同 chunks |
| 回滚 | 保留旧 pipeline 的 golden fixtures，变更触发全量 staging |

G2 出口：不调用模型即可从 seed source 生成可追踪 document/chunk 清单和 lint 报告。

## 4. G3：Provider 与索引

### KB-201 DashScope Embedding adapter

| 项目 | 内容 |
|---|---|
| 依赖 | KB-003、KB-103；用户确认地域/模型/维度后才做真实 smoke test |
| 修改范围 | `providers/dashscope_embedding.py`、fake HTTP server、cache |
| 输出 | `probe/embed_documents/embed_query`；批量、重试、熔断、usage 指标 |
| 实现 | OpenAI-compatible endpoint；`DASHSCOPE_API_KEY`；401/403 不重试；429/5xx 指数退避 |
| 测试 | fake 200/401/429/500/timeout、乱序/数量错误、维度错误、cache hit、日志脱敏 |
| 验收 | provider 只返回 domain DTO；真实 smoke test 有调用预算且不写 key |
| 回滚 | adapter 可切 fake；禁止生产自动回退其他供应商 |

### KB-202 Qdrant release adapter

| 项目 | 内容 |
|---|---|
| 依赖 | KB-201 port 稳定 |
| 修改范围 | `indexes/qdrant.py`、test compose |
| 输出 | collection create/upsert/query/delete staging/snapshot/alias adapter |
| 实现 | physical collection per release；Cosine；payload filter；维度三方校验；独立 API key |
| 测试 | test container；批量 upsert 幂等；filter；alias switch；snapshot；网络中断 |
| 验收 | 只写 staging collection；绝不接触非 `roto_kb_` 前缀 collection |
| 回滚 | 删除失败 staging；active/previous 由 release service 保护 |

### KB-203 BM25 与工程 tokenizer

| 项目 | 内容 |
|---|---|
| 依赖 | KB-103 |
| 修改范围 | `indexes/bm25.py`、术语词典、canonical corpus |
| 输出 | build/load/search adapter；可校验的语料 hash |
| 实现 | rank-bm25 + jieba；标识符整体词元；不反序列化不可信 pickle |
| 测试 | `traction_bcs/vol_frac/filter_radius` 精确命中；中文、英文、混合查询；损坏产物 |
| 验收 | 同语料结果确定；security scope 在候选阶段过滤 |
| 回滚 | 从 release chunks 重建，不把 BM25 当真源 |

### KB-204 关系索引

| 项目 | 内容 |
|---|---|
| 依赖 | KB-101、KB-103 |
| 修改范围 | `indexes/relations.py`、SQLite schema |
| 输出 | RDF/JSONL 离线 compiler；entity/relation/rule store；双向 depth=1 graph adapter |
| 实现 | 只读 deployment manifest 白名单；禁网络 `owl:imports`；QUDT/IOF/W3C/ROTO seed 规范化；DashScope LLM 辅助默认关闭 |
| 测试 | RDF/XML/TTL/JSONL、XXE/DTD、重复 URI、悬空端点、未知 source_ref、三元组上限、release/security filter |
| 验收 | 不配置任何图谱 API key 也能完成编译；inferred/ambiguous 只作提示；材料数值不能由概念图产生 |
| 回滚 | relations 可由 source/chunk 重建 |

G3 出口：fixture release 可同时构建向量、BM25、relations，三个索引均有独立故障测试。

## 5. G4：检索与 API

### KB-301 RRF、聚合与降级策略

| 项目 | 内容 |
|---|---|
| 依赖 | KB-202、KB-203、KB-204 |
| 修改范围 | `application/retrieve.py`、`domain/scoring.py` |
| 输出 | chunk RRF、document aggregate、related hint、degradation reasons |
| 实现 | vector/BM25 top20；RRF k=60；final top6；最多 3 个去重 snippet；固定 runtime snapshot |
| 测试 | 公式 golden tests、单路/双路故障、无匹配、低分、权限过滤、排序稳定性 |
| 验收 | 正常无匹配与系统不可用可区分；不生成工程默认值 |
| 回滚 | 算法变更提升 pipeline/retrieval version 并跑评测对比 |

### KB-302 Browse/Search/Fetch/Graph application services

| 项目 | 内容 |
|---|---|
| 依赖 | KB-301、KB-101 |
| 修改范围 | `application/queries/` |
| 输出 | 四类纯用例服务、分页和大小限制 |
| 实现 | 只经 ports 访问数据；fetch 章节定位；每响应绑定 active release ID |
| 测试 | rel_empty、分页、过滤、404、章节不存在、超限、激活时并发查询 |
| 验收 | 用 fake ports 完成全部单元测试；响应无 SDK/SQLite 对象 |
| 回滚 | 保持 v1 schema 兼容，破坏性变化发布 v2 路由 |

### KB-303 FastAPI、鉴权与错误协议

| 项目 | 内容 |
|---|---|
| 依赖 | KB-002、KB-302 |
| 修改范围 | `api/`、OpenAPI fixture |
| 输出 | health/browse/search/fetch/graph/reload/build/release/lint routes |
| 实现 | read/admin scope；常量时间比较；request ID；统一错误；管理限流；202 build job |
| 测试 | OpenAPI snapshot；200/202/400/401/403/404/409/422/503；secret/header 脱敏 |
| 验收 | rel_empty 下 health/browse/search/fetch 契约通过；公网响应无内部路径/traceback |
| 回滚 | OpenAPI fixture 版本化；路由兼容策略记录 |

G4 出口：本地服务可用 fake/fixture 索引完成全套 HTTP contract，不代表可生产上线。

## 6. G5：Release 管理

### KB-401 可恢复 staging builder

| 项目 | 内容 |
|---|---|
| 依赖 | G2、G3、KB-303 |
| 修改范围 | `release/builder.py`、build registry、CLI/API |
| 输出 | 异步增量/full build job、phase checkpoint、lease/heartbeat/resume |
| 实现 | 单 build lease；idempotency key；磁盘门；不修改 active；失败留下可诊断报告 |
| 测试 | 中途崩溃/恢复、重复请求、取消、磁盘不足、DashScope 失败、Qdrant 部分写入 |
| 验收 | 失败 build 不改变 active 查询结果；重试不重复计费已缓存 chunk |
| 回滚 | 清理仅针对解析后确认的失败 staging 路径/collection |

### KB-402 Lint、离线评测与 ready gate

| 项目 | 内容 |
|---|---|
| 依赖 | KB-401 |
| 修改范围 | `release/validator.py`、`evals/`、报告 schema |
| 输出 | manifest/license/parser/index/eval/citation/isolation gate 报告 |
| 实现 | hit@k、MRR、keyword hit、coverage、citation accuracy、p95；阈值版本化 |
| 测试 | 每个 gate 独立失败；报告可重放；同 release 不同评测版本不可混淆 |
| 验收 | 只有所有 blocking gate 通过才能 `ready`；warning 不静默 |
| 回滚 | rejected/failed 保留报告，不激活 |

### KB-403 激活、回滚与启动恢复

| 项目 | 内容 |
|---|---|
| 依赖 | KB-402 |
| 修改范围 | `release/activator.py`、runtime bundle、recovery |
| 输出 | alias switch、内存 bundle 原子交换、activation intent、rollback |
| 实现 | 写锁临界区；补偿事务；active/previous 保护；smoke query；启动 reconcile |
| 测试 | 每一步故障注入、进程崩溃、alias/registry 不一致、并发查询、重复激活 |
| 验收 | 任何失败最终回到可查询的最后完整 release；请求内 release 不漂移 |
| 回滚 | 显式 rollback API；不靠手工改 SQLite/Qdrant |

G5 出口：种子内容可形成可评测 release，并能在故障注入下激活和回滚。

## 7. G6：部署与运维

### KB-501 本地 Compose 与生产服务文件

| 项目 | 内容 |
|---|---|
| 依赖 | KB-303、KB-403；执行部署需用户另行启动 |
| 修改范围 | `infra/compose.yaml`、systemd、nginx、scripts |
| 输出 | 固定版本/digest 的 Qdrant；`roto-kb.service`；`/roto-kb/` nginx 配置 |
| 实现 | `127.0.0.1:6334:6333`；`127.0.0.1:8710`；独立目录/user/secret；部署不 auto-reload |
| 测试 | 配置静态检查、本地 compose health、systemd/nginx syntax dry run |
| 验收 | 所有名称/端口/路径与旧服务不同；生产无 `latest` |
| 回滚 | 恢复上一代码版本并 restart；索引 release 不随代码回滚删除 |

### KB-502 监控、日志、备份恢复

| 项目 | 内容 |
|---|---|
| 依赖 | KB-401、KB-403 |
| 修改范围 | `ops/metrics.py`、backup/restore scripts、runbook |
| 输出 | 指标、结构化日志、Qdrant snapshot、同 release 备份包、恢复演练 |
| 实现 | 日志脱敏；7 daily/4 weekly；hash/维度/eval restore gate |
| 测试 | secret 扫描；损坏 snapshot；缺 BM25；错误维度；低磁盘；恢复 smoke |
| 验收 | 仅 Qdrant snapshot 不能被误判为完整备份；演练报告可审查 |
| 回滚 | 备份脚本不清理 active；清理任务单独审批 |

### KB-503 远端隔离验收

| 项目 | 内容 |
|---|---|
| 依赖 | KB-501、KB-502；需用户明确允许进入部署阶段 |
| 修改范围 | `scripts/isolation-check.*`、验收报告 |
| 输出 | 部署前/后旧服务 health、count、process、port、path 对比证据 |
| 实现 | 只读采集旧服务基线；新服务 start/stop/reload/rollback 隔离测试 |
| 测试 | 脚本对 forbidden path fail closed；模拟端口/目录冲突 |
| 验收 | 旧服务所有基线不变；Qdrant 不公网暴露；新服务独立停止/恢复 |
| 回滚 | 停止并移除仅 ROTO-KB unit/container；保留数据供分析，不碰旧服务 |

G6 出口：只在实际部署和隔离证据完成后成立；当前明确暂停在此阶段之前。

## 8. G7：ROTO 主线联调

### KB-601 发布客户端契约包

| 项目 | 内容 |
|---|---|
| 依赖 | KB-002、KB-303 |
| 修改范围 | `contracts/`、OpenAPI/JSON Schema、response fixtures |
| 输出 | success/empty/degraded/error fixtures；版本兼容说明 |
| 实现 | 不共享 Python 内部类型；以 JSON Schema/OpenAPI 为跨仓真源 |
| 测试 | consumer contract 可在 ROTO 仓库离线运行 |
| 验收 | ROTO FakeRagService 和 RemoteRagClient 可用相同 fixture |
| 回滚 | 保留旧 fixture；breaking change 新版本并行发布 |

### KB-602 跨仓契约和故障联调

| 项目 | 内容 |
|---|---|
| 依赖 | KB-601、G5；主线对应任务可用 |
| 修改范围 | 两仓 contract test 配置和联调报告，不改主线业务边界 |
| 输出 | timeout/401/403/503/no-match/degraded/release change 联调证据 |
| 实现 | 验证 citation/release 进入事件；RAG 不直接触发 solver；失败不阻塞 loop |
| 测试 | consumer/provider contract + 端到端 smoke |
| 验收 | 主线行为符合 PRD 9；双方版本矩阵记录 |
| 回滚 | 主线切 Fake/Local adapter；远端 active release 不受影响 |

## 9. 持续知识内容任务

### KB-701 新知识批次登记

| 项目 | 内容 |
|---|---|
| 依赖 | G2；可在 G5 前准备但不可上线 |
| 修改范围 | `knowledge/`、manifest、checksums、eval cases |
| 输出 | 可审计的 source batch |
| 实现 | 来源、revision、license、attribution、domain、scope、hash；图谱使用 deployment allowlist；不确定则 quarantined |
| 测试 | manifest/schema/checksum/license、RDF no-network-import、JSONL graph integrity CI；secret/大文件扫描 |
| 验收 | 每批至少一个代表性检索 case；不提交生成索引 |
| 回滚 | revert 内容 PR；已上线则走 KB-702 disabled + 新 release |

### KB-702 更新、停用与退役

| 项目 | 内容 |
|---|---|
| 依赖 | KB-701、G5 |
| 修改范围 | manifest 状态、replacement、审计记录、eval regression |
| 输出 | 增量 staging release，不修改历史 release |
| 实现 | source ID 稳定；hash/version 更新；disabled 先下线后清理；删除非常规 |
| 测试 | 旧查询回归、新版本命中、disabled 不召回、rollback 恢复旧 release |
| 验收 | 变更影响可解释；无 silent deletion；active 激活前人工审核 |
| 回滚 | alias 回上一 release；manifest 修复走新提交 |

### KB-703 每批 release 运营清单

| 项目 | 内容 |
|---|---|
| 依赖 | KB-701 或 KB-702、KB-402、KB-403 |
| 修改范围 | release report、运营记录 |
| 输出 | build/eval/approve/activate/snapshot/smoke 全链证据 |
| 实现 | 记录代码 commit、content commit、pipeline、模型/维度、成本、指标差异和审批人 |
| 测试 | 固定 smoke queries；引用抽查；上一 release rollback drill（定期） |
| 验收 | active release 可追溯到唯一内容和代码版本；备份完成后才关闭任务 |
| 回滚 | 运行 KB-403 rollback，并记录原因和后续修复任务 |

## 10. 当前需要用户补充的决策

以下事项分为“现在必须完成”和“可以暂缓”。仓库创建已完成，不再作为前置项。

### 10.1 现在必须完成

1. **跨仓 EvidencePackage v1 对齐**：确认 `source` 与 `source_uri/source_hash/document_version/security_scope` 的最终字段，以及 `degradation_reason` 单值还是 `degradation_reasons[]`；补齐 `no_match`。先在 `roto-kb/contracts/` 固化 JSON Schema、OpenAPI、success/empty/degraded/error fixtures，再让 ROTO 主线离线消费。
2. **项目契约交付**：把 ROTO PRD/SDD/T02 和实现所需 Schema 以 commit/SHA-256 快照或可访问版本化包交付给 ROTO-KB。`E:/Project/ROTO/...` 只能用于本机开发，不能成为 Linux 服务器的 source path。
3. **仓库质量门**：保护 public 仓库 `main`，启用 CI 必过、secret scanning，并确认密钥、模型权重、生成索引不入库。

### 10.2 首次真实索引前完成

4. 阿里云 API key 所属地域，以确定 DashScope compatible endpoint。
5. 最终 Embedding 模型和维度；默认候选为 `text-embedding-v4`，实际能力在首次构建前 probe。
6. 是否在 V1 开启 DashScope LLM 做摘要/关系抽取；默认关闭，先用确定性 metadata 和关系。

### 10.3 服务器部署前完成

7. 允许对 `54.172.101.190` 做 Docker/nginx/systemd/目录变更，并完成旧服务只读基线与新服务隔离验收。
8. 生成并安装 read/admin/Qdrant 三套不同 secret；确认域名/HTTPS 方案，或明确仅限临时 HTTP 验收。
9. 修复部署用 SSH 私钥 ACL；Windows OpenSSH 当前会因 `ladder.pem` 对 Authenticated Users 可读而拒绝该密钥。

### 10.4 可以后补

10. CORA、PropNet、MatOnto 的文件导入和材料事实批次；三者已在 manifest 保留为 reference-only/link-and-map-only，不阻塞 G1-G4。
11. 何时从 G0 进入 G1 实现，以及何时允许执行 G6 的服务器软件变更。

## 11. 详细设计对照补充任务

参考设计文档包含 67 个 T1.1-T14.3 任务；本仓库原任务表将它们合并为较粗粒度 KB 任务。以下任务把尚未明确的技术细节拆开，作为实现时的执行清单，不改变现有阶段门。

### D-004 跨仓契约冻结

依赖：G0。输入：ROTO 主线 `contracts.py`、T02、`docs/PRD.md` 与 `docs/SDD.md`。输出：`contracts/evidence-package.v1.schema.json`、`contracts/openapi.yaml`、四类 response fixture、兼容性说明。验收：ROTO 与 ROTO-KB 均能离线校验；字段、错误码、`no_match`、降级列表和 citation 语义一致。回滚：新版本使用 `v2`，不覆盖已发布 v1。

### D-005 内容目录与 parser 路由

依赖：KB-001、KB-003。输入：source manifest、允许根目录、domain 映射。输出：scanner、parser registry、文件清单。验收：Markdown/TXT/HTML/PDF/RDF/OWL/TTL 路由可配置；代码文件只登记不默认切片；扫描拒绝符号链接逃逸、设备文件、旧知识库目录和父目录；PDF 扫描件标记 warning，V1 不 OCR。回滚：恢复上一 pipeline version。

### D-006 结构切片与展示/检索分离

依赖：KB-005。输出：稳定 `DocumentRecord`/`ChunkRecord`、章节路径、源行号、检索上下文前缀。验收：目标 300-500 token、重叠 50、最小 50；代码块/表格/RDF 实体不从中间截断；fetch 展示内容不包含隐藏前缀；相同输入和 pipeline version 产生相同 chunk ID。

### D-007 离线图谱编译器

依赖：KB-005、deployment manifest。输出：实体、关系、规则 SQLite/JSON 产物。验收：只读取白名单；禁网络 `owl:imports`、DTD/XXE；检查 namespace、重复 URI、悬空端点、source_refs、文件大小和三元组上限；CORA/PropNet/MatOnto 默认不进入 active。

### D-008 Embedding provider 与能力探针

依赖：KB-003、KB-006。输出：DashScope probe/embed adapter、cache、重试和熔断。验收：API key 缺失时 fake/empty 模式可启动；真实构建前 probe 记录地域、模型和维度；401/403 不重试，429/5xx/timeout 有上限退避；日志不含原文和密钥。

### D-009 Qdrant release adapter

依赖：KB-008。输出：独立 Server collection/alias/snapshot adapter。验收：只操作 `roto_kb_` 前缀；向量维度、距离和 payload 三方一致；staging 写入不影响 active；alias 切换可回滚；不使用参考文档中的嵌入式 Qdrant。

### D-010 BM25、关系和 RRF

依赖：KB-006、KB-007、KB-009。输出：jieba/标识符 tokenizer、BM25、depth=1 relations、RRF 聚合。验收：中英混合和工程标识符精确命中；RRF `k=60` 可配置；权限过滤发生在每一路候选阶段；单路故障返回可识别降级原因。

### D-011 API 与渐进式加载

依赖：KB-004、KB-010。输出：`health/browse/search/fetch/graph/help/lint`。验收：空库 `rel_empty`、分页、章节 fetch、大小限制、404、统一错误结构和 read/admin scope 全通过；`/help` 与 OpenAPI 一致。

### D-012 Release builder 与任务恢复

依赖：KB-011。输出：incremental/full/`evolve=false` 三种 build，lease、checkpoint、resume、cancel。验收：同 idempotency key 幂等；单 build 并发；中途崩溃标记 interrupted；失败不改变 active；重试不重复 Embedding 计费。

### D-013 自进化与反馈接口

依赖：KB-012。输出：`/evolve/status`、`/evolve/suggestions`、`/evolve/apply`、`/evolve/dismiss`、`/evolve/log`、`/feedback`。验收：阈值和报告可追溯；合并/分裂只产生人工建议；dismiss 按 source hash 抑制重复；feedback 在下次增量 build 优先处理。

### D-014 443 TLS 与公网边界

依赖：KB-011、用户提供 IP-SAN 证书或临时自签名验收方式。输出：nginx 443 配置、80 旧服务保留策略、firewall/security-group 变更说明。验收：仅 443 对公网提供 ROTO-KB；8710/6334 loopback；TLS 1.2+、证书 SAN 包含 `54.172.101.190`、HSTS、限流、请求体/超时限制；80 不代理 ROTO-KB 业务 Authorization；管理路由仍需 admin token。

### D-015 部署、隔离和恢复演练

依赖：KB-014、KB-012。输出：systemd、Docker compose、备份恢复、isolation-check、runbook。验收：新旧服务独立；旧服务 health/count/process/port/path 不变；active/previous release 可恢复；snapshot、BM25、relations、manifest 同 release 校验通过。

### D-016 主线联调

依赖：KB-004、KB-011、KB-015。输出：FakeRagService、RemoteRagClient、双仓 contract/e2e 报告。验收：timeout/401/403/429/503/no-match/degraded、citation 和 release ID 全覆盖；RAG 失败不阻塞 loop，不直接触发 solver。

## 12. 任务交接模板

```markdown
Task: KB-xxx
SDD refs: x.x, y.y
Status: review
Changed files:
Tests and outputs:
Contract/migration impact:
Security/isolation checks:
Rollback procedure:
Known limitations:
Next unlocked tasks:
```
