"""Gap rows: the questions the desk could not answer for want of an article (D-26).

One row per ticket and reason, written only when a ticket is handed to a person because no article
matched or the ticket was not in English. The text is the cleaned question (no markup, links or
addresses) cut to ``GAP_TEXT_CAP`` characters, and the rows expire after 90 days (store.ensure_indexes).
The Knowledge Base gap list reads them back (D-26, DESK-06): the open ``no_article`` rows of the last 90 days
(at most 500, newest first) are grouped by plain text similarity (TF-IDF cosine, no model) so that the same
question asked three ways counts once. ``not_english`` rows are only counted, never listed. A group has no
stored identity: its id is the id of its oldest member, found again by grouping the same rows, so dismissing,
restoring or writing an article for a group acts on every member and nothing else.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from service_desk import GAP_REASONS, GAP_TEXT_CAP
from service_desk import sanitize, store
from service_desk.retrieval import _terms        # the same content words the desk matches articles on

GROUP_THRESHOLD = 0.6           # two questions with a cosine of at least this are one group (D-26)
WINDOW = timedelta(days=90)
ROW_CAP = 500
QUESTION_CAP = 200
STATUSES = ("open", "dismissed", "written")
Similarity = Callable[[List[str]], Sequence[Sequence[float]]]


async def record(db, tenant_id: str, *, ticket_id: str, ticket_number: Optional[str], text: str, reason: str,
                 now: Optional[datetime] = None) -> bool:
    """Keep one gap row. True when this call wrote it; False when the row already existed or the question
    is empty once cleaned. A reason outside ``GAP_REASONS`` raises ValueError. Idempotent: the upsert key
    is the tenant, the ticket and the reason."""
    if reason not in GAP_REASONS:
        raise ValueError(f"not a gap reason: {reason!r}")
    question = sanitize.clean_text(text, GAP_TEXT_CAP)
    if not question:
        return False
    created = now or datetime.now(timezone.utc)
    created = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
    document = {"id": "SDG-" + uuid.uuid4().hex, "tenantId": tenant_id, "ticketId": ticket_id,
                "ticketNumber": ticket_number, "text": question, "reason": reason, "createdAt": created,
                "status": "open"}
    result = await store.gaps(db).update_one(
        {"tenantId": tenant_id, "ticketId": ticket_id, "reason": reason}, {"$setOnInsert": document}, upsert=True)
    return result.upserted_id is not None



# ---------------------------------------------------------------- grouping

def _when(row: Dict[str, Any]) -> datetime:
    """The time a row was written as an aware UTC datetime; a row without a readable time sorts oldest."""
    value = row.get("createdAt")
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            value = None
    if not isinstance(value, datetime):
        return datetime.min.replace(tzinfo=timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _words(text: str) -> List[str]:
    """The desk's content words of a question, less scikit-learn's English stop words as well ("every", "other"):
    two ways of asking the same thing share their subject, not their filler."""
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
    return [word for word in _terms(text) if word not in ENGLISH_STOP_WORDS]


def tfidf_similarity(texts: List[str]) -> List[List[float]]:
    """The pairwise TF-IDF cosine of ``texts`` over the desk's content words, as a square list. Identical
    questions always score 1, also when no content word is left to compare."""
    count = len(texts)
    sims: List[List[float]] = [[0.0] * count for _ in range(count)]
    if count > 1:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import linear_kernel
            sims = linear_kernel(TfidfVectorizer(sublinear_tf=True, analyzer=_words).fit_transform(texts)).tolist()
        except ValueError:      # an empty vocabulary: every question is only everyday words
            pass
    plain = [(text or "").strip().casefold() for text in texts]
    folded = [sanitize.normalize_for_match(text) for text in texts]
    for i in range(count):
        sims[i][i] = 1.0
        for j in range(i + 1, count):
            if plain[i] == plain[j] or (folded[i] and folded[i] == folded[j]):
                sims[i][j] = sims[j][i] = 1.0
    return sims


def group(rows: List[Dict[str, Any]], threshold: float = GROUP_THRESHOLD,
          similarity: Similarity = tfidf_similarity) -> List[List[Dict[str, Any]]]:
    """``rows`` in groups, each group newest member first. One greedy pass in createdAt-descending order (ties
    by id, descending): a row joins the first group whose seed (its first, newest, member) it scores at least
    ``threshold`` against, else starts a group. The result depends only on the rows, never on their order."""
    ordered = sorted(rows, key=lambda row: (_when(row), str(row.get("id"))), reverse=True)
    if not ordered:
        return []
    sims = similarity([str(row.get("text") or "") for row in ordered])
    members_of: List[List[int]] = []
    for i in range(len(ordered)):
        for members in members_of:
            if sims[i][members[0]] >= threshold - 1e-9:        # a score of exactly the threshold groups
                members.append(i)
                break
        else:
            members_of.append([i])
    return [[ordered[i] for i in members] for members in members_of]


def oldest_id(members: List[Dict[str, Any]]) -> str:
    """The id of the group's oldest member."""
    return str(min(members, key=lambda row: (_when(row), str(row.get("id"))))["id"])


