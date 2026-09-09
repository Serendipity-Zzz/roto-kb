# SDD：ROTO-KB 独立工程知识服务

| 属性 | 内容 |
|---|---|
| 文档版本 | SDD v1.2 |
| 日期 | 2026-09-09 |
| 状态 | 开发设计基线；契约对齐和部署前置待完成 |
| 对齐 PRD | `docs/PRD.md` v1.4 |
| 仓库 | `https://github.com/Serendipity-Zzz/roto-kb` |
| 主线契约 | ROTO `EvidencePackage v1` / `RagService` |
| 模型供应商 | 阿里云百炼 Model Studio（DashScope） |

## 0. 文档定位与来源边界

本文档把 PRD 转换为可编码、可测试、可验收的软件设计。PRD 决定产品范围和验收目标，SDD 决定组件、接口、状态、数据和故障行为，[开发子任务](./DEVELOPMENT-TASKS.md) 决定实施顺序。发生冲突时优先级为：用户最新决策 > PRD > SDD > 开发子任务。

参考的既有知识库设计文档只用于吸收 `browse/search/fetch/graph`、混合检索和增量编译思路；其中针对第三方 `kb-server` 的路径、端口、嵌入式 Qdrant、无鉴权假设和执行指令不适用于 ROTO-KB。ROTO-KB 不读取、不复制、不修改服务器现有第三方知识内容。

## 1. 架构驱动因素

### 1.1 功能驱动

1. 空知识库也能启动并返回稳定契约。
2. 后续可持续补充、更新、停用知识源，不重新部署应用。
3. 文档可被解析、切片、向量化、关键词索引和关系索引。
4. 在线提供 `browse/search/fetch/graph`，返回可追溯证据。
5. 索引通过 staging、评测、激活、回滚发布，不原地破坏 active release。
6. ROTO 主线只通过 HTTP/SDK 契约集成，不访问索引内部。

### 1.2 非功能驱动

| 维度 | V1 目标 |
|---|---|
| 隔离 | 与 `kb-server.service`、8700、旧目录和旧索引零共享 |
| 可用性 | Qdrant 或 BM25 单路故障时可降级；active release 不被构建任务修改 |
| 一致性 | 每条 evidence 可定位到 source hash、document version、chunk 和 release |
| 性能 | 50,000 chunks 内，1-10 QPS，`search` p95 < 1.5s，不含生成式 LLM |
| 安全 | 应用和 Qdrant 只监听 loopback；read/admin/Qdrant 三类凭据分离 |
| 可恢复 | active/previous release、source、BM25/relations 和 Qdrant snapshot 可配套恢复 |
| 可测试 | 外部 API、Qdrant、文件系统均有 adapter，可用 fake 完成单元和契约测试 |

## 2. PRD 追踪矩阵

| PRD 能力 | SDD 章节 | 开发任务 |
|---|---|---|
| 独立仓库与服务边界 | 3、4、15 | KB-001、KB-503 |
| 空库启动和稳定契约 | 6、11、12 | KB-002、KB-303 |
| source catalog 和增量检测 | 6、7、13 | KB-101、KB-701、KB-702 |
| 解析与切片 | 7 | KB-102、KB-103 |
| DashScope Embedding | 5、8 | KB-201 |
| Qdrant/BM25/relations | 9 | KB-202、KB-203、KB-204 |
| 混合检索和 EvidencePackage | 10、11 | KB-301、KB-302、KB-303 |
| staging/评测/激活/回滚 | 12 | KB-401、KB-402、KB-403 |
| 安全、监控、备份、部署 | 14-17 | KB-501、KB-502、KB-503 |
| ROTO 主线联调 | 11、18 | KB-601、KB-602 |
| 后续补充知识内容 | 13 | KB-701、KB-702、KB-703 |
| 外部图谱离线种子 | 7.5、9.3 | KB-204、KB-701 |

## 3. 系统架构

### 3.1 上下文

```text
ROTO Loop Engineering
  FakeRagService / RemoteRagClient
                  |
                  | EvidencePackage v1 over HTTP
                  v
nginx /roto-kb/ -> FastAPI 127.0.0.1:8710
                      |
     +----------------+------------------+
     |                |                  |
Qdrant Server     BM25 runtime      SQLite/relations
127.0.0.1:6334   release files     catalog + releases
     |
DashScope Embedding API is called only by build/query adapters
```

### 3.2 运行组件

