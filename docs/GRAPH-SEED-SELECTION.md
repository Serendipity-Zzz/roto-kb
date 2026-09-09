# 外部图谱离线种子选型

日期：2026-09-09

输入调研：ROTO 主仓库的 `docs/外部知识图谱调研与ROTO知识库种子.md`、`data/rag/knowledge_graph_seed.jsonl`、`data/rag/knowledge_source_manifest.json`。

## 选型原则

V1 只接收无需付费 API、无需运行时 API key、可离线解析、许可/再分发边界可记录、能够直接改善单位/来源/工业语义的内容。外部 RDF 的本体语义用于检索、映射和校验，不作为工程材料许用值或求解结论。

“保留”分为两种状态：

- `active-offline`：文件已纳入本仓库并可进入部署白名单。
- `reference-only`：只登记 canonical URL、revision、用途和映射计划；默认不进入 active release。即使项目非商用，也不把缺失授权解释为自动获得再分发权。

## 最终纳入

| 内容 | 本地位置 | 纳入范围 | 作用 |
|---|---|---|---|
| QUDT | `knowledge/ontologies/qudt/` | schema、units、quantity kinds、dimension vectors 白名单 | 单位归一、量纲和物理量 URI |
| IOF Core | `knowledge/ontologies/iof-core/core/Core.rdf` | maturity=Released 的 Core 文件，只抽 label/comment/明确关系 | 工业对象、过程、设计产物上位语义 |
| W3C PROV-O | `knowledge/ontologies/w3c/prov-o.ttl` | 原始 vocabulary 快照 | source、artifact、release 的 provenance |
| W3C DCAT 3 | `knowledge/ontologies/w3c/dcat3.ttl` | 原始 vocabulary 快照 | Dataset/Distribution/CatalogRecord 来源目录 |
| W3C SHACL | `knowledge/ontologies/w3c/shacl.ttl` | vocabulary；ROTO shapes 以后单独编写 | 图数据和字段约束词汇 |
| ROTO domain seed v1 | `knowledge/graph/seeds/roto-domain-seed.v1.jsonl` | 41 nodes、18 relations、3 rules | 工程别名、FEniTop 字段映射和安全规则 |

部署清单由 `knowledge/graph/deployment-manifest.yaml` 固定。首批编译不得递归吞入 QUDT/IOF 仓库全部文件，也不得联网解析 `owl:imports`；否则会引入不受控体积、重复上位本体和版本漂移。

## 保留但默认不激活的候选

| 候选 | 处理 | 当前结论 |
|---|---|---|
| IEEE 1872 CORA/RPARTS/POS | `reference-only`，可在保留 CC BY-4.0 声明和 IEEE 标准版权说明后单独启用 | 仓库 README 明确声明 OWL 实现为 CC BY-4.0；`owl:imports` 必须离线白名单化，不能联网闭包推理 |
| PropNet | `reference-only`，保留 LICENSE、版权和依赖归属；只抽取符号/模型说明，不直接执行模型 | 仓库 `LICENSE` 为 BSD 风格定制文本，允许源码/二进制再分发，但 Materials Project/依赖/数据文件仍需逐项核对 |
| MatOnto | `reference-only` / `link-and-map-only` | 仓库和 OWL 文件未发现明确标准再分发许可证；可登记链接、术语 URI 和内部映射，不复制原 OWL |

这三项有研究价值，可以保留在 manifest；它们不是 V1 active 图谱的启动依赖。需要进入 active release 时，必须另建内容 PR、记录文件级 hash/许可证证据并通过人工审核。

## 明确不纳入 V1

| 候选 | 处理 | 原因 |
|---|---|---|
| Materials Project | 未来 connector，默认关闭 | 需要 API key/服务依赖；计算材料数据不是工程许用值 |
| NOMAD、Materials Cloud、AFLOW、OQMD | 未来离线数据批次或 connector | 在线接口、记录级许可或可用性仍需逐项确认 |
| Wikidata | 不纳入首批 | 全量 dump 太大且通用实体噪声高；不为少量别名依赖 SPARQL API |
| AiiDA | 文档参考，不作图谱种子 | 它是工作流/provenance 软件，PROV-O 已覆盖 V1 语义需求 |
| Common Core Ontologies、OBO RO | 暂缓 | 与 IOF/BFO 上位语义重叠，可能增加类冲突，V1 收益有限 |

原调研种子中的 `Aluminum6061T6`、`MaterialProject`、`CORA` 节点及相关关系已从部署版种子删除；`Material` 只保留为概念，不带强度、弹性、疲劳或温度数值。材料事实必须以后由有明确许可、带牌号/状态/温度/单位/来源的离线表进入独立 release。

## 许可与更新

- QUDT：CC BY 4.0，保留 QUDT.org attribution。
- IOF：MIT，保留仓库 LICENSE；当前 Core 声明 maturity `Released`。
- W3C vocabulary：原样快照并保留 canonical URL、W3C copyright 和 Document License notice。
- ROTO seed：项目自有内容，所有 `source_refs` 必须能解析到已登记 source。
- CORA：保留 CC BY-4.0 notice、IEEE 标准版权说明和 canonical URL；默认只做 reference mapping。
- PropNet：保留仓库 `LICENSE`、版权、依赖和数据来源说明；不得把模型推导结果当作工程许用值。
- MatOnto：仅保留 canonical URL、revision 和内部映射；未取得明确授权前不复制 OWL 文件。

更新外部快照必须新建知识内容 PR，记录 URL、retrieved_at、ETag/版本和 SHA-256，跑 RDF 语法、重复 URI、悬空关系、许可和固定检索用例后才进入 staging release。

## 当前校验结果

2026-09-09 使用 `rdflib 7.1.4` 离线解析全部白名单文件成功，共 86,721 triples：W3C 三份 3,969、QUDT 四份 78,520、IOF Core 4,232。ROTO seed 共 62 条记录（41 nodes、18 relations、3 rules），无重复 node ID、无悬空关系、无未知 `source_refs`，且不含被排除的 API/许可未决来源引用。知识目录 563 个静态文件的 SHA-256 已重新生成并逐项校验。CORA、MatOnto、PropNet 当前只做 manifest/reference 状态，不计入上述 active triples。
