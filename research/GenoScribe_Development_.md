# GenoScribe (Ancestra) — Research & Engineering Log  
**Scope:** Phase 0 → Phase 6 (Terminal Claude → RAG assistant → CLI product packaging)  
**Audience:** Complete beginners → advanced builders  
**Principles:** Scientific rigor • Reproducibility • No hallucination (eventual) • Modularity • Minimal variables

---

## 0) What GenoScribe is (Essence of the Tool)

GenoScribe is a local terminal-based genomics research assistant designed to accelerate reading, auditing, and operationalizing genomics knowledge while maintaining scientific discipline. It combines:

1) **LLM conversation** (Claude via Anthropic API)  
2) **Local document library** (PDF/TXT/MD added from your PC)  
3) **Retrieval-Augmented Generation (RAG)**: answers can be grounded in retrieved text snippets rather than the model’s general memory  
4) **Audit-style evidence workflows**: /search → /cite → “strict evidence table” behaviors  
5) **Reproducible structure**: command-driven interface + saved sessions + version control

The deeper mission is aligned with **Ancestra Genomics**: building trustworthy, ancestry-aware, reproducible genomics research tooling that teaches methodological rigor—not just “answers questions”.

---

## 1) Core Pain Points Being Solved (Why We Built This)

### Pain Point A — Genomics paper overload  
Modern genomics moves fast: variant predictors, foundation models, pathogenicity tools, ancestry bias studies. Reading and extracting actionable knowledge manually is slow.

### Pain Point B — Hallucination risk in standard LLM usage  
LLMs can produce convincing output that is not evidence-based. In genomics (high-stakes), this is unacceptable.

### Pain Point C — Reproducibility gap  
A lot of “AI help” lacks a reproducible workflow:
- unclear evidence provenance
- no traceable audit path
- no version control discipline
- unstable environments (dependencies missing)

### Pain Point D — Training intuition for beginners  
Beginners need:
- why a tool behaves a certain way
- how to debug systematically
- how to reason about architecture and algorithms
- how to separate "evidence" from "background knowledge"

GenoScribe is meant to teach this implicitly through the interface and workflows.

---

## 2) Phase 0 — Terminal Claude (First Working Baseline)

### Goal  
Get a working terminal chat with Claude using the official Python SDK.

### What we did  
- Installed Python SDK: `pip install anthropic`
- Set API key in environment: `ANTHROPIC_API_KEY`
- Wrote a basic terminal loop (`claude.py`) using:
  - `anthropic.Anthropic(api_key=...)`
  - `client.messages.create(model=..., messages=[...])`

### What failed initially and why  
- Attempts to install an Anthropic CLI via npm failed (404 / package not found).  
  **Reason:** not everything branded “Anthropic CLI” exists on npm, and packages can be renamed, removed, or restricted.  
  **Lesson:** When a toolchain fails, fall back to the official SDK that is documented and supported.

### Key engineering intuition  
Start from the smallest working unit (“hello world”) and validate:
- environment variable works
- model name is valid
- request/response loop works

This becomes the stable foundation to scale.

---

## 3) Phase 1 — Conversation Memory (Stateful Chat)

### Goal  
Make Claude remember prior turns within a session (multi-turn behavior).

### What we implemented  
A list called `conversation = []` where each user/assistant message is appended:

- user input appended as `{"role":"user","content":...}`
- Claude reply appended as `{"role":"assistant","content":...}`

### Why it matters  
Without memory, the assistant is just single-shot Q&A. With memory:
- iterative paper dissection becomes possible
- you can refine prompts without repeating context
- it supports “research sessions” like a real collaborator

### Tip for top-level builders  
Memory must remain controlled:
- too long → cost & drift
- too short → forgets key context
Eventually you want summarization + pinned facts + retrieval-based context injection.

---

## 4) Phase 2 — Local Library + RAG (Core Research Instrument)

### Goal  
Make the assistant ground answers in local papers, not general model memory.

### Implemented commands  
- `/add <path>`: ingest PDFs/MD/TXT into a local library  
- `/search <query>`: retrieve relevant passages from the library  
- `/cite <n>`: attach retrieval #n as a citation into the next prompt  
- `/expand <n>`: add neighbor chunks around a retrieval for wider context