| 组件 | 责任 | 持久化 | 禁止承担 |
|---|---|---|---|
| `api` | HTTP、鉴权、schema、错误映射、request ID | 无 | 直接拼装索引内部对象 |
| `application` | browse/search/fetch/release 用例编排 | 无 | 依赖具体 SDK 全局实例 |
| `domain` | 数据模型、状态机、规则、ports | 无 | 网络和磁盘 I/O |
| `ingestion` | 扫描、解析、切片、增量计划 | staging | 修改原始 source |
| `providers` | DashScope Embedding/LLM adapter | embedding cache | 决定 release 状态 |
| `indexes` | Qdrant、BM25、relations adapter | 各自存储 | 绕过 security filter |
| `release` | build、validate、activate、rollback、recovery | release manifest | 在线原地重建 active |
| `ops` | health、metrics、backup、部署脚本 | 日志/snapshot | 接触旧知识库路径 |

### 3.3 依赖方向

`api -> application -> domain`；`ingestion/providers/indexes/release` 实现 domain ports。domain 不导入 FastAPI、Qdrant、DashScope SDK 或文件系统模块。测试可用 fake adapter 替代所有外部依赖。

## 4. 目标代码结构与技术栈

```text
roto-kb/
  pyproject.toml
  .env.example
  src/roto_kb/
    api/                  # FastAPI routes、dependencies、errors
    application/          # query/build/release use cases
    domain/               # Pydantic models、enums、ports、rules
    ingestion/            # scanner、parsers、chunkers、planner
    providers/            # DashScope adapters
    indexes/              # qdrant、bm25、relations
    release/              # manifest、builder、activator、recovery
    ops/                   # health、metrics、backup guards
    config.py
    main.py
  tests/
    unit/
    contract/
    integration/
    e2e/
    fixtures/
  evals/
    queries.yaml
    expected/
  infra/
    compose.yaml
    nginx/
    systemd/
  scripts/
  docs/
  knowledge/
```

基线技术：Python 3.12、FastAPI、Uvicorn、Pydantic v2/pydantic-settings、httpx 或 OpenAI Python SDK、qdrant-client、rank-bm25、jieba、markdown-it-py、BeautifulSoup、PyMuPDF、rdflib、SQLite、pytest、Ruff、mypy。版本在实现任务 KB-001 中锁定，不在 SDD 写浮动最低版本。

## 5. 配置设计

### 5.1 配置优先级

`环境变量 > /etc/roto-kb/roto-kb.env > 代码非秘密默认值`。生产不读取仓库 `.env`。所有配置在启动时解析成不可变 `Settings`，缺少必要配置时 fail fast。

### 5.2 DashScope 配置

```yaml
model_api:
  provider: dashscope
  base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
  api_key_env: DASHSCOPE_API_KEY
  embedding:
    model: text-embedding-v4
    dimension: null       # 首次索引前确认；不得由代码猜测
    batch_size: 16
    timeout_seconds: 30
    max_retries: 4
  llm:
    enabled: false
    model: null
    timeout_seconds: 60
    max_retries: 2
```

约束：

- `provider` 只允许 `dashscope` 或测试用 `fake`，生产禁止无提示回退其他供应商。
- `base_url` 必须是 HTTPS；地域 endpoint 必须与 API key 所属地域一致。
- `DASHSCOPE_API_KEY` 不得出现在 YAML、日志、trace、异常或健康响应。
- `dimension` 在 collection 创建前必须非空，并与 capability probe 实际长度一致。
- LLM 辅助能力默认关闭；V1 的核心检索不能依赖 LLM 才能工作。

### 5.3 索引与 release 配置

```yaml
qdrant:
  url: http://127.0.0.1:6334
  api_key_env: QDRANT_API_KEY
  collection_prefix: roto_kb
  active_alias: roto_kb_active
  distance: cosine
retrieval:
  vector_top_k: 20
  bm25_top_k: 20
  final_top_k: 6
  rrf_k: 60
  relation_depth: 1
chunking:
  target_tokens: 400
  overlap_tokens: 50
  min_tokens: 50
release:
  retention: 2
  min_free_disk_gb: 5
```

配置校验同时检查：路径位于允许根目录、端口不冲突、token 不相同、top-k 合理、chunk overlap 小于 target、release retention 不小于 2。

## 6. 核心数据模型

### 6.1 SourceRecord

```json
{
  "schema_version": "source-record.v1",
  "source_id": "src_...",
  "source_uri": "https://...",
  "local_path": "official-docs/fenitop/README.md",
  "domain": "fenitop-examples",
  "media_type": "text/markdown",
  "sha256": "...",
  "revision": "git-sha-or-date",
  "retrieved_at": "2026-09-08T00:00:00Z",
  "license": "MIT",
  "attribution": "...",
  "security_scope": "public",
  "ingestion_status": "ready"
}
```

`source_id = src_ + sha256(canonical source_uri)[0:20]`，同一来源更新时 ID 不变、hash/version 变化。`ingestion_status` 为 `quarantined | ready | disabled | retired`。当前 manifest 中的 `downloaded` 是采集状态，不等于 `ready`；许可证和 metadata 未通过 lint 时必须进入 `quarantined`。

