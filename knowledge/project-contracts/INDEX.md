# ROTO 项目契约索引

知识库编译时应把以下仓库文件作为 `project-contracts` 来源读取，不复制出第二份，避免版本漂移：

- `docs/PRD-LLM-RAG-Topology-Optimization-Agent.md`
- `docs/SDD-LLM-RAG-Topology-Optimization-Agent.md`
- `docs/tasks/T02-RAG知识索引与参数校验.md`
- `backend/app/domain/contracts.py`
- `backend/app/rag/index.py`
- `backend/app/rag/sqlite_index.py`
- `backend/app/rag/validation.py`
- `tests/test_parameters_and_rag.py`

外部图谱种子选型还追踪以下调研产物；它们是设计输入，不直接作为部署白名单：

- `docs/外部知识图谱调研与ROTO知识库种子.md`
- `data/rag/knowledge_graph_seed.jsonl`
- `data/rag/knowledge_source_manifest.json`

编译清单必须记录这些文件的 Git commit 或 SHA-256；主线 loop 与 RAG 联调只依赖版本化 `EvidencePackage`，不依赖索引内部对象。
