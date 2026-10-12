"""FR-R9 advanced RAG: routing across knowledge bases, GraphRAG-style entity expansion, multimodal intent.

Deterministic/offline pure helpers. They only ever see what the caller already permission-filtered:
routing is restricted to knowledge bases the user may access, and the entity graph is built from chunks
that already passed the SQL permission filter, so nothing here can widen access. Output carries ids,
scores, and entity names only: never chunk text.
"""

import pytest


KBS = [
    {"id": "kb-hr", "name": "HR policies", "topics": ["leave", "payroll", "benefits", "cuti", "gaji"]},
    {"id": "kb-it", "name": "IT support", "topics": ["vpn", "laptop", "password", "wifi"]},
    {"id": "kb-fin", "name": "Finance", "topics": ["invoice", "budget", "expense", "reimbursement"]},
]


def test_routing_ranks_kbs_by_topic_overlap_in_en_and_id():
    from e2eai.advanced_rag import route_knowledge_bases

    r = route_knowledge_bases("How many leave days and what benefits do I get?", KBS, accessible_ids={"kb-hr", "kb-it", "kb-fin"})
    assert [x["kb_id"] for x in r["routes"]][0] == "kb-hr" and r["fallback"] is False
    idr = route_knowledge_bases("berapa sisa cuti dan gaji saya", KBS, accessible_ids={"kb-hr", "kb-it"})
    assert idr["routes"][0]["kb_id"] == "kb-hr"
    assert all(x["score"] > 0 for x in r["routes"])


def test_routing_never_returns_inaccessible_kbs():
    from e2eai.advanced_rag import route_knowledge_bases

    r = route_knowledge_bases("leave and payroll", KBS, accessible_ids={"kb-it"})
    assert {x["kb_id"] for x in r["routes"]} <= {"kb-it"}
    assert "kb-hr" not in str(r)
    empty = route_knowledge_bases("leave", KBS, accessible_ids=set())
    assert empty["routes"] == [] and empty["fallback"] is False


def test_routing_falls_back_to_all_accessible_when_nothing_matches_and_limits_top_k():
    from e2eai.advanced_rag import route_knowledge_bases

    r = route_knowledge_bases("quantum chromodynamics", KBS, accessible_ids={"kb-hr", "kb-it"})
    assert r["fallback"] is True and {x["kb_id"] for x in r["routes"]} == {"kb-hr", "kb-it"}
    multi = route_knowledge_bases("vpn leave invoice", KBS, accessible_ids={"kb-hr", "kb-it", "kb-fin"}, top_k=2)
    assert len(multi["routes"]) == 2


CHUNKS = [
    {"id": "c1", "text": "Alice Johnson leads the Payroll Team and reports to Bob Smith."},
    {"id": "c2", "text": "Bob Smith approves the Annual Budget together with Carol Lee."},
    {"id": "c3", "text": "Carol Lee manages the Vendor Portal."},
    {"id": "c4", "text": "The cafeteria opens at 8am."},
]


def test_entity_graph_links_cooccurring_entities():
    from e2eai.advanced_rag import build_entity_graph

    g = build_entity_graph(CHUNKS)
    assert "bob smith" in g["entities"] and "alice johnson" in g["entities"]
    assert "bob smith" in g["edges"]["alice johnson"]
    assert "c4" not in {c for cs in g["entity_chunks"].values() for c in cs}  # no entities there
    assert g["entity_chunks"]["bob smith"] == ["c1", "c2"]


def test_graph_expansion_finds_multi_hop_chunks():
    from e2eai.advanced_rag import build_entity_graph, expand_with_graph

    g = build_entity_graph(CHUNKS)
    one = expand_with_graph(g, "What does Alice Johnson do?", hops=1)
    assert one["seed_entities"] == ["alice johnson"]
    assert one["chunk_ids"][:1] == ["c1"] and "c2" not in one["chunk_ids"][:1]
    assert "c2" in one["chunk_ids"]  # via Bob Smith
    assert "c3" not in one["chunk_ids"]  # two hops away
    two = expand_with_graph(g, "What does Alice Johnson do?", hops=2)
    assert "c3" in two["chunk_ids"] and two["chunk_ids"].index("c1") < two["chunk_ids"].index("c3")
    none = expand_with_graph(g, "cafeteria hours?", hops=2)
    assert none["seed_entities"] == [] and none["chunk_ids"] == []
    assert "Alice" not in str(one)  # entity names only lowercased; no chunk text
    with pytest.raises(ValueError):
        expand_with_graph(g, "x", hops=5)


def test_multimodal_intent_prefers_figure_and_chart_chunks():
    from e2eai.advanced_rag import detect_modality, rerank_by_modality

    assert detect_modality("Show me the revenue chart for Q3") == "chart"
    assert detect_modality("grafik penjualan tahun lalu") == "chart"
    assert detect_modality("what does the wiring diagram look like") == "figure"
    assert detect_modality("how many leave days") == "text"

    chunks = [
        {"id": "t1", "kind": "text", "score": 0.9},
        {"id": "ch1", "kind": "chart", "score": 0.6},
        {"id": "f1", "kind": "figure", "score": 0.7},
    ]
    out = rerank_by_modality(chunks, "chart")
    assert [c["id"] for c in out][0] == "ch1" and {c["id"] for c in out} == {"t1", "ch1", "f1"}
    same = rerank_by_modality(chunks, "text")
    assert [c["id"] for c in same] == ["t1", "f1", "ch1"]


def test_routes_wired():
    from e2eai.main import app

    paths = app.openapi()["paths"]
    assert "post" in paths["/api/v1/retrieval/route-kbs"]
    assert "post" in paths["/api/v1/retrieval/graph-expand"]