### 6.2 DocumentRecord 与 ChunkRecord

```json
{
  "document_id": "doc_...",
  "source_id": "src_...",
  "document_version": "sha256:...",
  "title": "...",
  "chapters": ["H1", "H1 > H2"],
  "language": "zh|en|mixed",
  "word_count": 1200,
  "pipeline_version": "pipe_..."
}
```

```json
{
  "chunk_id": "chk_...",
  "document_id": "doc_...",
  "document_version": "sha256:...",
  "ordinal": 3,
  "chapter_path": "H1 > H2",
  "content": "...",
  "content_hash": "sha256:...",
  "token_count": 386,
  "source_uri": "...",
  "source_hash": "...",
  "domain": "topopt-theory",
  "security_scope": "public",
  "pipeline_version": "pipe_..."
}
```

`chunk_id` 由 `document_id + document_version + ordinal + content_hash` 稳定计算。更新后的旧 chunk 不复用 ID，便于审计和 release 隔离。

### 6.3 IndexRelease

```json
{
  "schema_version": "index-release.v1",
  "release_id": "rel_20260908_001_ab12cd",
  "state": "ready",
  "pipeline_version": "pipe_...",
  "source_manifest_hash": "sha256:...",
  "embedding_provider": "dashscope",
  "embedding_model": "text-embedding-v4",
  "embedding_dimension": 1024,
  "qdrant_collection": "roto_kb_rel_20260908_001_ab12cd",
  "bm25_path": "releases/rel_.../bm25",
  "relations_path": "releases/rel_.../relations.sqlite",
  "document_count": 0,
  "chunk_count": 0,
  "eval_report_path": "releases/rel_.../eval.json",
  "created_at": "...",
  "activated_at": null
}
```

上例中的 `1024` 仅用于展示 release manifest 形状，不是当前已确认的 DashScope 维度；实现时必须写入 capability probe 返回且经用户确认的实际值。

状态机：

```text
draft -> building -> validating -> ready -> active -> superseded -> retired
                  \-> failed       \-> rejected
rel_empty ---------------------------------------> active (initial only)
```

状态只能由 release service 按允许边转换；每次转换写审计记录。`failed/rejected` 不能激活。

### 6.4 EvidencePackage v1

服务输出必须与 ROTO 主线契约兼容：

```json
{
  "schema_version": "evidence-package.v1",
  "query": "机器人支架拓扑优化的体积分数如何设置",
  "index_release_id": "rel_...",
  "degraded": false,
  "degradation_reasons": [],
  "no_match": false,
  "results": [{
    "doc_id": "doc_...",
    "title": "...",
    "domain": "fenitop-examples",
    "score": 0.031,
    "match_type": "hybrid",
    "snippets": [{
      "chunk_id": "chk_...",
      "chapter_path": "...",
      "content": "...",
      "source_uri": "...",
      "source_hash": "...",
      "document_version": "...",
      "security_scope": "public"
    }],
    "related_hint": []
  }]
}
```

空库或无匹配返回 HTTP 200、`results=[]`、`no_match=true`。不得将异常、空结果或低分片段转换成工程默认值。

## 7. 离线摄取设计

### 7.1 流水线

```text
manifest/source directory
 -> path guard
 -> catalog normalize + SHA-256
 -> license/metadata gate
 -> parser route
 -> canonical DocumentRecord
 -> structure-aware chunking
 -> chunk lint
 -> incremental plan
 -> DashScope embedding
 -> staging Qdrant + BM25 + relations
 -> release validation
```

每一步输入输出写入 staging release 工作目录，包含 phase、started_at、completed_at、input hash 和错误摘要；失败后可从最后一个完整 checkpoint 重试。

### 7.2 路径与格式

允许根目录仅为配置的 `ROTO_KB_SOURCE_PATH`。解析 `Resolve-Path/realpath` 后必须仍位于允许根目录；拒绝符号链接逃逸、`..`、设备文件和远端挂载。明确拒绝：`/data/knowledge-base`、`/home/ec2-user/.kb-server`、`/home/ec2-user/kb-server`。

V1 parser：

| 格式 | 解析策略 | 质量门 |
|---|---|---|
| Markdown | markdown-it AST，保留 H1-H6、代码块、列表 | 标题树可重建，正文非空 |
| Text/代码片段 | 编码探测，按空行/标记分段 | 非二进制，解码替换率受限 |
| HTML | 删除导航/脚本/样式，保留 main/article 和标题层级 | 正文占比、标题和 canonical URL |
| PDF | PyMuPDF 按页提取，保留页码 | 空页/扫描件标记；V1 不做 OCR |
| RDF/OWL/TTL | rdflib 解析类、属性、label、comment 和 URI | 语法合法、namespace 可追踪 |

