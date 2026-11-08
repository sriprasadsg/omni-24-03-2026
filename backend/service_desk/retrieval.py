"""Finding the tenant's own Help desk article for a ticket (D-16, D-17, D-18).

Candidates are the tenant's own articles marked ``helpdesk`` and nothing else: an article with
tenantId ``global`` or another tenant's id, or with ``helpdesk`` not True, is never read here. The
score is the mean of two TF-IDF cosines fitted per call on the tenant's few articles (the question
against the whole article, and against its title and tags). An answer is attempted only when the best
article scores at least CUT AND shares at least MIN_TERMS distinct content words with the ticket
(``gate_score``). The cut-off is a retrieval score, never the model's confidence: this module imports
neither the model nor any setting, and a tenant cannot change CUT, MIN_TERMS or MARGIN_FLOOR (D-18).

Re-pinned in plan 85-06 on the four real starter articles of ``service_desk.starters`` with
tests/fixtures/service_desk/retrieval_set.jsonl (48 questions that must match, 50 that must not):

* lowest gate score of a match   0.3528  ("Where is the My tickets menu of the IT support agent")
* highest gate score of a non-match 0.1260  ("My home network is slow and video calls freeze")
* margin 0.2268; CUT is in the middle of that gap (0.2394 -> 0.24) and MARGIN_FLOOR sits just below it.

A question that shares only one word with an article is stopped by MIN_TERMS alone (its raw score can
be as high as 0.56, "the Wi-Fi guest password for visitors"), and a question that names the subject of an
article without being answered by it ("order new toner for the office printer") passes the cut-off by
design: whether the article really answers is the model's cite-none reply and the D-19 checks. A
retune of any constant, of the stop words or of the stemmer shows up as a failing margin test.
Pure apart from ``candidates``; no model is involved.
"""
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from autonomous_ops.scope import raw

from . import ARTICLE_TEXT_CAP, MAX_CANDIDATES, MAX_CITED
from .sanitize import normalize_for_match

logger = logging.getLogger(__name__)

CUT = 0.24
MIN_TERMS = 2
MARGIN_FLOOR = 0.22

# Words that carry no topic. The second line is the vocabulary of every ticket and every starter article
# ("I need help", "raise a ticket for my company"): sharing one of them says nothing about the subject.
_STOP = frozenset((
    "a about above after again against all am an and any are as at be because been before being below between "
    "both but by can could did do does doing down during each few for from further had has have having he her "
    "here hers him his how i if in into is it its itself just me more most my myself no nor not of off on once "
    "only or other our ours out over own same she should so some such than that the their theirs them then "
    "there these they this those through to too under until up very was we were what when where which while "
    "who whom why will with would you your yours yourself also get got let may might must now one see shall "
    "us way yes well still even much many".split()))
_GENERIC = frozenset((
    "help need needs needed please issue issues problem problems ticket tickets raise raised company companys "
    "work working works support hi hello thanks thank request question trouble able unable cannot cant dont "
    "doesnt wont isnt arent didnt like want wants try tried trying make use using used new old again tell "
    "sometimes always never really keep keeps kept show shows showed shown come comes came turn turns fix fixed "
    "say says said look looks go goes going give gives take takes put puts find finds".split()))
_STOPPED = _STOP | _GENERIC


@dataclass
class Match:
    id: str
    title: str
    content: str
    content_hash: str
    score: float
    terms: List[str] = field(default_factory=list)


def _stem(word: str) -> str:
    """Light suffix stripping: -ing, -ed, -es (after s, x, z, ch, sh) and -s for words longer than 4 letters,
    one doubled final consonant undone ("stopped" -> "stop"), then a trailing e dropped so that "use",
    "using" and "used" meet."""
    if len(word) > 4:
        for suffix in ("ing", "ed"):
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                word = word[:-len(suffix)]
                if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "aeioulszf":
                    word = word[:-1]
                break
        else:
            if word.endswith("es") and word[:-2].endswith(("s", "x", "z", "ch", "sh")):
                word = word[:-2]
            elif word.endswith("s") and not word.endswith("ss"):
                word = word[:-1]
    if len(word) > 3 and word.endswith("e"):
        word = word[:-1]
    return word


