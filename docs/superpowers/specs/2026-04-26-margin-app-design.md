# Margin App — Design Spec

**Date:** 2026-04-26
**Status:** Draft
**Project:** Margin — Academic writing workspace with AI Humanizer and Auto-Cite

---

## 1. Overview

Margin is a separate full-stack web application for academic writing assistance. Two core features at launch:

1. **Humanizer** — Rewrites AI-generated text to sound human, with tone/strength controls and diff highlighting
2. **Auto-Cite** — Scans essays for unsupported claims, finds academic sources from CrossRef/OpenAlex/Semantic Scholar, and builds a managed bibliography

Additional feature at launch: **Plagiarism Check** via Copyscape API. More tools planned for future releases.

**Target users:** Students writing essays, lab reports, theses.

---

## 2. Architecture

Monorepo, single Express backend + Next.js frontend. Mirrors Survify's patterns.

```
margin/
├── margin-backend/          # Express.js + TypeScript (port 8001)
├── margin-frontend/         # Next.js 14 App Router (port 8002)
└── docker/
    └── docker-compose.yml   # MongoDB + Redis
```

### Tech Stack

| Layer       | Technology                                          |
|-------------|-----------------------------------------------------|
| Frontend    | Next.js 14+, React 19, Tailwind CSS, Redux Toolkit, SWR |
| Backend     | Express.js, TypeScript, Typegoose/Mongoose          |
| Database    | MongoDB 6.0                                         |
| Cache/Queue | Redis + Bull                                        |
| Auth        | Passport.js (JWT, Local, Google OAuth)               |
| Real-time   | Socket.io (auto-cite progress), SSE (humanizer streaming) |
| Storage     | AWS S3 + CloudFront                                  |
| Payments    | Stripe, PayPal, LemonSqueezy                         |
| AI          | OpenAI (primary), Claude (fallback)                  |

---

## 3. Data Models

### User

| Field             | Type    | Notes                              |
|-------------------|---------|------------------------------------|
| username          | String  | Required                           |
| email             | String  | Required, unique                   |
| password          | String  | Required, bcrypt hashed            |
| googleId          | String  | Nullable, for Google OAuth         |
| emailVerified     | Boolean | Default false                      |
| verificationToken | String  | Nullable                           |
| credit            | Number  | Default 0, current balance         |
| plan              | String  | "free" / "student" / "pro"         |
| role              | String  | "User" / "Admin"                   |
| version           | String  | App version tracker                |

### Credit

| Field       | Type   | Notes                                      |
|-------------|--------|--------------------------------------------|
| amount      | Number | Credit amount                              |
| direction   | String | "inbound" / "outbound"                     |
| owner       | String | User ID                                    |
| status      | String | "pending" / "completed" / "failed"         |
| description | String | Human-readable reason                      |
| orderType   | String | "humanize" / "autocite" / "plagiarism" etc |
| orderId     | String | Reference to the job that consumed credits |

### Document

| Field      | Type   | Notes                                  |
|------------|--------|----------------------------------------|
| owner      | String | User ID                                |
| title      | String | Filename or extracted title             |
| content    | String | Extracted plain text                   |
| sourceType | String | "paste" / "upload" / "url"             |
| sourceUrl  | String | Nullable, for URL imports              |
| fileKey    | String | Nullable, S3 key for uploaded files    |
| mimeType   | String | "text/plain", "application/pdf", etc   |
| wordCount  | Number | Computed on save                       |

### HumanizeJob

| Field        | Type   | Notes                                  |
|--------------|--------|----------------------------------------|
| owner        | String | User ID                                |
| documentId   | String | Reference to Document                  |
| inputText    | String | Original text                          |
| outputHtml   | String | Rewritten text with diff markup        |
| outputText   | String | Rewritten plain text                   |
| tone         | String | "academic" / "casual" / "persuasive"   |
| strength     | Number | 0-100                                  |
| lengthMode   | String | "match" / "shorter" / "longer"         |
| aiScoreIn    | Number | AI detection score of input (0-100)    |
| aiScoreOut   | Number | AI detection score of output (0-100)   |
| changesCount | Number | Number of phrases rewritten            |
| creditsUsed  | Number | Credits consumed                       |
| status       | String | "processing" / "completed" / "failed"  |

### Citation