RDF parser 必须关闭网络解析：`owl:imports` 仅记录为 metadata，不自动下载或推理。XML 外部实体和 DTD 禁用。每个 RDF source 设置三元组数、文件大小和解析时限；超过限制进入 quarantined。

### 7.3 切片

优先按语义结构切片：章节、函数/配置块、材料条目、本体实体。超过目标长度才递归按段落和句子切分。默认目标 400 tokens、重叠 50、最小 50；代码块、表格行和 RDF 实体描述不得从中间截断。

每个 chunk 前可添加不参与展示的检索上下文：标题、domain、chapter_path、关键术语。展示内容仍保持原文，避免把增强前缀误当引用。

### 7.4 增量计划

通过 `(source_id, sha256, pipeline_version)` 比较 active release：

- 新 source：解析、切片、向量化并加入 staging。
- hash 未变：复用上一 release 产物，不重复调用 DashScope。
- hash 改变：生成新 document version；旧版本只存在于历史 release。
- disabled：staging 中排除，但 source 和审计记录保留。
- parser/chunker/schema/Embedding 不兼容变化：全量重建，不伪装成增量。

### 7.5 外部图谱离线编译

图谱输入只来自 `knowledge/graph/deployment-manifest.yaml`。V1 active 固定选择 QUDT 白名单文件、IOF Core `Core.rdf`、W3C PROV-O/DCAT 3/SHACL 静态 TTL，以及 ROTO domain seed v1。CORA 和 PropNet 作为可选 `reference-only` source，MatOnto 作为 `link-and-map-only` source；任何未在清单中的 RDF/OWL/JSONL 即使位于 source 目录也不能进入 staging。

```text
deployment manifest
 -> verify path/hash/license/source id
 -> parse RDF without network imports / parse JSONL schema
 -> normalize URI, label, alias, relation, confidence
 -> namespace allowlist + duplicate URI check
 -> dangling endpoint + provenance check
 -> relation rows + entity search documents
 -> staging evaluation
```

规范化输出分为：

- `GraphEntity(entity_id, type, labels, aliases, domain, external_uri, source_refs, release_id)`。
- `GraphRelation(source_id, predicate, target_id, confidence, evidence_refs, release_id)`。
- `GraphRule(rule_id, body, requires, forbid_when, source_refs, release_id)`；规则只作为校验输入，不能执行任意代码。

QUDT 允许提取单位、quantity kind、dimension vector、conversion multiplier/offset 及 label；IOF 只提取 Released Core 文件中的类、对象属性、label/comment 和显式关系，不运行 BFO/import closure；PROV-O/DCAT/SHACL 只提取 ROTO 使用的 vocabulary 子集和来源定义。原始快照完整保留用于追溯，运行时关系库只保存编译后的 allowlist 子集。

图谱数据路径不调用 Materials Project、NOMAD、Materials Cloud、AFLOW、OQMD、Wikidata SPARQL 或其他在线数据 API。DashScope 仍用于文本向量化，但不是图谱 source；即使 DashScope 不可用，RDF/JSONL 图结构也能编译和通过确定性查询验收。

## 8. DashScope Provider 设计

### 8.1 Port

```python
class EmbeddingProvider(Protocol):
    async def probe(self) -> EmbeddingCapability: ...
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...
```

provider 返回纯向量，不返回 SDK 对象。probe 输出 provider、endpoint region、model、dimension 和 checked_at，不输出 key。

### 8.2 调用规则

- document 和 query 使用同一模型、维度和规范化版本。
- 以 batch 发送，单批失败可重试，不重复写 Qdrant。
- `401/403` 视为不可重试配置错误；`429/5xx/timeout` 采用指数退避加抖动，最多 4 次。
- 连续失败触发短时 circuit open；在线 query embedding 失败时使用 BM25/graph 降级。
- cache key 为 `sha256(provider + model + dimension + normalization_version + content_hash)`。
- 日志只记录 request ID、模型、批大小、耗时、状态和 token/用量聚合，不记录原文和 API key。

### 8.3 维度不变量

release build 开始前必须完成 probe。probe 实际维度、配置维度、Qdrant collection size 三者必须相同；任一不一致立即失败，不做截断、补零或自动创建另一维度的 active collection。

## 9. 索引存储设计

### 9.1 Qdrant

每个 release 一个物理 collection：`roto_kb_<release_id>`，distance 为 Cosine。payload 至少包含 `chunk_id/document_id/document_version/domain/chapter_path/source_uri/source_hash/security_scope/pipeline_version/content`。

