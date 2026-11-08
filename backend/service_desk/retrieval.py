"""Finding the tenant's own Help desk article for a ticket (D-16, D-17).

Candidates are the tenant's own articles marked ``helpdesk`` and nothing else: an article with
tenantId ``global`` or another tenant's id, or with ``helpdesk`` not True, is never read here. The
score is the cosine of a TF-IDF vector fitted per call on the tenant's few articles, and an answer is
attempted only when the best article is close enough AND shares at least MIN_TERMS distinct words with
the ticket. ``CUT`` and ``MIN_TERMS`` are starting values; 85-06 re-pins them on the starter articles.
Pure apart from ``candidates``; no model is involved.
"""
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from autonomous_ops.scope import raw

from . import ARTICLE_TEXT_CAP, MAX_CANDIDATES, MAX_CITED

logger = logging.getLogger(__name__)

CUT = 0.25
MIN_TERMS = 2


@dataclass
class Match:
    id: str
    title: str
    content: str
    content_hash: str
    score: float
    terms: List[str] = field(default_factory=list)


async def candidates(db, tenant_id: str) -> List[Dict[str, Any]]:
    """The tenant's own Help desk articles, at most MAX_CANDIDATES."""
    if not isinstance(tenant_id, str) or not tenant_id or tenant_id == "global":
        return []
    cursor = raw(db).knowledge_docs.find({"tenantId": tenant_id, "helpdesk": True},
                                         {"_id": 0, "id": 1, "title": 1, "content": 1, "tags": 1})
    return await cursor.to_list(MAX_CANDIDATES)


def _text(doc: Dict[str, Any]) -> str:
    title = doc.get("title") if isinstance(doc.get("title"), str) else ""
    content = doc.get("content") if isinstance(doc.get("content"), str) else ""
    tags = doc.get("tags") if isinstance(doc.get("tags"), list) else []
    return " ".join([title, title, title, " ".join(t for t in tags if isinstance(t, str)),
                     content[:ARTICLE_TEXT_CAP]])


def score(question: str, docs: List[Dict[str, Any]]) -> List[Match]:
    """Every doc scored against the question, best first. Empty when nothing can be scored."""
    docs = [d for d in docs if isinstance(d, dict) and isinstance(d.get("id"), str)]
    if not docs or not isinstance(question, str) or not question.strip():
        return []
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import linear_kernel
    texts = [_text(d) for d in docs]
    try:
        vectorizer = TfidfVectorizer(sublinear_tf=True, stop_words="english")
        matrix = vectorizer.fit_transform(texts)
        sims = linear_kernel(vectorizer.transform([question]), matrix)[0]
    except ValueError:      # an empty vocabulary: nothing to compare
        return []
    analyze = vectorizer.build_analyzer()
    asked = set(analyze(question))
    matches = []
    for doc, text, sim in zip(docs, texts, sims):
        content = doc.get("content") if isinstance(doc.get("content"), str) else ""
        matches.append(Match(
            id=doc["id"], title=doc.get("title") if isinstance(doc.get("title"), str) else "", content=content,
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest()[:16], score=float(sim),
            terms=sorted(asked & set(analyze(text)))))
    matches.sort(key=lambda m: (-m.score, m.id))
    return matches


def select(matches: List[Match]) -> List[Match]:
    """The articles to answer from, or [] when none is close enough: the best must reach CUT with at
    least MIN_TERMS shared words; up to MAX_CITED more qualify at half the best score or CUT."""
    if not matches:
        return []
    best = matches[0]
    if best.score < CUT or len(best.terms) < MIN_TERMS:
        return []
    floor = max(CUT, 0.5 * best.score)
    return [m for m in matches if m.score >= floor and len(m.terms) >= MIN_TERMS][:MAX_CITED]