### Why this matters scientifically  
RAG creates a controlled evidence channel:
- you can point to what was used
- you can prevent unsupported claims
- you can audit the chain: query → retrieval → cited excerpt → answer

### What went wrong at first  
A key failure mode:
- user typed `add/ path` instead of `/add path`
- the tool treated it like normal chat and the LLM responded from generic memory
- result: convincing but ungrounded summary

**Lesson:** UX guardrails matter. A serious research tool must reduce “accidental non-command input” drift.

---

## 5) Phase 3 — Audit Discipline (Strict Evidence Behavior)

### Goal  
When evidence excerpts exist, enforce “audit-grade” behavior:
- no extra claims unless supported by the cited text
- separate evidence-backed statements from background definitions
- mark unsupported claims as “Unknown”

### Why this matters for Ancestra  
Ancestry-aware genomics and clinical interpretation require trust. Trust requires:
- evidence provenance
- transparent limits
- refusal to invent missing details

### Key insight  
Strictness cannot activate only when citations exist.  
If we want “no hallucination,” eventually we must implement:
- RAG-only mode
- deterministic library accounting
- refusal to answer without evidence unless user explicitly asks for background

(Planned upgrades.)

---

## 6) Phase 4 — Modes (Paper → Assembly → Variant)

### Goal  
Align outputs with genomics workflows:
- Paper mode: dissection, evidence tables, claim audit
- Assembly mode: QC reporting checklist (QUAST/BUSCO/KAT/Bandage mindset)
- Variant mode: leakage-safe evaluation plans (ancestry-aware)

### Why modes are architecturally powerful  
Modes are “policy modules”:
- same infrastructure (RAG, citations, memory)
- different system prompts + output structure

This is modular architecture: you change behavior without rewriting core machinery.

### Reality check  
Paper mode alone is already valuable and feasible.
Assembly/variant modes are not “required” for an MVP but they are meaningful for a long-term platform.

---

## 7) Phase 5 — Engineering Hygiene (Git + Repo Structure)

### Goal  
Make this reproducible and professionally versioned.

### Problems encountered  
`git status` failed: “not a git repository”  
**Reason:** repo had not been initialized (`.git` missing).

### Fix  
- created a project folder (GenoScribe)
- moved scripts inside
- initialized git inside project root
- added `.gitignore` to avoid committing junk and secrets

### Core lesson  
Reproducibility is not optional. If it can’t be rebuilt cleanly, it’s not research-grade software.

---

## 8) Phase 6 — “Software Product” Upgrade (Installable CLI Command)

### Goal  
Make it runnable as:

`genoscribe`

instead of:

`python genoscribe_app.py`

### Why it matters  
This reduces variables:
- no guessing which file to run
- no “works only in one terminal”
- dependencies become explicit and installable

### What we built  
- `genoscribe/` package folder
- `genoscribe/cli.py` entrypoint calling `genoscribe_app.main()`
- `pyproject.toml` defining:
  - package metadata
  - dependencies
  - CLI script entrypoint
- `environment.yml` for conda reproducible env creation:
  - installs project in editable mode `-e .`

### Debugging win  
`ModuleNotFoundError: pypdf` occurred in a new terminal.  
**Reason:** environment drift (dependency not installed in that interpreter/env).  
**Fix:** packaging + environment files ensured fresh installs carry dependencies.

### Hygiene improvement  
`genoscribe.egg-info/` was accidentally committed.  
**Fix:** added to `.gitignore` and removed from git tracking.

---

## 9) Current State of GenoScribe (Today)

### What works reliably
- CLI command works: `genoscribe` launches
- Commands exist: `/add /search /cite /expand /template /mode ...`
- Project is version-controlled with clean structure
- Conda env creation works and installs dependencies

### What still needs to be upgraded (scientific rigor)
These are known architectural gaps causing “not convincing” behavior:

1) **Library accounting must be deterministic**
   - Questions like “which papers mention transformers?” should be answered by a local scan (`/where transformers`), not by the LLM.

2) **RAG-only enforcement**
   - If no citations exist, the assistant should refuse to give evidence-framed answers.
   - It should ask the user to `/search` and `/cite` first.

3) **Retrieval ranking upgrade**
   - Current keyword/TF similarity works but can feel weak.
   - Upgrade path: TF-IDF (still explainable) before embeddings.