collection 在 staging 创建，只允许按 release ID 写入。在线查询使用 `roto_kb_active` alias。payload filter 在 ANN 查询时执行，不得只在结果组装阶段过滤。

### 9.2 BM25

使用 `rank-bm25`，中文用 jieba + 工程术语词典，英文保留大小写归一后的标识符整体词元，例如 `traction_bcs`、`vol_frac`、`filter_radius`。canonical tokenized corpus 保存为 JSONL/压缩文本并带 hash，进程启动时重建内存对象；禁止反序列化不可信 pickle。

### 9.3 关系与图谱索引

SQLite 保存 `graph_entities`、`relations` 和 `graph_rules`。`relations(source_entity_id, target_entity_id, predicate, confidence, evidence_refs, release_id)` 的两端必须在同 release 存在；外部 URI 可作为 entity 的 `external_uri`，不能形成未登记悬空端点。V1 支持 depth=1 的出边/入边；`extracted` 可参与排序，`inferred/ambiguous` 只作为 related hint，不能成为工程参数唯一证据。

实体 label/alias 同时生成小型检索文档进入 BM25；是否向量化由 `embedding_enabled` 配置控制。QUDT 全量单位标签默认只进入精确词典和图索引，避免大量相似单位说明淹没普通文档向量召回。

### 9.4 Catalog 与 release registry

SQLite 使用 WAL、外键和单写者锁，保存 source、document、release、release_transition、feedback、build_job。大段原文、向量和生成索引不放 SQLite。迁移使用显式 schema version，启动时禁止自动执行破坏性 downgrade。

## 10. 在线检索设计

### 10.1 查询流程

```text
validate request + authorize scope
 -> normalize query
 -> DashScope query embedding ---------> Qdrant top 20 --\
 -> engineering tokenizer -------------> BM25 top 20 -----+-> chunk RRF
 -> optional filters --------------------------------------/
 -> document aggregate
 -> relation depth=1 enrichment
 -> evidence threshold/source validation
 -> EvidencePackage top 6
```

RRF 使用 `score(d) = sum(1/(k + rank_i(d)))`，默认 `k=60`。融合发生在 chunk 层，文档层取最高 chunk 分并保留最多 3 个去重 snippet。原始 Qdrant/BM25 分数可进入内部 explain 信息，但公网默认不返回实现细节。

### 10.2 降级矩阵

| 故障 | 行为 | 响应标记 |
|---|---|---|
| DashScope query embedding 失败 | BM25 + graph | `embedding_unavailable` |
| Qdrant 不可达 | BM25 + graph | `vector_store_unavailable` |
| BM25 未加载 | Qdrant + graph | `keyword_index_unavailable` |
| relations 不可用 | vector/BM25，不返回 related hint | `relation_index_unavailable` |
| 所有召回不可用 | 503，不伪造空命中 | `retrieval_unavailable` |
| 正常但无匹配 | 200 空 EvidencePackage | `no_match=true` |

## 11. HTTP API 设计

应用内部路由从 `/` 开始，nginx 对外添加 `/roto-kb/` 前缀。

| Method | Path | Token | 用例 |
|---|---|---|---|
| GET | `/health` | 无 | liveness/readiness、active release 聚合状态 |
| GET | `/browse` | read | 元数据分页/按 domain 过滤 |
| POST | `/search` | read | 混合召回 |
| GET | `/fetch/{doc_id}` | read | 文档或章节读取 |
| GET | `/graph/{doc_id}` | read | 关系查询 |
| GET | `/help` | read | 机器可读接口说明和版本 |
| POST | `/reload` | admin | 创建异步 staging build job |
| GET | `/builds/{job_id}` | admin | 查询构建阶段和报告 |
| GET | `/lint` | admin | source/release 质量报告 |
| GET | `/evolve/status` | admin | 自进化状态和待处理建议统计 |
| GET | `/evolve/suggestions` | admin | 查看合并/分裂建议 |
| POST | `/evolve/apply` | admin | 人工批准后执行建议 |
| POST | `/evolve/dismiss` | admin | 驳回建议并记录原因 |
| GET | `/evolve/log` | admin | 查询自进化审计日志 |
| POST | `/feedback` | read | 记录文档过时/不够用反馈 |
| GET | `/releases` | admin | release 列表和状态 |
| POST | `/releases/{id}/activate` | admin | 激活 ready release |
| POST | `/releases/{id}/rollback` | admin | 回滚到指定可恢复 release |

`POST /search`：

```json
{
  "query": "traction_bcs 面载荷如何设置",
  "filters": {"domains": ["fenitop-examples"], "security_scopes": ["public"]},
  "top_k": 6,
  "include_snippets": true,
  "snippet_count": 3
}
```

`POST /reload` 只创建 job，返回 `202`：

