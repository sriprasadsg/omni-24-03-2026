"""A small KQL (Kusto Query Language) subset for Advanced Hunting: tokenizer and parser.

`Table | where ... | summarize ... by ... | order by ... | take N`. The parser only builds a list of stages;
kql_engine turns them into a MongoDB pipeline over real collections. Every value is data (a string, number, time
or list of them), never code, and every name is a plain identifier, so nothing typed reaches the database as an
operator or a field path the engine did not choose.

Supported: where (==, !=, =~, !~, <, <=, >, >=, in, !in, in~, contains, has, startswith, endswith and their ! and
_cs forms, matches regex, isempty(), isnotempty(), and, or, not(), ago(), now(), datetime()), project, summarize
(count, dcount, sum, avg, min, max, make_set; by columns or bin(column, span)), order by / sort by, take / limit,
top N by, distinct, count.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Tuple

MAX_QUERY, MAX_STAGES, MAX_TERMS, MAX_LIST, MAX_TAKE = 4000, 20, 40, 50, 1000
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,40}$")
SPAN_UNITS = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400}
CMP_OPS = {"==", "!=", "=~", "!~", "<", "<=", ">", ">=", "in", "!in", "in~", "contains", "!contains",
           "contains_cs", "!contains_cs", "has", "!has", "has_cs", "startswith", "!startswith",
           "startswith_cs", "endswith", "!endswith", "endswith_cs", "matches"}
AGGS = {"count", "dcount", "sum", "avg", "min", "max", "make_set"}

_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<str>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
  | (?P<span>\d+(?:\.\d+)?(?:ms|d|h|m|s)\b)
  | (?P<num>\d+(?:\.\d+)?)
  | (?P<op>==|!=|=~|!~|<=|>=|<|>|=|\||,|\(|\))
  | (?P<word>!?[A-Za-z_][A-Za-z0-9_]*(?:-[a-z]+)?~?)
""", re.VERBOSE)


class KqlError(ValueError):
    """A query the engine will not run; the message is shown to the analyst as is."""


def tokenize(text: str) -> List[Tuple[str, Any]]:
    if len(text) > MAX_QUERY:
        raise KqlError(f"A query can be at most {MAX_QUERY} characters")
    out, pos = [], 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise KqlError(f"Unexpected character {text[pos]!r} at position {pos + 1}")
        kind, value = m.lastgroup, m.group()
        pos = m.end()
        if kind == "ws":
            continue
        if kind == "str":
            value = re.sub(r"\\(.)", r"\1", value[1:-1])
        elif kind == "num":
            value = float(value) if "." in value else int(value)
        elif kind == "span":
            unit = "ms" if value.endswith("ms") else value[-1]
            value = timedelta(seconds=float(value[: -len(unit)]) * SPAN_UNITS[unit])
        out.append((kind, value))
    return out


