# GenoScribe agent instructions

## Mission

GenoScribe is an evidence-first review system for genomics papers and technical documents.

Its primary purpose is to help scientists inspect, structure, verify, and audit evidence with traceable support.

## Product hierarchy

### Core / flagship: Paper mode
Paper mode is the primary wedge and highest-priority workflow.
Prioritize:
- structured paper retrieval and synthesis
- citation-faithful evidence review
- contradiction detection
- supported vs unsupported claim handling
- audit-first outputs
- review workflow quality and inspectability

### Secondary / specialized: Assembly mode
Assembly mode is a specialized extension built on the same evidence spine.
Prioritize:
- QC-focused interpretation
- provenance-linked metrics and summaries
- narrow scope around QUAST, BUSCO, KAT, Bandage, and related assembly diagnostics
Do not let assembly mode redefine the product.

### Experimental / research-only: Variant mode
Variant mode is experimental and research-only.
Prioritize:
- evidence completeness
- HGVS normalization
- contradiction tracking
- ancestry/context extraction
Do not present variant mode as clinical interpretation support.
Do not let variant-mode complexity degrade the flagship paper workflow.

## Non-negotiables

- Evidence first.
- Preserve provenance, auditability, and reproducibility.
- Keep distinctions explicit between supported evidence, unsupported claims, limitations, contradictions, missing coverage, and model inference.
- Do not soften conflicts or missing coverage.
- Prefer minimal, high-leverage changes.
- Preserve backend truth; interfaces must remain thin consumers.

## Product boundaries

GenoScribe is:
- an evidence-review system
- a scientific inspection and audit tool
- a local or developer-facing trust-oriented workflow

GenoScribe is not:
- a general chatbot
- a clinical decision engine
- a polished multi-purpose assistant product
- a place to add broad chat UX or unrelated new modes

## Prioritization rules

When choosing between tasks:
1. strengthen paper mode first
2. improve assembly mode only when it reinforces the same evidence architecture
3. keep variant mode conservative and explicitly experimental
4. defer features that blur product identity

## Avoid drift

Do not:
- treat all three modes as equally mature
- add features that increase product blur
- introduce UI polish work that outruns backend trust
- add cross-mode hacks that weaken paper-mode retrieval or audits
- overbuild abstractions without clear current value

## Preferred outputs from Codex

When proposing work, distinguish:
- core
- secondary
- experimental
- required now
- optional later
- deferred

When implementing:
- keep patches surgical
- document tradeoffs clearly
- add focused tests
- preserve backward compatibility when possible