```json
{
  "mode": "incremental",
  "source_manifest_hash": "sha256:...",
  "idempotency_key": "client-generated-key",
  "auto_activate": false
}
```

相同 idempotency key + 相同 payload 返回原 job；同 key 不同 payload 返回 `409 knowledge.idempotency_conflict`。V1 默认禁止 `auto_activate=true`。

### 11.1 参考设计补充：reload 与自进化语义

`reload` 必须区分三种模式：`mode=incremental` 只处理 source manifest 中新增、hash 变化、停用和受反馈标记的 source；`mode=full` 重建 staging 全量索引，用于索引损坏或 parser/chunker/schema/embedding 不兼容升级；`evolve=false` 只执行确定性扫描、解析、切片、索引和 lint，跳过摘要重生成、LLM 关系和合并/分裂建议。

`evolve=true` 或 `mode=full` 异步执行。任务状态至少包括 `pending/running/completed/failed/interrupted/cancelled`，阶段包括 `detect/identify/compile/verify/persist`，并记录 `processed/total/started_at/finished_at/report`。同一时间只允许一个 build lease；冲突返回 409，不排队。服务重启后不得假称任务仍在运行，必须从 checkpoint 标记为 `interrupted`，由 admin 显式 resume 或重新构建。`rel_empty` 不对应 Qdrant collection，首次真实 release 必须完整 build/validate/activate。

自进化阈值必须配置化并写入报告：潜在重复向量相似度 `0.92`；合并候选相似度 `0.88` 且文本重叠 `0.60`；内容变化超过 `0.20` 触发摘要重生成；文档超过 `15000` 字且主题数不少于 `3` 产生分裂建议；摘要验证相似度低于 `0.70` 拒绝。合并和分裂只能生成建议，不能自动修改原始 source；人工 apply 后生成新 release。`/help` 返回当前 API、schema 版本、鉴权 scope、请求限制和错误码；`/feedback` V1 只写入审计日志并在下一次增量 build 优先处理；`/evolve/dismiss` 保存拒绝原因，并以 source hash 作为重新评估条件。

错误统一为：

```json
{"error":{"code":"knowledge.not_found","message":"Document not found","request_id":"req_..."}}
```

## 12. Release 生命周期

### 12.1 Build

构建器持有全局 build lease，同一时刻只允许一个 staging build；在线查询不加该锁。job 可恢复、可取消，但取消只影响 staging，不删除 active/previous。

`rel_empty` 是只读初始 release，不对应真实 Qdrant collection。首次有内容的 release 必须走完整 build/validate/activate。

### 12.2 Validate

ready 前必须通过：manifest/schema/hash/license gate、parser/chunk lint、Qdrant/BM25/chunk 数一致、embedding 维度一致、固定检索评测、citation 抽查、隔离路径检查和磁盘门槛。报告包含每个 gate 的结果及版本。

### 12.3 Activate

激活在进程级写锁内执行：

1. 再次确认 release 为 `ready` 且产物完整。
2. 预加载 BM25/relations runtime bundle。
3. 记录 activation intent 和 previous release。
4. 将 Qdrant alias 切向 staging collection。
5. 原子交换内存 runtime bundle 和磁盘 active manifest 指针。
6. 将 registry 状态更新为 active，旧 active 标记 superseded。
7. 执行 smoke queries；失败则按 intent 补偿回 previous。

启动恢复程序读取 activation intent、registry 和 Qdrant alias，发现不一致时优先恢复到最后一个完整 active release，不自行选择最新 staging。

### 12.4 Rollback 与清理

rollback 只能指向产物和 snapshot 均可用的 release，复用 activate 流程。retention 默认 2；清理是独立管理动作，必须跳过 active、previous、building 和被备份任务引用的 release。

## 13. 后续知识内容补充流程

### 13.1 提交包

每批知识变更必须包含 source 文件或稳定 URL、manifest 记录、license/attribution、domain/security scope、checksum，以及至少一个新增或更新的检索评测 case。允许先提交 `quarantined`，但不能激活。

外部图谱批次还必须更新 `knowledge/graph/deployment-manifest.yaml`，并通过 RDF/JSONL 语法、namespace、重复 URI、悬空关系、license notice 和无网络 import 测试。需要 API key、在线查询或记录级许可未确认的数据只能登记为 disabled connector，不能进入 active release。

```text
新增资料 PR
 -> manifest/schema/checksum/license CI
 -> merge（资料仍未上线）
 -> sync 到 /data/roto-kb/sources
 -> POST /reload incremental
 -> staging eval
 -> 人工审核报告
 -> activate
```

### 13.2 更新、停用、退役

