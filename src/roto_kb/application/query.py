from ..service import KnowledgeService


def retrieve(service: KnowledgeService, query: str, *, filters=None, top_k=6):
    return service.search(query, filters=filters, top_k=top_k)


def browse(service: KnowledgeService):
    return service.browse()


def fetch(service: KnowledgeService, doc_id: str, *, chapter=None):
    return service.fetch(doc_id, chapter)
