"""PageSizeCapMiddleware (Phase 86 review WR-02): it runs before authentication on every route, so a
crafted page size must never raise there, and no spelling of a big number may slip past the cap."""
from urllib.parse import parse_qsl

import pytest

from app_middleware import MAX_PAGE_SIZE, PageSizeCapMiddleware


async def _forwarded_query(query: bytes) -> dict:
    seen = {}

    async def app(scope, receive, send):
        seen.update(parse_qsl(scope["query_string"].decode("latin-1"), keep_blank_values=True))

    await PageSizeCapMiddleware(app)({"type": "http", "query_string": query}, None, None)
    return seen


@pytest.mark.parametrize("query, expected", [
    (b"limit=%C2%B2", "²"),
    (b"limit=abc", "abc"),
    (b"limit=", ""),
    (b"limit=5", "5"),
    (b"limit=-1", "-1"),
])
async def test_a_value_the_cap_does_not_apply_to_passes_through_untouched(query, expected):
    assert (await _forwarded_query(query))["limit"] == expected


@pytest.mark.parametrize("query", [
    b"limit=999999",
    b"page_size=%20999999%20",
    b"per_page=%2B999999",
    b"pageSize=%EF%BC%99%EF%BC%99%EF%BC%99%EF%BC%99%EF%BC%99",  # full-width digits, which int() reads
])
async def test_every_spelling_of_a_big_number_is_capped(query):
    assert list((await _forwarded_query(query)).values()) == [str(MAX_PAGE_SIZE)]


async def test_other_parameters_are_left_alone():
    assert await _forwarded_query(b"q=999999&limit=10") == {"q": "999999", "limit": "10"}
