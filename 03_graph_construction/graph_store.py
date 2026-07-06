"""
Component 3 — Graph store abstraction with two backends behind ONE interface:
  - NetworkXGraphStore: in-process, runnable/verifiable in any environment (used to prove logic).
  - Neo4jGraphStore: production backend for Catalyst AppSail (containerized Neo4j).
Both implement the same methods, so Components 4 & 5 are backend-agnostic.

NODE TYPES: FIR, Person, Location, PoliceStation, District, Section, Victim, Complainant,
            Phone, Vehicle, FinancialAccount   (last 3 added by Component 4)
EDGE TYPES: ACCUSED_IN, VICTIM_IN, COMPLAINANT_IN, REGISTERED_AT, OCCURRED_AT, CHARGED_UNDER,
            USED_PHONE, OWNS_VEHICLE, TRANSACTED_VIA   (last 3 added by Component 4)

CRITICAL BOUNDARY: Component 3 creates ONE Person node per Accused row. It performs NO
cross-case merging. Five accused rows for one real person = five Person nodes, by design.
Resolution is Component 5's job and must not be pre-empted here.
"""

# ---- Cypher identifier safety (labels & rel-types cannot be parameterized) ----
ALLOWED_LABELS = {"FIR","Person","Location","PoliceStation","District","Section","Victim",
                  "Complainant","Phone","Vehicle","FinancialAccount"}
ALLOWED_RELS = {"ACCUSED_IN","VICTIM_IN","COMPLAINANT_IN","REGISTERED_AT","OCCURRED_AT",
                "CHARGED_UNDER","IN_DISTRICT","USED_PHONE","PERSON_USED_PHONE","VEHICLE_SEEN",
                "OWNS_VEHICLE","TRANSACTED_VIA","CO_ACCUSED_WITH","SAME_MO_AS"}

def _safe_label(label):
    # Defense-in-depth: allowlist first; also enforce identifier charset.
    if label not in ALLOWED_LABELS or not label.replace("_","").isalnum():
        raise ValueError(f"Unsafe/unknown node label rejected: {label!r}")
    return label

def _safe_rel(rel):
    if rel not in ALLOWED_RELS or not rel.replace("_","").isalnum():
        raise ValueError(f"Unsafe/unknown relationship type rejected: {rel!r}")
    return rel


class BaseGraphStore:
    def add_node(self, node_id, label, **props): raise NotImplementedError
    def add_edge(self, src, dst, rel, **props): raise NotImplementedError
    def node_count_by_label(self): raise NotImplementedError
    def edge_count_by_rel(self): raise NotImplementedError
    def find_nodes(self, label, **filters): raise NotImplementedError
    def get_node(self, node_id): raise NotImplementedError
    def neighbors(self, node_id, rel=None): raise NotImplementedError


class NetworkXGraphStore(BaseGraphStore):
    def __init__(self):
        import networkx as nx
        self.g = nx.MultiDiGraph()
    def add_node(self, node_id, label, **props):
        self.g.add_node(node_id, label=label, **props)
    def add_edge(self, src, dst, rel, **props):
        self.g.add_edge(src, dst, key=rel, rel=rel, **props)
    def node_count_by_label(self):
        out = {}
        for _, d in self.g.nodes(data=True):
            out[d.get("label","?")] = out.get(d.get("label","?"),0)+1
        return out
    def edge_count_by_rel(self):
        out = {}
        for _,_,d in self.g.edges(data=True):
            out[d.get("rel","?")] = out.get(d.get("rel","?"),0)+1
        return out
    def find_nodes(self, label, **filters):
        res = []
        for nid, d in self.g.nodes(data=True):
            if d.get("label") != label: continue
            if all(d.get(k)==v for k,v in filters.items()):
                res.append((nid, d))
        return res
    def get_node(self, node_id):
        return self.g.nodes[node_id] if node_id in self.g.nodes else None
    def neighbors(self, node_id, rel=None):
        res=[]
        for _, dst, d in self.g.out_edges(node_id, data=True):
            if rel is None or d.get("rel")==rel: res.append((dst, d))
        for src, _, d in self.g.in_edges(node_id, data=True):
            if rel is None or d.get("rel")==rel: res.append((src, d))
        return res


class Neo4jGraphStore(BaseGraphStore):
    """
    Production backend. Requires: pip install neo4j ; a running Neo4j (containerized on AppSail).
    Credentials via env vars NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD — NEVER hardcoded.
    """
    def __init__(self, uri=None, user=None, password=None):
        import os
        from neo4j import GraphDatabase
        uri = uri or os.environ["NEO4J_URI"]
        user = user or os.environ["NEO4J_USER"]
        password = password or os.environ["NEO4J_PASSWORD"]
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
    def add_node(self, node_id, label, **props):
        props = {**props, "node_id": node_id}
        with self.driver.session() as s:
            s.run(f"MERGE (n:{_safe_label(label)} {{node_id:$node_id}}) SET n += $props",
                  node_id=node_id, props=props)
    def add_edge(self, src, dst, rel, **props):
        with self.driver.session() as s:
            s.run(f"""MATCH (a {{node_id:$src}}), (b {{node_id:$dst}})
                      MERGE (a)-[r:{_safe_rel(rel)}]->(b) SET r += $props""",
                  src=src, dst=dst, props=props)
    def node_count_by_label(self):
        with self.driver.session() as s:
            res = s.run("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS c")
            return {r["label"]: r["c"] for r in res}
    def edge_count_by_rel(self):
        with self.driver.session() as s:
            res = s.run("MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS c")
            return {r["rel"]: r["c"] for r in res}
    def find_nodes(self, label, **filters):
        clause = " AND ".join(f"n.{k}=${k}" for k in filters)
        where = f"WHERE {clause}" if clause else ""
        with self.driver.session() as s:
            res = s.run(f"MATCH (n:{_safe_label(label)}) {where} RETURN n", **filters)
            return [(r["n"]["node_id"], dict(r["n"])) for r in res]
    def get_node(self, node_id):
        with self.driver.session() as s:
            res = s.run("MATCH (n {node_id:$id}) RETURN n", id=node_id).single()
            return dict(res["n"]) if res else None
    def neighbors(self, node_id, rel=None):
        rel_pat = f":{_safe_rel(rel)}" if rel else ""
        with self.driver.session() as s:
            res = s.run(f"MATCH (n {{node_id:$id}})-[r{rel_pat}]-(m) RETURN m, type(r) AS rel", id=node_id)
            return [(r["m"]["node_id"], {**dict(r["m"]), "rel": r["rel"]}) for r in res]
    def close(self): self.driver.close()
