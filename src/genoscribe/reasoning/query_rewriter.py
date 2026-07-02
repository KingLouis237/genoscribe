from __future__ import annotations

from typing import Optional


class QueryRewriter:
    """Deterministic query rewriter that injects mode context."""

    def rewrite(self, query: str, mode: Optional[str] = None) -> str:
        if not mode:
            return query
        return f"[{mode}] {query}" if not query.lower().startswith(f"[{mode}") else query


__all__ = ["QueryRewriter"]