class _Parser:
    def __init__(self, tokens: List[Tuple[str, Any]], now: datetime):
        self.t, self.i, self.now, self.terms = tokens, 0, now, 0

    def peek(self, offset: int = 0) -> Tuple[Optional[str], Any]:
        j = self.i + offset
        return self.t[j] if j < len(self.t) else (None, None)

    def take(self) -> Tuple[Optional[str], Any]:
        tok = self.peek()
        self.i += 1
        return tok

    def word(self, *expected: str) -> str:
        kind, value = self.take()
        if kind != "word" or (expected and str(value).lower() not in expected):
            want = " or ".join(expected) if expected else "a name"
            raise KqlError(f"Expected {want}, found {value if value is not None else 'the end of the query'}")
        return str(value)

    def is_word(self, *names: str) -> bool:
        kind, value = self.peek()
        return kind == "word" and str(value).lower() in names

    def expect(self, op: str) -> None:
        kind, value = self.take()
        if kind != "op" or value != op:
            raise KqlError(f"Expected '{op}', found {value if value is not None else 'the end of the query'}")

    def is_op(self, op: str) -> bool:
        return self.peek() == ("op", op)

    def name(self) -> str:
        n = self.word()
        if not NAME.match(n):
            raise KqlError(f"{n!r} is not a column name")
        return n

    # -- values -------------------------------------------------------------------------------------------------

    def value(self) -> Tuple[str, Any]:
        kind, v = self.take()
        if kind == "str":
            return ("str", v)
        if kind == "num":
            return ("num", v)
        if kind == "word" and str(v).lower() in ("true", "false"):
            return ("bool", str(v).lower() == "true")
        if kind == "word" and str(v).lower() in ("ago", "now", "datetime"):
            fn = str(v).lower()
            self.expect("(")
            if fn == "ago":
                k, span = self.take()
                if k != "span":
                    raise KqlError("ago() takes a time span such as 1h, 30m or 7d")
                out = self.now - span
            elif fn == "now":
                out = self.now
            else:
                k, s = self.take()
                if k != "str":
                    raise KqlError('datetime() takes a quoted date, for example datetime("2026-11-19T10:00:00Z")')
                try:
                    out = datetime.fromisoformat(s.replace("Z", "+00:00"))
                except ValueError:
                    raise KqlError(f"{s!r} is not a date")
                out = out if out.tzinfo else out.replace(tzinfo=timezone.utc)
            self.expect(")")
            return ("time", out)
        raise KqlError(f"Expected a value, found {v if v is not None else 'the end of the query'}")

    def value_list(self) -> Tuple[str, Any]:
        self.expect("(")
        items = [self.value()]
        while self.is_op(","):
            self.take()
            items.append(self.value())
        self.expect(")")
        if len(items) > MAX_LIST:
            raise KqlError(f"A list takes at most {MAX_LIST} values")
        return ("list", items)

    # -- where expressions ----------------------------------------------------------------------------------

    def expr(self):
        parts = [self.and_expr()]
        while self.is_word("or"):
            self.take()
            parts.append(self.and_expr())
        return parts[0] if len(parts) == 1 else ("or", parts)

    def and_expr(self):
        parts = [self.not_expr()]
        while self.is_word("and"):
            self.take()
            parts.append(self.not_expr())
        return parts[0] if len(parts) == 1 else ("and", parts)

    def not_expr(self):
        if self.is_word("not") and self.peek(1) == ("op", "("):
            self.take(); self.take()
            inner = self.expr()
            self.expect(")")
            return ("not", inner)
        if self.is_op("("):
            self.take()
            inner = self.expr()
            self.expect(")")
            return inner
        return self.comparison()

    def comparison(self):
        self.terms += 1
        if self.terms > MAX_TERMS:
            raise KqlError(f"A query takes at most {MAX_TERMS} conditions")
        if self.is_word("isempty", "isnotempty") and self.peek(1) == ("op", "("):
            fn = self.word().lower()
            self.expect("(")
            col = self.name()
            self.expect(")")
            return ("fn", fn, col)
        col = self.name()
        _, op = self.take()
        op = str(op).lower() if op is not None else None
        if op not in CMP_OPS:
            raise KqlError(f"Expected a comparison after {col} (==, !=, contains, in, ...), found {op or 'the end of the query'}")
        if op == "matches":
            self.word("regex")
            val = self.value()
        elif op in ("in", "!in", "in~"):
            val = self.value_list()
        else:
            val = self.value()
        return ("cmp", col, op, val)

    # -- stages ---------------------------------------------------------------------------------------------

    def columns(self) -> List[Tuple[str, str]]:
        cols = [self.project_item()]
        while self.is_op(","):
            self.take()
            cols.append(self.project_item())
        return cols

    def project_item(self) -> Tuple[str, str]:
        first = self.name()
        if self.is_op("="):
            self.take()
            return (first, self.name())
        return (first, first)

    def aggregate(self) -> Tuple[Optional[str], str, Optional[str]]:
        alias = None
        if self.peek(1) == ("op", "="):
            alias = self.name()
            self.take()
        fn = self.word().lower()
        if fn not in AGGS:
            raise KqlError(f"summarize supports {', '.join(sorted(AGGS))}(), not {fn}()")
        self.expect("(")
        col = None
        if not self.is_op(")"):
            col = self.name()
        self.expect(")")
        if fn != "count" and col is None:
            raise KqlError(f"{fn}() needs a column")
        return (alias, fn, col)

    def group_key(self) -> Tuple[str, str, str, Optional[timedelta]]:
        if self.is_word("bin") and self.peek(1) == ("op", "("):
            self.take(); self.take()
            col = self.name()
            self.expect(",")
            kind, span = self.take()
            if kind != "span":
                raise KqlError("bin() takes a column and a time span, for example bin(TimeGenerated, 1h)")
            self.expect(")")
            return (col, "bin", col, span)
        alias, col = self.project_item()
        return (alias, "col", col, None)

    def sort_keys(self) -> List[Tuple[str, bool]]:
        keys = []
        while True:
            col = self.name()
            desc = True
            if self.is_word("asc", "desc"):
                desc = self.word().lower() == "desc"
            keys.append((col, desc))
            if not self.is_op(","):
                return keys
            self.take()

    def count_n(self) -> int:
        kind, n = self.take()
        if kind != "num" or not isinstance(n, int) or n < 1:
            raise KqlError("Expected a whole number of rows")
        return min(n, MAX_TAKE)

    def stage(self) -> dict:
        op = self.word().lower()
        if op == "where":
            return {"op": "where", "expr": self.expr()}
        if op == "project":
            return {"op": "project", "cols": self.columns()}
        if op == "summarize":
            aggs = [self.aggregate()]
            while self.is_op(","):
                self.take()
                aggs.append(self.aggregate())
            by = []
            if self.is_word("by"):
                self.take()
                by.append(self.group_key())
                while self.is_op(","):
                    self.take()
                    by.append(self.group_key())
            return {"op": "summarize", "aggs": aggs, "by": by}
        if op in ("order", "sort"):
            self.word("by")
            return {"op": "sort", "keys": self.sort_keys()}
        if op in ("take", "limit"):
            return {"op": "take", "n": self.count_n()}
        if op == "top":
            n = self.count_n()
            self.word("by")
            return {"op": "top", "n": n, "keys": self.sort_keys()[:1]}
        if op == "distinct":
            return {"op": "distinct", "cols": self.columns()}
        if op == "count":
            return {"op": "count"}
        raise KqlError(f"Unsupported operator {op!r}; use where, project, summarize, order by, take, top, distinct or count")


def parse(text: str, now: Optional[datetime] = None) -> Tuple[str, List[dict]]:
    """The table name and the stages of a query (raises KqlError)."""
    p = _Parser(tokenize(text or ""), now or datetime.now(timezone.utc))
    if p.peek() == (None, None):
        raise KqlError("Write a query that starts with a table, for example SecurityEvent | take 10")
    table = p.name()
    stages = []
    while p.is_op("|"):
        p.take()
        stages.append(p.stage())
        if len(stages) > MAX_STAGES:
            raise KqlError(f"A query takes at most {MAX_STAGES} operators")
    if p.peek() != (None, None):
        raise KqlError(f"Unexpected {p.peek()[1]!r}; separate operators with |")
    return table, stages
