"""Conversation-aware query rewriting for follow-up questions (FR-R6).

Pure, deterministic and offline (no LLM call). A follow-up such as "How much is it?" is expanded
with the topic keywords of the most recent standalone *user* question so retrieval can find the
right chunks. Only the caller's own earlier user questions are used (never assistant output or
retrieved text), so rewriting cannot import injected instructions or widen access: the rewritten
string is only the retrieval query, and permission filtering still happens inside the SQL query.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

MAX_QUERY_CHARS = 500
MAX_TOPIC_TERMS = 12

_WORD_RE = re.compile(r"[a-z0-9]+")

# Single-word follow-up markers (English + Indonesian): pronouns/anaphora and continuation words.
_MARKER_WORDS = frozenset({
    "it", "its", "that", "this", "they", "them", "their", "those", "these", "he", "she", "him", "her",
    "also", "then", "and", "but", "so",
    "itu", "ini", "tersebut", "mereka", "dia", "nya", "lalu", "kemudian", "terus", "kalau", "jika",
    "dan", "tapi", "serta", "juga",
})
# Multi-word follow-up phrases, matched on the normalised token string.
_MARKER_PHRASES = ("what about", "how about", "bagaimana dengan", "gimana dengan", "apa itu lagi")

_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "do", "does", "did", "of", "to", "in",
    "on", "for", "with", "at", "by", "from", "as", "what", "who", "whom", "which", "when", "where",
    "why", "how", "much", "many", "about", "can", "could", "would", "should", "will", "tell", "me",
    "please", "i", "we", "you", "my", "our", "your",
    "apa", "siapa", "kapan", "dimana", "di", "ke", "dari", "yang", "untuk", "dengan", "adalah",
    "berapa", "bagaimana", "gimana", "mengapa", "kenapa", "bisa", "tolong", "saya", "kami", "kita",
    "anda", "atau", "pada", "akan", "ada", "apakah",
}) | _MARKER_WORDS


@dataclass(frozen=True)
class RewriteResult:
    original: str
    rewritten: str
    applied: bool
    reason: str

    def as_dict(self) -> dict:
        """Safe, serialisable summary (no history text) for API responses and audit."""
        return {"applied": self.applied, "reason": self.reason}


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


def is_follow_up(question: str) -> bool:
    """True when the question depends on earlier conversation (anaphora / continuation)."""
    tokens = _tokens(question)
    if not tokens:
        return False
    if any(t in _MARKER_WORDS for t in tokens):
        return True
    joined = " ".join(tokens)
    return any(phrase in joined for phrase in _MARKER_PHRASES)


def _topic_terms(text: str, exclude: set[str]) -> list[str]:
    terms: list[str] = []
    for tok in _tokens(text):
        if tok in _STOPWORDS or tok in exclude or tok in terms or len(tok) < 2:
            continue
        terms.append(tok)
        if len(terms) >= MAX_TOPIC_TERMS:
            break
    return terms


def rewrite_query(question: str, history: Sequence[str]) -> RewriteResult:
    """Expand a follow-up *question* using prior user questions in *history* (oldest first)."""
    original = question
    if not is_follow_up(question):
        return RewriteResult(original, original, False, "standalone")
    prior = [h for h in history if h and h.strip()]
    if not prior:
        return RewriteResult(original, original, False, "no_history")
    anchor = next((h for h in reversed(prior) if not is_follow_up(h)), None)
    if anchor is None:
        return RewriteResult(original, original, False, "no_anchor")
    terms = _topic_terms(anchor, exclude=set(_tokens(question)))
    if not terms:
        return RewriteResult(original, original, False, "no_topic")
    rewritten = f"{question.strip()} {' '.join(terms)}"[:MAX_QUERY_CHARS]
    return RewriteResult(original, rewritten, True, "follow_up")
