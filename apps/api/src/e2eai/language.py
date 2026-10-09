"""Deterministic language detection for Indonesian vs English (FR-C13).

The P0 detector uses a word-frequency heuristic: if a sufficient proportion of tokens
match common Indonesian function words (prepositions, pronouns, conjunctions, question words),
classify as Indonesian; otherwise English. This is intentionally simple and offline — no
external paid services.
"""

import re

_INDONESIAN_WORDS = frozenset({
    # Question words
    "apa", "siapa", "kapan", "dimana", "mengapa", "kenapa", "bagaimana",
    "berapa", "mana",
    # Pronouns
    "saya", "aku", "kamu", "anda", "dia", "ia", "kami", "kita", "mereka",
    # Prepositions / conjunctions / particles
    "di", "ke", "dari", "untuk", "dengan", "pada", "dalam", "oleh",
    "dan", "atau", "tetapi", "tapi", "namun", "karena", "jika", "kalau",
    "yang", "ini", "itu", "adalah", "ada", "tidak", "bukan", "belum",
    "sudah", "akan", "bisa", "harus", "perlu", "boleh", "mau",
    # Common verbs/words
    "tolong", "mohon", "jelaskan", "ceritakan", "beritahu",
    "tentang", "mengenai", "terkait", "antara", "seperti",
    "bagi", "hasil", "dokumen", "berikan",
    # Additional common words
    "tahu", "ingin", "kuartal", "pendapatan", "bersih",
})

_WORD_RE = re.compile(r"[a-zA-Z\u00C0-\u024F]+")


def detect_language(text: str) -> str:
    """Classify text as Indonesian ('id') or English ('en').

    Uses a simple token overlap heuristic: the proportion of tokens that match common Indonesian
    function/content words. If >= 25% of tokens are Indonesian, classify as 'id'.
    """
    tokens = [t.lower() for t in _WORD_RE.findall(text)]
    if not tokens:
        return "en"
    indonesian_count = sum(1 for t in tokens if t in _INDONESIAN_WORDS)
    ratio = indonesian_count / len(tokens)
    return "id" if ratio >= 0.25 else "en"