| Field         | Type   | Notes                                       |
|---------------|--------|---------------------------------------------|
| owner         | String | User ID                                     |
| folderId      | String | Nullable, reference to CitationFolder       |
| style         | String | "apa" / "mla" / "chicago" / "harvard" / "ieee" |
| formattedText | String | The full formatted citation string (HTML)   |
| author        | String | Author name(s)                              |
| year          | Number | Publication year                            |
| title         | String | Work title                                  |
| journal       | String | Nullable                                    |
| doi           | String | Nullable                                    |
| url           | String | Nullable                                    |
| sourceApi     | String | "crossref" / "openalex" / "semanticscholar" |

### CitationFolder

| Field | Type   | Notes              |
|-------|--------|--------------------|
| owner | String | User ID            |
| name  | String | Folder display name|
| color | String | Hex color code     |

### AutoCiteJob

| Field      | Type   | Notes                                           |
|------------|--------|-------------------------------------------------|
| owner      | String | User ID                                         |
| documentId | String | Reference to Document                           |
| style      | String | Citation style                                  |
| status     | String | "pending" / "extracting" / "searching" / "matching" / "formatting" / "done" / "failed" |
| claims     | Array  | `[{ text, sourceId, status, candidates[] }]`    |
| sources    | Array  | `[{ id, cite, authorShort, year, title, snippet, conf, sourceApi }]` |
| creditsUsed| Number | Credits consumed                                |

**claims[] item:**

| Field      | Type   | Notes                                    |
|------------|--------|------------------------------------------|
| text       | String | The claim text extracted from essay       |
| sourceId   | String | Nullable, accepted source ID             |
| status     | String | "pending" / "cited" / "skipped"          |
| candidates | Array  | `[{ sourceId, relevanceScore }]`         |

### PlagiarismJob

| Field        | Type   | Notes                                         |
|--------------|--------|-----------------------------------------------|
| owner        | String | User ID                                       |
| documentId   | String | Reference to Document                         |
| overallScore | Number | 0-100 similarity percentage                   |
| status       | String | "pending" / "processing" / "done" / "failed"  |
| matches      | Array  | `[{ sourceTitle, sourceUrl, similarity, matchedText, severity }]` (severity: "high" >= 80%, "medium" >= 40%, "low" < 40%) |
| creditsUsed  | Number | Credits consumed                              |

---

## 4. API Endpoints

### Auth

| Method | Endpoint               | Description            |
|--------|------------------------|------------------------|
| POST   | /api/auth/register     | Email/password signup  |
| POST   | /api/auth/login        | Email/password login   |
| POST   | /api/auth/google       | Google OAuth           |
| GET    | /api/me                | Current user profile   |

### Humanizer

| Method | Endpoint                  | Description                          | Delivery    |
|--------|---------------------------|--------------------------------------|-------------|
| POST   | /api/humanize/run         | Rewrite text, stream result          | SSE         |
| POST   | /api/humanize/check-score | Get AI detection score               | REST        |
| GET    | /api/humanize/history     | List past HumanizeJobs               | REST + SWR  |
| GET    | /api/humanize/:id         | Get single job detail                | REST        |

### Auto-Cite

| Method | Endpoint                  | Description                          | Delivery         |
|--------|---------------------------|--------------------------------------|------------------|
| POST   | /api/cite/analyze         | Submit essay for analysis            | Bull + Socket.io |
| POST   | /api/cite/accept          | Accept a source for a claim          | REST             |
| POST   | /api/cite/remove          | Remove citation from a claim         | REST             |
| POST   | /api/cite/reformat        | Change citation style                | REST             |
| POST   | /api/cite/export          | Export bibliography (docx/bib/txt)   | REST (download)  |
| GET    | /api/cite/:id             | Get job status and results           | REST             |

### Plagiarism

| Method | Endpoint                  | Description                          | Delivery         |
|--------|---------------------------|--------------------------------------|------------------|
| POST   | /api/plagiarism/check     | Submit essay for plagiarism check    | Bull + Socket.io |
| GET    | /api/plagiarism/:id       | Get results                          | REST             |

### Document

| Method | Endpoint                  | Description                          |
|--------|---------------------------|--------------------------------------|
| POST   | /api/document/upload      | Upload file (multipart → S3)         |
| POST   | /api/document/import-url  | Scrape URL with Cheerio              |
| GET    | /api/document/list        | List user's documents                |
| GET    | /api/document/:id         | Get document content                 |

