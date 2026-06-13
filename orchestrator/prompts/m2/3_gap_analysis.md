# Phase 3 — Gap_Analysis

Given the synthesis from Phase 2, identify 3-4 specific research gaps. Each gap must:

- Have a clear statement of what's missing or contested
- Cite 1-3 supporting papers (author, year, page when known)
- Be ranked by relevance to the project's research title

## How to detect a gap — the five gap types

Don't guess. Classify the reviewed literature against these five gap types, and ground each
gap you report in one of them:

| Gap type | What it is | How to detect it |
|----------|-----------|------------------|
| **Contextual** | Not yet studied in this setting / population (e.g. this country, this user group) | Filter the papers by their context (country, sector, population) and find the uncovered cell |
| **Methodological** | A method that hasn't been applied here (e.g. PLS-SEM, mixed-methods, longitudinal) | Compare the methods used across papers; spot the one nobody has tried |
| **Variable** | A construct left out of existing models — a missing mediator, moderator, or control | Inspect each paper's model; find the relationship nobody has tested |
| **Temporal** | Findings are dated; the context has since shifted (new tech, policy, behaviour) | Filter by year; flag conclusions a recent change may have invalidated |
| **Contradictory** | Paper A finds an effect, Paper B finds none | Compare reported findings; surface the unresolved disagreement |

Process: synthesise the papers → mentally tabulate them by context / method / variables / year /
key finding → run them through the five types above → keep the gaps most feasible for this
specific project → derive a candidate research question from each kept gap.

For each gap, the `description` should name its type and give the evidence (e.g. *"Contextual: none
of the 7 reviewed studies examine Vietnamese SMEs"*), and `relevance` should reflect how directly
the gap maps onto the project's research title.

Respond with ONLY a JSON array, no prose, no markdown. Schema:
```json
[
  {"id": "1", "description": "...", "relevance": "High",
   "supporting_papers": [{"author": "X", "year": 2020, "page": 12}]}
]
```

If the user has refinements (e.g., "make them methodological"), honor them.