def _terms(text: Any) -> List[str]:
    """The content words of ``text``, in order. Folded by ``sanitize.normalize_for_match`` (the form the fixed
    rules match in, so "Wi-Fi" and "wifi" meet and the two layers cannot disagree), then stop words removed
    and the rest lightly stemmed."""
    out = []
    for token in normalize_for_match(text).split():
        if len(token) < 2 or token in _STOPPED:
            continue
        stem = _stem(token)
        if len(stem) >= 2 and stem not in _STOPPED:
            out.append(stem)
    return out


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
    return " ".join([title, title, title, _tags(doc), content[:ARTICLE_TEXT_CAP]])


def _tags(doc: Dict[str, Any]) -> str:
    tags = doc.get("tags") if isinstance(doc.get("tags"), list) else []
    return " ".join(t for t in tags if isinstance(t, str))


def _topic(doc: Dict[str, Any]) -> str:
    """What the article is about: its title and tags only."""
    title = doc.get("title") if isinstance(doc.get("title"), str) else ""
    return title + " " + _tags(doc)


def score(question: str, docs: List[Dict[str, Any]]) -> List[Match]:
    """Every doc scored against the question, best first. Empty when nothing can be scored.

    The score is the mean of two TF-IDF cosines, each fitted on the tenant's own articles: the question
    against the whole article text, and against its title and tags alone. A short question always scores
    low against a long article (the full-text cosine of "my VPN keeps dropping" is about 0.23), and a
    question about another subject that shares a few everyday words ("my home network is slow") scores
    about the same; the title and tags are what separate them, because they name the subject."""
    docs = [d for d in docs if isinstance(d, dict) and isinstance(d.get("id"), str)]
    if not docs or not isinstance(question, str):
        return []
    asked = set(_terms(question))
    if not asked:
        return []
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import linear_kernel
    texts = [_text(d) for d in docs]
    try:
        whole = TfidfVectorizer(sublinear_tf=True, analyzer=_terms)
        whole_matrix = whole.fit_transform(texts)
        whole_sims = linear_kernel(whole.transform([question]), whole_matrix)[0]
    except ValueError:      # an empty vocabulary: nothing to compare
        return []
    try:
        topic = TfidfVectorizer(sublinear_tf=True, analyzer=_terms)
        topic_matrix = topic.fit_transform([_topic(d) for d in docs])
        topic_sims = linear_kernel(topic.transform([question]), topic_matrix)[0]
    except ValueError:      # no article has a title or tag worth a word
        topic_sims = [0.0] * len(docs)
    matches = []
    for doc, text, whole_sim, topic_sim in zip(docs, texts, whole_sims, topic_sims):
        content = doc.get("content") if isinstance(doc.get("content"), str) else ""
        matches.append(Match(
            id=doc["id"], title=doc.get("title") if isinstance(doc.get("title"), str) else "", content=content,
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest()[:16],
            score=(float(whole_sim) + float(topic_sim)) / 2, terms=sorted(asked & set(_terms(text)))))
    matches.sort(key=lambda m: (-m.score, m.id))
    return matches


def gate_score(match: Match) -> float:
    """The score an article counts with: its retrieval score when it shares at least MIN_TERMS words with the
    question, else 0. This is the one number CUT is compared with, and the one the tests keep apart."""
    return match.score if len(match.terms) >= MIN_TERMS else 0.0


def select(matches: List[Match]) -> List[Match]:
    """The articles to answer from, or [] when none is close enough: the best must reach CUT with at least
    MIN_TERMS shared words; up to MAX_CITED more qualify at half the best score or CUT."""
    able = [m for m in matches if gate_score(m) >= CUT]
    if not able:
        return []
    floor = max(CUT, 0.5 * able[0].score)
    return [m for m in able if m.score >= floor][:MAX_CITED]