### Library

| Method | Endpoint                    | Description                        |
|--------|-----------------------------|------------------------------------|
| GET    | /api/library/folders        | List folders                       |
| POST   | /api/library/folders        | Create folder                      |
| PUT    | /api/library/folders/:id    | Update folder                      |
| DELETE | /api/library/folders/:id    | Delete folder                      |
| GET    | /api/library/citations      | List citations (filter by folder)  |
| POST   | /api/library/citations      | Save citation                      |
| PUT    | /api/library/citations/:id  | Update citation                    |
| DELETE | /api/library/citations/:id  | Delete citation                    |
| POST   | /api/library/export         | Export folder as bibliography       |

### Credits

| Method | Endpoint                  | Description                          |
|--------|---------------------------|--------------------------------------|
| GET    | /api/credit/balance       | Current credit balance               |
| GET    | /api/credit/history       | Credit transaction history           |
| POST   | /api/credit/purchase      | Create Stripe checkout session       |
| POST   | /api/webhook/stripe       | Stripe webhook handler               |

---

## 5. AI & External Services

### AI Provider Strategy

`AIServiceManager` with primary/fallback pattern (from Survify):

- **Primary:** OpenAI `gpt-4o`
- **Fallback:** Claude `claude-sonnet-4-20250514`

### Humanizer Prompts

Three parameters from UI control the system prompt:

- **Tone** (academic / casual / persuasive) — sets writing style instructions
- **Strength** (0-100%) — low = light edits to obvious AI phrases, high = full rewrite
- **Length** (match / -15% / +15%) — instruction to maintain, shorten, or expand

**Response format:** Structured JSON `{ rewrittenText, changes: [{ original, replacement, reason }] }`. Frontend renders diff highlighting from this.

### AI Detection Score

Prompt the LLM to score 0-100 how likely text is AI-generated. Future: integrate GPTZero or Originality.ai API for more robust scoring.

### Citation Search Pipeline

For each claim the LLM extracts:

1. **CrossRef** — `api.crossref.org/works?query=...` (free, no key, rate-limited)
2. **OpenAlex** — `api.openalex.org/works?search=...` (free, generous limits)
3. **Semantic Scholar** — `api.semanticscholar.org/graph/v1/paper/search?query=...` (free, API key for higher rate)

All three queried in parallel. Results merged, deduplicated by DOI. LLM ranks top 3 candidates per claim. Citation formatted by LLM with style-specific prompts (APA 7, MLA 9, Chicago, Harvard, IEEE).

### Plagiarism

Copyscape Premium API (`api.copyscape.com`) — pay-per-search, returns matched URLs + similarity percentages + matched text excerpts.

### URL Scraping

Cheerio-based (already used in Survify): fetch HTML → extract `<article>`, `<main>`, or largest text block → strip nav/ads/scripts → return clean text + title + word count.

### File Parsing

- **docx** — `mammoth` library (converts to HTML/text)
- **pdf** — `pdf-parse` library (extracts text)
- **txt/md** — read directly

---

## 6. Frontend Architecture

### Design System

CSS variables from the HTML mockup mapped to Tailwind config:

| Variable       | Value     | Tailwind Name |
|----------------|-----------|---------------|
| --bg           | #FFFFFF   | bg-white      |
| --bg-soft      | #F7F8FC   | bg-soft       |
| --bg-blue      | #F0F3FF   | bg-blue       |
| --bg-purple    | #F4F0FF   | bg-purple     |
| --primary      | #0022FF   | primary       |
| --primary-dark | #001ACC   | primary-dark  |
| --purple       | #6633FF   | purple        |
| --success      | #00B383   | success       |
| --warn         | #E89C2C   | warn          |
| --error        | #E84C5A   | error         |
| --ink          | #0A0E27   | ink           |
| --ink-soft     | #3F4566   | ink-soft      |
| --ink-muted    | #8B91A8   | ink-muted     |
| --rule         | #ECEDF3   | rule          |
| --rule-strong  | #D8DAE5   | rule-strong   |

**Fonts:** Instrument Serif (headings), DM Sans (body), JetBrains Mono (code/stats)

### Routes

