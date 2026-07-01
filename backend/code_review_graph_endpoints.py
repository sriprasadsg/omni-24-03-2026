"""Code Review Graph — FastAPI endpoints.

Bridges the enterprise platform to the code-review-graph Python library
(stored in code-review-graph-main/) so the frontend dashboard can trigger
graph builds, run change-impact analysis, and search code entities without
running a separate MCP stdio process.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from authentication_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/code-review", tags=["Code Review Graph"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class BuildRequest(BaseModel):
    repo_root: str
    full_rebuild: bool = False


class AnalyzeRequest(BaseModel):
    repo_root: str
    changed_files: Optional[List[str]] = None
    base: str = "HEAD~1"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/graph/stats")
async def get_graph_stats(
    repo_root: str = Query(..., description="Absolute path to the repository root"),
    current_user=Depends(get_current_user),
):
    """Return node/edge counts and language breakdown for the graph."""
    try:
        from code_review_graph.tools import list_graph_stats
        result = await asyncio.to_thread(list_graph_stats, repo_root)
        return result
    except Exception as exc:
        logger.warning("code-review-graph stats error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/graph/build")
async def build_graph(req: BuildRequest, current_user=Depends(get_current_user)):
    """Build or incrementally update the code review graph for a repository."""
    try:
        from code_review_graph.tools import build_or_update_graph
        result = await asyncio.to_thread(
            build_or_update_graph,
            full_rebuild=req.full_rebuild,
            repo_root=req.repo_root,
        )
        return result
    except Exception as exc:
        logger.warning("code-review-graph build error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/graph/analyze")
async def analyze_changes(req: AnalyzeRequest, current_user=Depends(get_current_user)):
    """Risk-score the impact of changed files using the code review graph."""
    try:
        from code_review_graph.tools import detect_changes_func
        result = await asyncio.to_thread(
            detect_changes_func,
            base=req.base,
            changed_files=req.changed_files,
            repo_root=req.repo_root,
        )
        return result
    except Exception as exc:
        logger.warning("code-review-graph analyze error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/graph/search")
async def search_graph(
    query: str = Query(..., description="Search term"),
    repo_root: str = Query(..., description="Absolute path to the repository root"),
    kind: Optional[str] = Query(None, description="Node kind: File, Class, Function, Type, Test"),
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    """Search code entities by name or keyword."""
    try:
        from code_review_graph.tools import semantic_search_nodes
        result = await asyncio.to_thread(
            semantic_search_nodes,
            query=query,
            kind=kind,
            limit=limit,
            repo_root=repo_root,
        )
        return result
    except Exception as exc:
        logger.warning("code-review-graph search error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/graph/context")
async def get_context(
    repo_root: str = Query(..., description="Absolute path to the repository root"),
    task: str = Query("", description="Task description for AI context"),
    current_user=Depends(get_current_user),
):
    """Return an ultra-compact (~100 token) codebase summary for AI assistants."""
    try:
        from code_review_graph.tools import get_minimal_context
        result = await asyncio.to_thread(
            get_minimal_context,
            task=task,
            repo_root=repo_root,
        )
        return result
    except Exception as exc:
        logger.warning("code-review-graph context error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")