- 更新：source ID 不变，revision/hash 变化，生成新 document version。
- 停用：设为 disabled，下个 staging release 不召回，历史 release 保留。
- 退役：记录 replacement/原因/日期；先经过回滚窗口，再允许清理历史产物。
- 删除：不作为常规内容操作；只有许可/安全要求明确时执行，并保留不可含原文的审计记录。

### 13.3 内容与引擎解耦

普通内容更新不修改应用版本。parser、chunk schema、Embedding 模型/维度或检索算法变化必须提升 `pipeline_version`，单独跑基准评测；不得与大批内容变更混在同一 release 中，以便定位质量变化来源。

## 14. 安全、可靠性与并发

### 14.1 鉴权

Bearer read/admin token 只保存 hash，常量时间比较。Qdrant 使用独立 API key。token 不同且至少 32 字节；管理接口可在 nginx 额外限制来源 IP。正式公网调用前必须使用 HTTPS，HTTP 只允许临时受限验收。

### 14.2 路径隔离

所有读写脚本共享 `PathPolicy`，只允许以下根：`/home/ec2-user/roto-kb`、`/data/roto-kb`、`/var/log/roto-kb`、`/etc/roto-kb`。任何命中旧知识库目录、父目录扫描或未解析变量均 fail closed。

### 14.3 并发与超时

- 每请求固定 active runtime snapshot，激活中途不改变该请求的 release。
- Qdrant、DashScope 和磁盘分别设置超时；不使用无限重试。
- build job 有 lease/heartbeat；失联后标记 interrupted，可显式 resume。
- fetch 限制响应大小和章节范围；browse 强制分页；search 限制 query 长度和 top_k。

## 15. 可观测性

日志字段：`request_id/job_id/release_id/phase/provider/model/duration_ms/status/degraded_reason`。严禁记录 token、API key、完整原文和异常中的 Authorization header。

指标：API count/latency/error、DashScope request/429/5xx/latency/usage、Qdrant latency、BM25 latency、fallback rate、no-match rate、build phase duration、release state、chunk/document count、磁盘和 snapshot 状态。

`/health` 分 liveness 和 readiness 语义：进程存活但无内容时为 `ok + content_status=empty`；active 依赖不可用且无法提供任何召回时 readiness 为失败。响应只给聚合信息。

## 16. 测试设计

| 层级 | 覆盖 |
|---|---|
| Unit | ID/hash、状态机、配置、parser、chunker、tokenizer、RRF、权限规则 |
| Contract | EvidencePackage、HTTP schema、错误码、Fake/Remote client 一致性 |
| Integration | DashScope fake server、真实 Qdrant test container、SQLite、BM25、release recovery |
| E2E | 空库、种子库、增量新增/修改/停用、失败 build、activate、rollback |
| Evaluation | hit@k、MRR、keyword hit、evidence coverage、citation accuracy、p95 |
| Isolation | 端口、目录、service、collection、token；旧服务 health/count 前后不变 |
| Security | token 权限、路径穿越、敏感日志、非法 payload、管理限流 |

测试 fixture 不调用真实 DashScope 计费接口；真实账号 smoke test 由显式标记的手工/受控 CI job 执行。任何真实调用必须设置请求数和费用上限。

## 17. 部署与恢复设计

生产采用 hybrid：`roto-kb.service` 管 FastAPI，Docker 管独立 Qdrant，nginx 在 TCP 443 终止 TLS 并代理 `/roto-kb/`。公网基址固定为 `https://54.172.101.190/roto-kb/`，证书必须包含 IP SAN `54.172.101.190`。Qdrant 映射 `127.0.0.1:6334 -> container:6333`，持久化到 `/data/roto-kb/qdrant`；应用监听 `127.0.0.1:8710`。nginx 配置固定为 `/etc/nginx/sites-available/roto-kb.conf`（启用链接 `/etc/nginx/sites-enabled/roto-kb.conf`），证书和私钥使用 `/etc/roto-kb/tls/` 的 root-only 文件。80 保留旧服务根路径，不代理 ROTO-KB 业务，不依赖域名 ACME challenge。

防火墙边界：AWS Security Group 只允许 TCP 443（HTTP-01 续期窗口可临时允许 80）；若服务器启用 UFW，则只允许 `443/tcp`，不允许 8710/6334。应用与 Qdrant 永远绑定 loopback。证书续期使用 `certbot renew --deploy-hook "nginx -t && systemctl reload nginx"` 或等价 hook；续期失败进入告警，不自动切换到自签名证书。

部署顺序：预检目录/端口/磁盘/Docker/443 -> 确认 DNS/SAN 和 Security Group/UFW -> 拉取固定代码和依赖 -> 配置 secret -> 配置证书和 nginx -> `nginx -t` -> 启动/校验 Qdrant -> 启动应用 -> empty/active smoke test -> HTTPS、证书链、HTTP 跳转和 nginx path 验证。代码部署不得自动 reload 或 activate 知识 release。