| Route         | View        | Description                            |
|---------------|-------------|----------------------------------------|
| /humanizer    | Humanizer   | Default landing, AI text rewriter      |
| /auto-cite    | Auto-Cite   | Citation finder + plagiarism tab       |
| /library      | Library     | Citation folders and saved citations   |
| /history      | History     | Past humanize runs                     |

### Layout

`(workspace)/layout.tsx` — persistent sidebar (256px) + topbar (58px). Child routes render in main area.

`(auth)/` — login/register pages, no sidebar.

### Key Components

| Component       | Location              | Responsibility                                  |
|-----------------|-----------------------|-------------------------------------------------|
| Sidebar         | components/layout/    | Nav items, recent docs, usage bar, user avatar  |
| Topbar          | components/layout/    | Breadcrumb, credit pill, help/feedback buttons  |
| HumBoard        | components/humanizer/ | Toolbar + split pane + footer, main humanizer UI|
| HumToolbar      | components/humanizer/ | Tone pills, strength slider, length toggle      |
| InputPane       | components/humanizer/ | Tabbed: paste / upload (DropZone) / URL import  |
| OutputPane      | components/humanizer/ | Diff-highlighted rewritten text, AI score meter |
| InsightCards    | components/humanizer/ | 4 stat cards (avg score, rewrites, grade, pass) |
| CiteBoard       | components/cite/      | Empty → loading → review states                |
| ClaimPopover    | components/cite/      | Click claim → candidate picker or cited info    |
| SourceList      | components/cite/      | Bibliography panel, hover highlights, remove    |
| PlagiarismView  | components/cite/      | Score circle + match list + actions             |
| FolderSidebar   | components/library/   | Folder list with colors and counts              |
| CitationRow     | components/library/   | Single citation in library list                 |
| DropZone        | components/common/    | Drag & drop file upload with format badges      |
| FileCard        | components/common/    | Uploaded file preview with replace button       |
| UrlImport       | components/common/    | URL input + fetch button + preview              |
| AiMeter         | components/ui/        | AI score bar with color coding                  |
| CreditPill      | components/ui/        | Credit count badge in topbar                    |
| Toast           | components/ui/        | Bottom-center notification                      |

### State Management

- **Redux slices:** `authSlice`, `creditSlice`, `humanizerSlice`, `autoCiteSlice`, `librarySlice`
- **SWR:** history list, library citations, credit balance, document list
- **Local state:** popover position, active tone/length pills, slider drag, input source tab

### Real-time

- **Humanizer:** SSE via `EventSource` — stream tokens into output pane as LLM generates
- **Auto-Cite:** Socket.io — emit step progress events, update loading UI in real-time
- **Plagiarism:** Socket.io — same pattern as auto-cite

---

## 7. Credit Costs

| Operation        | Cost                    |
|------------------|-------------------------|
| Humanize         | ~1 credit per 100 words |
| Auto-Cite        | ~3 credits per analysis |
| Plagiarism Check | ~5 credits per check    |
| AI Score Check   | ~1 credit               |

---

## 8. Error Handling

- **API responses:** Standard `{ code, message, data }` pattern (from Survify)
- **AI failures:** Primary → fallback via AIServiceManager
- **Rate limits:** Per-user: humanize 10/min, auto-cite 5/min, plagiarism 3/min
- **Credit guard:** Check balance before processing, atomic deduction, refund on failure
- **File validation:** Max 10MB, validate MIME type server-side, sanitize extracted text
- **Stream errors:** If SSE/Socket disconnects, job completes in background, retrievable via GET

---

## 9. Security

- **Auth:** JWT in cookies, Passport.js (same as Survify)
- **Input sanitization:** Sanitize all user text before LLM prompts (prevent prompt injection)
- **File uploads:** Validate type + size server-side, S3 storage with random keys
- **API keys:** All third-party keys in `.env`, never exposed to client
- **CORS:** Restrict to frontend domain in production

---

## 10. Testing

- **Unit tests:** AI prompt builders, citation formatters, credit calculation
- **Integration tests:** Full API flow (auth → upload → humanize → check history)
- **Mock external APIs:** Mock OpenAI/Claude, CrossRef, Copyscape in tests
- **Manual QA:** Real essays across all input modes (paste, upload docx/pdf/txt, URL)

---

## 11. Deployment

- **Local dev:** Docker Compose for MongoDB + Redis
- **Production:** PM2 behind reverse proxy (same as Survify)
- **Config:** `.env.example` with all required keys documented
