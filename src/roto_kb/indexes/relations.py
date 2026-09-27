from __future__ import annotations

from collections import defaultdict


class RelationIndex:
    def __init__(self): self.entities, self.relations = {}, []
    def add_entity(self, entity): self.entities[entity.entity_id] = entity
    def add_relation(self, relation):
        if relation.source_id not in self.entities or relation.target_id not in self.entities:
            raise ValueError("relation endpoint is not registered")
        self.relations.append(relation)
    def related(self, entity_id: str, depth: int = 1):
        if depth != 1: raise ValueError("only depth=1 is supported")
        out=[]
        for r in self.relations:
            if r.source_id == entity_id or r.target_id == entity_id: out.append(r)
        return out
