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

编译清单必须记录这些文件的 Git commit 或 SHA-256；主线 loop 与 RAG 联调只依赖版本化 `EvidencePackage`，不依赖索引内部对象。
