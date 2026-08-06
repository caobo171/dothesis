# Choosing an anchor

The anchor is the single input that decides whether this works. Everything else
in the method is downstream of it.

## Why it has to be off-distribution

An anchor works by giving the rewrite a rhythm to borrow that the model would
not have produced on its own. If the anchor is text the model was trained on,
there is nothing to borrow — the rewrite lands back on the distribution
detectors are built to recognise.

This was measured across a 12-text corpus against two independent detectors:

| Anchor source | Result |
|---|---|
| Pre-1928 public-domain prose (Russell, Mill, James, Strunk) | Works |
| A real person's own writing, idiosyncrasies and typos included | Works — the strongest |
| Wikipedia / modern CC-licensed web text | **Fails catastrophically** — scores went UP across the board |

The third row is the one worth internalising. Generic web-scraped anchors are
not "weaker", they are actively harmful, and the output still *reads* better,
which is why the failure is easy to miss.

## Getting a good one from the user

Ask for roughly 150 words they wrote **before they started using AI**. An old
essay, a report, a long message, coursework. Three properties matter:

- **Theirs.** Not a friend's, not a textbook's.
- **Old enough.** Written before AI assistance entered their workflow.
- **Same rough register.** Academic prose for a thesis; a casual message is a
  poor anchor for a formal chapter, though still better than web text.

Typos, quirks and slightly awkward constructions are **features**. Do not clean
the anchor up. The idiosyncrasies are exactly what sits outside the training
distribution.

## What not to do

- Do not generate an anchor yourself. Model output as an anchor for model output
  is a closed loop that teaches nothing.
- Do not use a famous author's recent work — recent published text is in the
  corpus, and imitating a recognisable voice is its own problem.
- Do not mix several people's writing into one anchor. The rhythm you want is
  one person's.
- Do not reuse one anchor across different registers without checking. Route the
  passage to an anchor whose register matches it.

## If they have nothing

Say plainly that the rewrite will be weaker, then use a pre-1928 public-domain
passage in a comparable register — Project Gutenberg is the obvious source.
Never silently substitute one and never present the weaker result as equivalent.
