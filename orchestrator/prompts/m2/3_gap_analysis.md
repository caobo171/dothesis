# Phase 3 — Gap_Analysis

Given the synthesis from Phase 2, identify 3-4 specific research gaps. Each gap must:

- Have a clear statement of what's missing or contested
- Cite 1-3 supporting papers (author, year, page when known)
- Be ranked by relevance to the project's research title

Respond with ONLY a JSON array, no prose, no markdown. Schema:
```json
[
  {"id": "1", "description": "...", "relevance": "High",
   "supporting_papers": [{"author": "X", "year": 2020, "page": 12}]}
]
```

If the user has refinements (e.g., "make them methodological"), honor them.