4) **PDF extraction quality scoring**
   - Indexing warnings like float conversion errors suggest parser quirks.
   - We need extraction quality metrics + fallback extractors (PyMuPDF, Docling optional).

These upgrades are next milestones.

---

## 10) How to Think Like a Top-Level Builder (Meta-Lessons)

### Lesson 1 — Separate layers clearly  
A research assistant is a system of layers:
- UI/CLI
- retrieval/indexing
- evidence packaging
- LLM reasoning policy
- persistence/state
- reproducibility/packaging

Confusing these layers leads to bugs that “feel like model issues” but are actually system routing issues.

### Lesson 2 — Determinism is your ally  
Where possible:
- compute it (don’t generate it)
- retrieve it (don’t guess it)
- audit it (don’t trust vibes)

### Lesson 3 — Design for failure  
Expect:
- broken PDFs
- bad extraction
- command typos
- environment drift
Build guardrails:
- typo suggestions
- RAG-only mode
- extraction warnings
- deterministic library scan commands

### Lesson 4 — Minimize variables  
One command, one entrypoint, one config file, clear defaults.
Everything else optional and explicit.

---

## 11) Next Planned Phases (Roadmap Summary)

### Phase 7 — Deterministic library introspection
- `/where <term>`
- `/docs`
- `/stats`

### Phase 8 — RAG-only mode + refusal policies
- never answer evidence claims without citations
- explicitly separate “Background” vs “Evidence”

### Phase 9 — Retrieval upgrade
- TF-IDF ranking + better chunking
- optional embeddings later (but must remain auditable)

### Phase 10 — PDF parsing backend selection
- pypdf default
- PyMuPDF optional
- Docling optional for structured extraction
- extraction quality scoring + fallback behavior

---

## Appendix — Command Workflow Patterns (Beginner-friendly)

### Pattern A: Audit-grade paper answer
1) `/search <topic>`
2) `/cite <n>` (or `/expand <n>`)
3) Ask your question and request strict evidence format

### Pattern B: Deterministic “which papers mention X”
(Planned) use:
- `/where X`

This avoids hallucination entirely.

---

**End of Phase 0–6 Log**

Addendum to the research log: why BM25 is the right next move (and what needed correcting)

After testing GenoScribe on a larger local library, we recognized that “not convincing” retrieval results are often not a model problem—they’re a retrieval-ranking problem. A strong, still-auditable upgrade over naive term-frequency scoring is BM25, a probabilistic-style lexical ranking function widely used in production search systems. The core logic is scientifically sound: BM25 fixes two failure modes that show up constantly in genomics PDFs—term-frequency saturation (a paper that repeats TP53 hundreds of times should not dominate results forever) and document length normalization (long review papers shouldn’t win just because they contain more words). However, we also tightened the language around BM25 so it stays accurate and non-hyped: “TF-IDF” is not one single method and some variants already apply normalization; BM25’s saturation is not literally “log-odds”; and claims about “rare variant robustness” depend heavily on the corpus and tokenization choices. The practical conclusion remains: BM25 is an excellent next step for an audit-grade genomics assistant because it improves ranking quality while remaining deterministic and explainable—each score can be traced to per-term contributions—making it compatible with Ancestra’s standards for scientific rigor and reproducibility.

. Retrieval quality is “garbage in, garbage out.” In practice, BM25 will only look “clinical-grade” if (1) the text is normalized consistently and (2) the units you search over (chunks) are well-formed.

We’ll go step by step and build intuition.

1) Tokenization & normalization (the hidden engine of retrieval quality)
The intuition

A lexical search engine is only as good as its ability to recognize that different surface forms refer to the same underlying concept, and that some surface forms should not be broken apart.

In genomics text, naïve tokenizers fail because genomics is full of:

mixed alphanumerics (rs429358, BRCA1, HLA-DQB1)

punctuation-heavy identifiers (c.68_69delAG, p.Arg117His, NM_000059.4)

Greek letters (β, α)

hyphenated gene/protein complexes (NF-κB, HLA-DRB1)

weird PDF artifacts (line-break hyphens, ligatures, broken words)

If your tokenizer splits the important identifiers incorrectly (or merges unrelated fragments), your retriever will “miss” the evidence even if it exists in the PDF.

