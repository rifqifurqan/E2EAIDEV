"""Advanced RAG helpers: knowledge-base routing, GraphRAG-style expansion, multimodal intent (FR-R9).

Deterministic/offline and pure. These helpers only see what the caller already permission-filtered:
routing is restricted to the knowledge bases the caller says the user may access, and the entity graph is
built from chunks that already passed the SQL permission filter, so nothing here can widen access.
Outputs carry ids, scores, and lowercased entity names only: never chunk text.
"""

from __future__ import annotations

import re
from collections import deque
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .auth import current_session, require_scope
from .core.errors import AppError
from .hybrid_search import tokenize

MAX_HOPS = 3
MAX_KBS = 200
MAX_CHUNKS = 2000
MAX_CHUNK_CHARS = 20_000

# Entity = run of 2+ capitalised words ("Alice Johnson", "Annual Budget"). Single capitalised words
# (sentence starts such as "The") are ignored on purpose to keep the graph precise.
_ENTITY_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")

_CHART_WORDS = frozenset({"chart", "charts", "plot", "grafik", "bagan", "histogram", "graph"})
_FIGURE_WORDS = frozenset({
    "diagram", "figure", "image", "picture", "gambar", "foto", "schematic", "skema", "illustration", "ilustrasi",
})


def route_knowledge_bases(
    query: str, knowledge_bases: list[dict[str, Any]], *, accessible_ids: set[str], top_k: int = 3,
) -> dict[str, Any]:
    """Rank accessible knowledge bases by overlap between the query and each KB's topic words."""
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    q = set(tokenize(query))
    scored: list[tuple[int, str]] = []
    reachable: list[str] = []
    for kb in knowledge_bases:
        kid = kb.get("id")
        if not isinstance(kid, str) or kid not in accessible_ids:
            continue  # inaccessible KBs are never scored, so they cannot leak through ranking
        reachable.append(kid)
        topics = {t for topic in kb.get("topics") or [] for t in tokenize(str(topic))}
        overlap = len(q & topics)
        if overlap:
            scored.append((overlap, kid))
    if scored:
        scored.sort(key=lambda s: (-s[0], s[1]))
        best = scored[0][0]
        routes = [{"kb_id": kid, "score": round(n / best, 4)} for n, kid in scored[:top_k]]
        return {"routes": routes, "fallback": False}
    if not reachable:
        return {"routes": [], "fallback": False}
    return {"routes": [{"kb_id": kid, "score": 0.0} for kid in sorted(reachable)[:top_k]], "fallback": True}


def _entities(text: str) -> list[str]:
    seen: list[str] = []
    for m in _ENTITY_RE.findall(text or ""):
        name = " ".join(m.lower().split())
        if name not in seen:
            seen.append(name)
    return seen


def build_entity_graph(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    entity_chunks: dict[str, list[str]] = {}
    edges: dict[str, set[str]] = {}
    for ch in chunks:
        cid = str(ch.get("id"))
        ents = _entities(str(ch.get("text") or ""))
        for e in ents:
            entity_chunks.setdefault(e, [])
            if cid not in entity_chunks[e]:
                entity_chunks[e].append(cid)
            edges.setdefault(e, set())
        for a in ents:
            for b in ents:
                if a != b:
                    edges[a].add(b)
    return {
        "entities": sorted(entity_chunks),
        "entity_chunks": entity_chunks,
        "edges": {k: sorted(v) for k, v in edges.items()},
        "chunk_order": [str(c.get("id")) for c in chunks],
    }


def expand_with_graph(graph: dict[str, Any], query: str, *, hops: int = 1) -> dict[str, Any]:
    """Find chunks connected to the query's entities within `hops` co-occurrence links (closest first)."""
    if not isinstance(hops, int) or isinstance(hops, bool) or not 0 <= hops <= MAX_HOPS:
        raise ValueError(f"hops must be between 0 and {MAX_HOPS}")
    lowered = " ".join((query or "").lower().split())
    seeds = [e for e in graph["entities"] if re.search(rf"(?<!\w){re.escape(e)}(?!\w)", lowered)]
    dist: dict[str, int] = {s: 0 for s in seeds}
    frontier = deque(seeds)
    while frontier:
        cur = frontier.popleft()
        if dist[cur] >= hops:
            continue
        for nxt in graph["edges"].get(cur, []):
            if nxt not in dist:
                dist[nxt] = dist[cur] + 1
                frontier.append(nxt)
    chunk_dist: dict[str, int] = {}
    for ent, d in dist.items():
        for cid in graph["entity_chunks"].get(ent, []):
            chunk_dist[cid] = min(d, chunk_dist.get(cid, d))
    order = {cid: i for i, cid in enumerate(graph.get("chunk_order", []))}
    ranked = sorted(chunk_dist, key=lambda c: (chunk_dist[c], order.get(c, 0)))
    return {"seed_entities": seeds, "chunk_ids": ranked, "hops": hops}


def detect_modality(query: str) -> str:
    words = set(tokenize(query))
    if words & _CHART_WORDS:
        return "chart"
    if words & _FIGURE_WORDS:
        return "figure"
    return "text"


def rerank_by_modality(chunks: list[dict[str, Any]], modality: str) -> list[dict[str, Any]]:
    """Boost chunks whose `kind` matches the asked-for modality (stable for ties)."""
    def key(item: tuple[int, dict[str, Any]]) -> tuple[float, int]:
        i, c = item
        score = float(c.get("score", 0.0))
        if modality in ("chart", "figure"):
            if c.get("kind") == modality:
                score += 0.5
            elif c.get("kind") in ("chart", "figure"):
                score += 0.1
        return (-score, i)

    return [c for _, c in sorted(enumerate(chunks), key=key)]


class KbIn(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(default="", max_length=200)
    topics: list[str] = Field(default=[], max_length=200)


class RouteKbsIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    knowledge_bases: list[KbIn] = Field(max_length=MAX_KBS)
    accessible_ids: list[str] = Field(max_length=MAX_KBS)
    top_k: int = Field(default=3, ge=1, le=20)


class GraphChunkIn(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    text: str = Field(max_length=MAX_CHUNK_CHARS)


class GraphExpandIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    chunks: list[GraphChunkIn] = Field(max_length=MAX_CHUNKS)
    hops: int = 1


router = APIRouter(prefix="/api/v1/retrieval", tags=["retrieval"])


@router.post("/route-kbs")
async def route_kbs_api(body: RouteKbsIn, sess: dict = Depends(current_session)) -> dict[str, Any]:
    """FR-R9: pick which of the user's accessible knowledge bases to search (also returns modality intent)."""
    require_scope(sess, "chat")
    try:
        result = route_knowledge_bases(
            body.query, [k.model_dump() for k in body.knowledge_bases],
            accessible_ids=set(body.accessible_ids), top_k=body.top_k,
        )
    except ValueError as exc:
        raise AppError(400, str(exc)) from exc
    result["modality"] = detect_modality(body.query)
    return result


@router.post("/graph-expand")
async def graph_expand_api(body: GraphExpandIn, sess: dict = Depends(current_session)) -> dict[str, Any]:
    """FR-R9: GraphRAG-style multi-hop expansion over already permission-filtered chunks (ids only returned)."""
    require_scope(sess, "chat")
    graph = build_entity_graph([c.model_dump() for c in body.chunks])
    try:
        return expand_with_graph(graph, body.query, hops=body.hops)
    except ValueError as exc:
        raise AppError(400, str(exc)) from exc
