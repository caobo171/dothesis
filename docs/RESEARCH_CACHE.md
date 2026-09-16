# Persistent research cache

Initial research, backfill, editor source search and claim confidence reuse the
JSON cache implemented in `orchestrator/tools/research_cache.py`.

| Operation | Expiry |
| --- | --- |
| Successful provider search, keyed by provider, normalized query and result limit | 7 days |
| Parsed and shape-validated query planning, relevance and claim model output | 7 days |
| Successful DOI/title identity resolution | 30 days |

Model keys include the complete prompt, resolved model, backend, endpoint
fingerprint and temperature. Changed claims, evidence or instructions therefore
do not reuse a previous judgment. Source identity and claim support remain
separate checks. Provider limits are part of the key; searches requesting
different limits are separate entries.

The default directory is `var/cache/research`, outside project state and ignored
by Git. Set `DOTHESIS_RESEARCH_CACHE_DIR` to override it. Files persist across
process restarts. Deployments with ephemeral filesystems must mount persistent
storage; replicas need a shared filesystem supporting `flock` to share entries.

Same-key work is coalesced across threads and processes. A bounded lock timeout
raises rather than starting another paid request. Writes are atomic; directories
are private and files readable only by their owner. Cache keys are SHA-256
filenames; raw keys and credentials are not stored. Cached values can contain
thesis claims and should be treated as private application data.

Exceptions, failed identity checks, malformed model outputs and empty provider
responses are not retained. Empty provider results are deliberately retried
because some provider clients return an empty list after an upstream failure.
Unavailable cache storage falls back to one uncached computation. Disk use is
bounded to 2,048 entries, each at most 1 MiB; expired and oldest entries are
removed on writes. Removing cache JSON files forces fresh computation next time.

Regression coverage includes reuse without provider/model calls, changed-input
invalidation, independent-process persistence, concurrent request coalescing,
expiry, corruption, write failures and API integration. Cache reads never mutate
the project context store or automatically insert citations.

## Claim review time and credits

Claim review extracts every relevant claim in each saved chunk, then evaluates
retrieved evidence in batches of at most six claims. Larger sets use additional
batches; claims are never sampled away to reduce cost. Candidate ownership,
complete claim coverage and verbatim supporting quotes are validated before a
batch is accepted. Existing reviews keep their saved chunk boundaries.

Independent claim queries are fetched with at most three query workers. Source
identities are deduplicated across those results, then verified with at most
three identity workers. Authorization and database access remain in the request
coordinator; workers only perform read-only scholarly lookups. The coordinator
merges results in stable query/source order so concurrency does not invalidate
model cache keys. Model calls and chunk checkpoints remain sequential to retain
the review's credit controls and stop/resume semantics.

Complete, consistent DOI records returned by the server's OpenAlex/Crossref
search adapters can supply canonical identity directly. Claim review does not
perform a second identity lookup for those records. Incomplete records,
conflicting bibliography or other provenance still use the cached resolver.
Client-supplied provider labels are not an identity trust signal. This shortcut
only eliminates redundant metadata requests; claim support still requires the
retrieved passage and exact-quote checks.

Only model cache misses enter `api/app/claim_review_billing.py`. Each invocation
has a durable `ToolRun` receipt; actual reported token usage is priced cumulatively
per review with the existing model rate. The user debit and attributed token
ledger are settled once under database locks, before JSON parsing. Cached results
are free; malformed paid responses still consume usage. A request timeout does
not discard a later provider response's usage, and pending work blocks another
paid dispatch for that review.

The default review credit threshold is 20, editable from 1 to 500. Reaching it or
running out of credits stops the next paid call. An in-flight call can consume
more model tokens than the remaining threshold, but the debit is capped by the
threshold and available balance. The stored cost and charged amount remain
separate for accounting. Users can raise the threshold on the same paused review
and resume without discarding completed chunks. Calls made before this billing
integration are not retroactively charged.