What we want (goals)

A good genomics-normalization layer should:

preserve biomedical identifiers as single searchable units where possible

standardize variants of the same token so queries match documents reliably

repair PDF extraction artifacts (especially line-break hyphenation)

make ranking robust without requiring embeddings

Practical normalization rules (what to implement first)

Start with a minimal but high-impact set:

A. Unicode normalization

Convert text to a consistent Unicode form (NFKC). This helps with visually similar characters and ligatures.

Convert to lowercase for general words, but optionally keep a copy of original case for gene symbols if you choose.

B. Greek letter normalization
Map common Greek letters to ASCII equivalents so users can type either form:

β → beta, α → alpha, κ → kappa
This matters for tokens like NF-κB.

C. De-hyphenation from PDFs
PDFs often split words at line endings:

patho- + newline + genicity becomes pathogenicity
You must repair this or you’ll create fake tokens.

D. Identifier-friendly tokenization
Use a regex tokenizer that treats as one token:

rsIDs: rs\d+

HGVS-like strings: patterns containing c. p. g. plus punctuation and digits

transcript IDs: NM_000059.4 etc.

gene symbols: [A-Z0-9]{2,} but be careful (you don’t want every acronym)

This is the key: don’t let a generic “split on punctuation” tokenizer destroy your important tokens.

E. Optional stopword control
Don’t overdo stopwords in genomics. Words like “variant”, “pathogenic”, “missense” are common but still meaningful. Use a light list (classic English stopwords) and don’t remove domain terms.

2) Chunking strategy (your retrieval unit)
First: is chunking the most recommended way?

Chunking is recommended, but it’s not the only approach. Think of it as choosing your “document granularity.”

You have three main choices:

Whole-document retrieval

Pro: simplest, no chunking errors

Con: ranking is coarse; your citations become huge; you’ll return irrelevant parts of long reviews.

Page-level retrieval

Pro: natural for PDFs; citations map cleanly to page numbers

Con: pages can mix multiple topics; still often too big.

Chunk-level retrieval (what you’re doing)

Pro: high precision; citations are tight; great for audit tables

Con: easy to fragment context if chunks are too small; retrieval can feel “thin.”

The right mental model

Chunking is not just a technical detail; it’s a scientific design decision:

Too small → you get evidence fragments that don’t carry definitions, assumptions, or conditions.

Too big → you dilute signal and ranking becomes noisy.

For GenoScribe (audit-grade, evidence-based), chunking is generally the best default if it’s done well, because you want to cite a compact passage as evidence.

What “good chunking” means for papers

In scientific PDFs, the best retrieval unit is often:

a paragraph (or multi-paragraph block)

or a section subunit (Methods subsection, Results paragraph, figure caption + surrounding explanation)

So, you want semantic-ish chunking rather than arbitrary “N characters”.

Recommended chunking strategy for GenoScribe

A strong, still-simple strategy:

Split by page first (keeps citations stable and traceable)

Within each page, split into paragraph-like blocks

paragraphs separated by blank lines or large whitespace gaps

If a paragraph block is too large:

split by sentences to ~150–300 words

Add overlap (a small overlap reduces fragmentation)

e.g., last 1–2 sentences of the previous chunk carried into the next chunk

Why overlap matters

Scientific meaning often spans boundaries:

a claim is in one sentence

the condition (“in Europeans only”, “under threshold 0.1%”) is in the next
Overlap reduces false confidence and improves context.

3) Implement BM25 (after tokenization + chunking are stable)
Intuition: why BM25 works better than TF/TF-IDF in your setting

Once tokens and chunks are reliable, BM25 is a smarter way to score “term match quality”:

It does not reward infinite repetition (TF saturation).

It does normalize for chunk length (so long chunks don’t win by sheer volume).

It stays explainable: score is a sum of term contributions.

Implementation plan (minimal changes, maximum auditability)

We implement BM25 at the chunk level:

Each chunk becomes a “document” for BM25.

We store:

tokenized terms per chunk

term frequency per chunk

document length (number of tokens)

We compute corpus statistics:

N = number of chunks

df(term) = number of chunks containing term

avgdl = average chunk length

Then scoring is:

For query Q and chunk D:

compute IDF per query term

apply BM25 formula

sum contributions