运维单元固定为：`/etc/systemd/system/roto-kb.service`（应用）、`/etc/systemd/system/roto-kb-lint.service`（一次性巡检）和 `/etc/systemd/system/roto-kb-lint.timer`（`OnCalendar=weekly`，默认每 7 天）；timer 通过 `systemctl enable --now roto-kb-lint.timer` 启用。巡检 unit 使用 `/home/ec2-user/roto-kb/scripts/inspect_release.py`，工作目录和输出均限制在 `/data/roto-kb`、`/var/log/roto-kb`。

部署验收必须证明：443 仅由 nginx 监听；8710/6334 只绑定 loopback；TLS 证书 SAN 覆盖 `54.172.101.190` IP；TLS 1.0/1.1 和弱密码套件被拒绝；缺少 read/admin token 分别返回 401/403；管理接口不会被匿名公网访问；80 不接受带 Authorization 的业务请求；旧 `kb-server` 的根路径、进程、端口和数据目录前后不变。

备份按同一 release 打包 source manifest、BM25/relations、registry 和 Qdrant snapshot。恢复必须校验 hash、模型/维度和 eval smoke query；仅恢复 Qdrant snapshot 不构成完整恢复。

## 18. 与 ROTO 主线联调

ROTO 主线维护 `FakeRagService` 和 `RemoteRagClient`，ROTO-KB 发布 JSON Schema/OpenAPI fixture。联调只在以下条件满足后开始：

1. `EvidencePackage v1` contract test 双方通过。
2. 空结果、401/403、429/503、timeout 和 degraded response fixture 齐全。
3. ROTO 证明 RAG 空结果不阻塞 loop、不伪造关键参数。
4. `index_release_id` 和 citation 能进入主线事件/报告。

ROTO-KB 不实现 LangGraph，不接收 solver job，不因检索命中触发求解器。

### 18.1 联调前置阻塞项

当前主线与本仓示例契约存在字段漂移：主线 `EvidenceSnippet.source` 对应本仓要求的 `source_uri/source_hash/document_version/security_scope`；主线 `degradation_reason` 为单值，而本仓还需要 `no_match` 与 `degradation_reasons[]`。在两仓共同提交 `contracts/` JSON Schema、OpenAPI 和四类 response fixture 前，不得把两边都标记为 `EvidencePackage v1` 已兼容。跨仓构建不得依赖 Windows 绝对路径；项目契约必须以 commit/SHA-256 快照或可访问的版本化契约包交付。

## 19. SDD 驱动开发规则

每个任务按以下顺序交付：契约/fixture -> 失败测试 -> 最小实现 -> 集成测试 -> 文档/运行证据。PR 只处理一个可验收任务或一个紧密任务组，并在描述中填写 PRD/SDD 条目、测试证据、迁移/回滚影响和未解决风险。

阶段门：

```text
G0 文档基线
 -> G1 空库契约
 -> G2 离线摄取
 -> G3 混合检索
 -> G4 release 管理
 -> G5 远端部署
 -> G6 主线联调
 -> G7 持续内容运营
```

后一阶段可提前开发 fake/fixture，但不得标记完成，直到前一阶段出口验收通过。

## 20. ADR 与待决事项

| ADR | 决策 | 状态 |
|---|---|---|
| ADR-001 | RAG 与 Loop Engineering 拆仓、按 HTTP 契约联调 | accepted |
| ADR-002 | Qdrant Server 独立容器，不使用旧库或嵌入式旧索引 | accepted |
| ADR-003 | DashScope 为模型 API 供应商，不自动回退其他供应商 | accepted |
| ADR-004 | Qdrant + BM25 + depth=1 relations，RRF 融合 | accepted |
| ADR-005 | staging release 评测后人工激活，默认不自动 activate | accepted |
| ADR-006 | 内容可以后补，但 metadata/license/eval gate 同步执行 | accepted |
| ADR-007 | V1 active 图谱只使用六组离线、许可边界可记录的静态内容，不依赖付费图谱 API | accepted |
| ADR-008 | CORA/PropNet/MatOnto 先登记为 reference-only/link-and-map-only，不作为 V1 active 启动依赖 | accepted |
| ADR-009 | 跨仓契约以 JSON Schema/OpenAPI/fixture 为真源，不依赖 Windows 外部路径 | accepted |

首次真实索引前仍需确认：跨仓契约字段并提交 fixture、DashScope API key 地域、最终 Embedding 模型与维度、是否启用 DashScope LLM 辅助摘要/关系抽取。上述事项不影响 G1 空库骨架，但契约字段未冻结会阻塞 KB-002/KB-601，模型/地域未确认会阻塞首次真实向量索引。