def _shape(members: List[Dict[str, Any]], status: str) -> Dict[str, Any]:
    newest = members[0]
    return {"id": oldest_id(members), "question": str(newest.get("text") or "")[:QUESTION_CAP],
            "count": len(members), "lastAskedAt": _when(newest).isoformat(),
            "tickets": [{"id": row.get("ticketId"), "number": row.get("ticketNumber") or ""} for row in members],
            "status": status}


# ---------------------------------------------------------------- reading and changing

def _cutoff(now: Optional[datetime]) -> datetime:
    current = now or datetime.now(timezone.utc)
    return (current if current.tzinfo else current.replace(tzinfo=timezone.utc)) - WINDOW


async def _rows(db, tenant_id: str, status: str, now: Optional[datetime]) -> List[Dict[str, Any]]:
    cursor = store.gaps(db).find(
        {"tenantId": tenant_id, "reason": "no_article", "status": status, "createdAt": {"$gte": _cutoff(now)}},
        {"_id": 0}).sort([("createdAt", -1), ("id", -1)]).limit(ROW_CAP)
    return await cursor.to_list(ROW_CAP)


async def _groups(db, tenant_id: str, status: str, now: Optional[datetime]) -> List[Dict[str, Any]]:
    return [_shape(members, status) | {"_members": members} for members in group(await _rows(db, tenant_id, status, now))]


def _order(groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Most asked first, then the most recently asked, then by id: the same order on every call."""
    return sorted(groups, key=lambda g: (-g["count"], -datetime.fromisoformat(g["lastAskedAt"]).timestamp(), g["id"]))


async def list_view(db, tenant_id: str, *, include_dismissed: bool = False,
                    now: Optional[datetime] = None) -> Dict[str, Any]:
    """The gap list of one tenant: ``groups`` (open ones, plus the dismissed ones when asked), the count of
    ``not_english`` rows that were not listed and the number of dismissed groups."""
    opened = await _groups(db, tenant_id, "open", now)
    dismissed = await _groups(db, tenant_id, "dismissed", now)
    shown = opened + (dismissed if include_dismissed else [])
    other = await store.gaps(db).count_documents({"tenantId": tenant_id, "reason": "not_english", "status": "open",
                                                  "createdAt": {"$gte": _cutoff(now)}})
    return {"groups": [{k: v for k, v in g.items() if k != "_members"} for g in _order(shown)],
            "otherLanguageCount": other, "dismissedCount": len(dismissed)}


async def find_group(db, tenant_id: str, group_identifier: str,
                     now: Optional[datetime] = None) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
    """(status, member rows) of the open or dismissed group with this id, or None. A written group is gone."""
    for status in ("open", "dismissed"):
        for found in await _groups(db, tenant_id, status, now):
            if found["id"] == group_identifier:
                return status, found["_members"]
    return None


async def set_status(db, tenant_id: str, ids: List[str], status: str, *, expect: Optional[str] = None) -> int:
    """Set ``status`` on these rows of the tenant (only those now in ``expect``, when given); the number changed."""
    if status not in STATUSES:
        raise ValueError(f"not a gap status: {status!r}")
    query: Dict[str, Any] = {"tenantId": tenant_id, "id": {"$in": list(ids)}, "reason": "no_article"}
    if expect is not None:
        query["status"] = expect
    result = await store.gaps(db).update_many(query, {"$set": {"status": status}})
    return result.modified_count