Why “chunk-level BM25” is aligned with your evidence workflow

Because your evidence system cites “chunk=32” etc. BM25 improves how you choose chunk 32 in the first place.

What we should do next, concretely

To do this properly without breaking what already works, I need to modify your code in the exact places where:

text is extracted from PDFs

text is chunked

indexing stores chunks

/search scores chunks

However, I can’t safely patch without seeing your current genoscribe_app.py (and some earlier uploaded files in this chat have expired on my side due to tool limits). If you upload your current genoscribe_app.py, I will return:

a drop-in normalization module (unicode, Greek mapping, dehyphenation, regex tokenizer)

improved chunker (page → paragraphs → sentence split + overlap)

a BM25 retriever (auditable, with per-term score breakdown option)

updates to /search to show:

doc, page, chunk

BM25 score

why it ranked (top contributing terms)

a new research log entry (Phase 7 draft) written in the same style as your current log

---

## 9) 2026-03-08 — Detail Panel Layout & Highlight Upgrade

**What changed:** The `details <n>` view now uses a two-column layout (metadata on the left, evidence on the right) with automatic highlighting, query-aware color accents, and basic table rendering for colon-separated metrics. We also persist the last user query so every follow-up view knows what to emphasize.

### Step-by-step build (teach the process)
1. **Diagnose the UX gap:** screenshots showed a tall single column full of raw text—hard to scan, especially when the passage mixes metrics, labels, and prose.
2. **Track the driver signal:** added `last_query` to `AssistantState` so we always know which terms matter for highlight (search, recent ask, or auto-search in chat).
3. **Color discipline:** extracted shared helpers that bold numeric metrics, tint pathogenic/benign/VUS/PLL R/KL keywords, and recolor query tokens. Applied them to both summaries and detail paragraphs.
4. **Layout refactor:** replaced the old panel with a Rich grid: metadata table (Source/Page/Chunk/Doc ID/Type) on the left, a stacked Group of paragraphs/tables on the right. This guarantees horizontal breathing room on wide terminals.
5. **Structured snippets when possible:** when a paragraph is mostly `label: value` lines, render it as a two-column table so trends (e.g., “DYNA KL Divergence: 24.6582”) line up visually.
6. **Horizontal layout polish:** replaced the left/right table with an inline metadata ribbon (“Source | Page | …”) plus column-aware renderables so wide terminals stay filled instead of stacking every line vertically.
7. **Tuned after user feedback:** rolled back the aggressive dual-column heuristic when a passage has no natural block separators to avoid interleaving unrelated numeric sequences.
8. **Auto-summaries + signal filter:** during indexing we now strip axis/tick lines, keep the raw chunk for reference, and store a short summary string (metrics/p-values) so searches and `details` panels lead with human-readable prose.
9. **Regression tests:** reran `uv run pytest` to ensure CLI parsing, session logic, and highlighting helpers still pass.

### Intuition builder (for beginners)
- *Observe before you act:* take screenshots or copy the exact terminal output that feels “off.” It’s easier to justify the fix when you can point to a pain point.
- *Separate concerns:* metadata vs. evidence text serve different cognitive purposes—put them in different visual buckets.
- *Automate small wins:* even a simple heuristic (“does this line contain a colon?”) can unlock a table view without building a full parser.
- *Keep a tight feedback loop:* after each tweak, run `details <n>` again to see if the highlight/spacing matches your mental model. Iterate quickly.

### Expert lens
- Maintain renderable composability. By returning a list of Rich renderables (Text or Table), we can later slot in figures, sparklines, or diff views without rewriting the command handler.
- Persisting `last_query` opens the door for analytics (e.g., “what did the user search most before citing?”) and ensures we don’t color stale terms after session reloads.
- The heuristics stay conservative—key/value detection only kicks in when ≥2 short colon lines exist, avoiding false positives on prose paragraphs.
- Future experiment: detect repeated numeric columns (e.g., histogram labels) and map them to Rich `Columns` for even better chart-like layouts.

### Verification & next steps
- ✅ `uv run pytest` (10 passed, 1 skipped) — confirms no regressions after the UI refactor.
- Next: consider user-configurable highlight palettes and detect structured bullet lists (e.g., “0 5 10”) to render as ASCII charts or mini tables for quantitative passages.





