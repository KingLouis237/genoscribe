
from __future__ import annotations

import os
import re
import json
import time
import pathlib
import shutil
import textwrap
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple
from genoscribe.config import (
    MODEL,
    MAX_TOKENS,
    DATA_DIR,
    LIBRARY_DIR,
    LIBRARY_FILES_DIR,
    INBOX_DIR,
    OUTPUT_DIR,
    SUPPORTED_EXT,
    DEFAULT_SEARCH_METHOD,
    TOP_K_DEFAULT,
    STRICT_ON_CITE,
    DEFAULT_DOWNLOADS_DIR,
)

from anthropic import Anthropic
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

#---
from genoscribe.indexing import (
    AssistantState,
    DocumentIndex,
    LibraryStats,
    Passage,
    build_index_for_file,
    library_requires_stats_rebuild,
    load_library,
    load_library_stats,
    load_state,
    rebuild_library_stats,
    save_doc_index,
    save_library_stats,
    save_state,
)
from genoscribe.indexing.dense_index import DenseRetriever
from genoscribe.indexing.reranker import DenseReranker
from genoscribe.retrieval import (
    build_evidence_block,
    expand_passage,
    format_citation,
)
from genoscribe.retrieval_hybrid import hybrid_collect, infer_target_doc_ids
from genoscribe.search import SearchBackendRegistry, SearchRequest
from genoscribe.schemas.evidence import EvidenceSet, EvidenceSpan
from genoscribe.session_store import SessionStore
from genoscribe.reasoning.query_rewriter import QueryRewriter
from genoscribe.reasoning.synthesizer import EvidenceSynthesizer
from genoscribe.reasoning.verifier import EvidenceVerifier
from genoscribe.reasoning.auditor import EvidenceAuditor

# ----------------------------

console = Console()
search_registry = SearchBackendRegistry()
query_rewriter = QueryRewriter()
synthesizer = EvidenceSynthesizer()
dense_retriever = DenseRetriever()
reranker = DenseReranker(dense_retriever)
verifier = EvidenceVerifier()
auditor = EvidenceAuditor()



"""
genoscribe_app.py (Production Edition)

A terminal-based AI Genomics Research Assistant powered by Anthropic Claude models.

PRODUCTION ENHANCEMENTS:
✅ Hallucination guardrails (prevents citing non-existent papers)
✅ Natural language commands (works with or without slashes)
✅ Citation validation (detects hallucinated citations)
✅ BM25 ranking algorithm (state-of-the-art retrieval)
✅ Structure-aware chunking (paragraph-based, preserves scientific context)
✅ Table and figure detection (special handling for structured data)
✅ Genomics text normalization (Greek letters, hyphenation repair, HGVS notation)

Features:
- Conversation memory (multi-turn context)
- Project system prompt tailored to genomics research workflows
- Local library indexing + search over PDF/TXT/MD files
- RAG workflow: /add -> /search -> /cite -> ask
- Templates (/template) to enforce strict evidence outputs
- Expand citations (/expand) to capture surrounding context
- Modes (/mode): paper, assembly, variant
- One-shot commands:
    /dissect   (paper)    auto paper dissection using last citations/top retrievals
    /qc_report (assembly) draft assembly QC report from last citations/top retrievals
    /eval_plan (variant)  leakage-safe ancestry-aware evaluation plan

Commands (work with or without slashes):
    add <path>         Add a file or folder of documents to your local library
    search <query>     Search your local library for relevant passages
    search_method      Show/set search method (tfidf or bm25)
    cite <n>           Insert a retrieved passage as a citation into your next prompt
    expand <n>         Queue retrieval #n plus neighboring chunks as citations
    templates          List available templates
    template <n>    Activate a template (strict_evidence, paper_dissect, claim_audit)
    template off       Disable active template
    modes              List available modes (paper, assembly, variant)
    mode <n>        Switch mode (paper, assembly, variant). /mode shows current
    dissect            Paper mode: auto-dissection using last citations (or top retrievals)
    qc_report          Assembly mode: draft an assembly QC report from last citations
    eval_plan          Variant mode: generate a leakage-safe evaluation plan (ancestry-aware)
    rebuild_index      Rebuild IDF weights and avg doc length (after adding many docs)
    notes              Show working notes
    note <text>        Add a working note
    clear              Clear conversation history (keeps library + notes)
    save               Save chat + notes to output folder
    library            Show current library contents
    help               Show help
    exit               Quit

IMPORTANT:
- This tool helps with literature + research assistance.
- It does not provide medical advice. Always verify clinically relevant claims.

Requirements:
    pip install anthropic pypdf rich pdfplumber

Environment variable:
    setx ANTHROPIC_API_KEY "sk-ant-..."
"""




# ----------------------------
# Templates + Audit-grade behavior
# ----------------------------

TEMPLATES: Dict[str, str] = {
    "strict_evidence": """Return TWO sections:

A) Strict Evidence Table:
Claim | Evidence quote | Citation | Confidence (High/Med/Low) | Verify next
Rules:
- Only include claims supported by the provided Evidence excerpts.
- If not supported, either OMIT the claim or mark it as Unknown with no evidence quote/citation.
- Do not import assumptions from outside the cited text.

B) Background (not from cited text):
- Only for general definitions (math/stats) if needed.
- Keep it short (<= 6 lines).
""",

    "paper_dissect": """Use this structure:

1) Paper Snapshot
- Research question
- Main contribution (1–3 bullets)
- Why it matters for Ancestra / African genomics

2) Methods (structured)
- Data: cohorts, ancestry, sample sizes, labels (ONLY if supported by evidence; else Unknown)
- Pipeline: tools, thresholds, features
- Evaluation: metrics, validation design, baselines

3) Key Findings (each must be backed by evidence or marked Unknown)
4) Bias & Generalization Risks (ancestry-aware, evidence-grounded)
5) Reproducibility Checklist (what we'd need to replicate)
6) Next actions (3–7 concrete steps)

If Evidence excerpts are provided, apply STRICT evidence discipline.
""",

    "claim_audit": """Produce a claim audit:

- List 5–12 key claims relevant to the user's question.
For each:
Claim | Evidence quote | Citation | Confidence | What to verify next

Rules:
- Only use provided Evidence excerpts for evidence.
- If a claim is important but not supported by excerpts, include it as Unknown (no evidence quote/citation)
  and add a "verify next" step pointing to what to search/cite.
"""
}


# ----------------------------
# Modes (paper -> assembly -> variant)
# ----------------------------
MODE_ORDER = ["paper", "assembly", "variant"]
DEFAULT_MODE = "paper"

# Enhanced prompts with STRICT hallucination prevention
PAPER_PROMPT = """You are GenoScribe, a LOCAL genomics research assistant.

CRITICAL HALLUCINATION PREVENTION RULES:
1. You can ONLY cite papers that exist in the user's local library.
2. You do NOT have access to PubMed, Google Scholar, or any external databases.
3. If you don't have information in the user's library, say: "I don't have that in your library."
4. NEVER use [CITE] tags unless the user has provided Evidence excerpts.
5. NEVER cite papers from your training data (Vaswani 2017, Jumper 2021, etc.).
6. When explaining general concepts, clearly label them as "General knowledge (not from your library):"

Your job:
- Help the user read, understand, and synthesize THEIR genomics literature.
- Produce rigorous, structured outputs based ONLY on provided evidence.
- Be explicit about uncertainty. Prefer "I don't know" over guessing.
- When the user provides Evidence excerpts (formatted like [CITE ...]), treat them as the ONLY primary evidence.
- Always separate:
    (1) What the evidence says (with citations from Evidence excerpts)
    (2) Your inference/interpretation (clearly labeled)
    (3) What to verify next

Operating principles:
- If asked for medical advice or clinical decisions, refuse and redirect to research/education framing.
- For computational tasks, propose reproducible steps (env, commands, file structure, tests).
- For genomics topics, favor standard best practices:
    QC -> alignment/assembly -> variant calling -> annotation -> interpretation -> validation.
- When drafting methods, include software versions, parameters, and reproducibility notes.

Output style:
- Clear headers, bullet points, and small tables when useful.
- Provide actionable next steps.

REMEMBER: Your knowledge is LIMITED to:
1. General genomics/bioinformatics concepts (clearly labeled)
2. Papers in the user's library (ONLY after they search and cite)
"""

ASSEMBLY_PROMPT = """You are GenoScribe's Genome Assembly & QC Assistant (LOCAL library only).

CRITICAL: You can ONLY reference assembly QC data from the user's Evidence excerpts.

Mission:
- Help evaluate genome assemblies based on provided QC metrics.
- Interpret QUAST, BUSCO, KAT, Bandage, N50/L50, coverage, contamination signals.
- Provide reproducible, step-by-step commands and conservative thresholds.

Rules:
- If organism/expected genome size/tech/read depth are missing, label them Unknown/Assumed.
- Separate:
  (1) What the metrics show (ONLY from Evidence excerpts)
  (2) Interpretation (general knowledge, clearly labeled)
  (3) Risks / failure modes
  (4) What to do next

Output structure:
1) Assembly Snapshot
2) QC Metrics & Interpretation
3) Pass/Fail flags (conservative)
4) Recommended next steps
5) Reproducible command checklist

NEVER cite QC values not in the Evidence excerpts.
"""

VARIANT_PROMPT = """You are GenoScribe's Variant Pathogenicity Modeling & Evaluation Assistant (LOCAL library only, research use).

CRITICAL: You can ONLY reference variant data from the user's Evidence excerpts.

Mission:
- Help design ancestry-aware variant pathogenicity models based on user's literature.
- Emphasize methodological rigor: leakage prevention, stratified evaluation, calibration, ancestry-aware reporting.
- Do NOT provide clinical decisions or medical advice.

Rules:
- Always check for data leakage risks (patient overlap, gene/variant leakage, label leakage).
- Always propose ancestry-stratified evaluation and calibration checks.
- If evidence excerpts are provided, cite them; if not, label as general best practice.

Output structure:
1) Problem restatement
2) Evidence (ONLY from provided excerpts)
3) Modeling plan (baselines, features, RF/LR, calibration)
4) Evaluation plan (splits, metrics, subgroup reporting)
5) Bias risks & mitigation
6) Next steps

NEVER cite variant data not in the Evidence excerpts.
"""

MODE_PROMPTS: Dict[str, str] = {
    "paper": PAPER_PROMPT,
    "assembly": ASSEMBLY_PROMPT,
    "variant": VARIANT_PROMPT,
}


# ----------------------------
# Natural Language Command Parser
# ----------------------------

def parse_user_input(text: str) -> Tuple[str, str]:
    """
    Parse user input to detect commands (with or without slashes).
    
    Returns (command, arguments)
    
    Supports:
    - Slash commands: /search BRCA1
    - Natural language: search for BRCA1, find transformers, cite 1, etc.
    - Fallback: treat as conversation
    """
    text = text.strip()
    
    if not text:
        return "chat", ""
    
    # Handle slash commands (original syntax)
    if text.startswith("/"):
        parts = text[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        return cmd, args
    
    # Natural language patterns (case-insensitive)
    text_lower = text.lower()
    
    # Search patterns
    if re.match(r"^(search|find|look for|lookup)\s+", text_lower):
        match = re.match(r"^(?:search|find|look for|lookup)\s+(.+)", text, re.IGNORECASE)
        return "search", match.group(1) if match else ""
    
    # Cite patterns
    if re.match(r"^cite\s+(\d+)$", text_lower):
        match = re.match(r"^cite\s+(\d+)$", text, re.IGNORECASE)
        return "cite", match.group(1)
    
    if re.match(r"^cite\s+(result|passage|retrieval)\s*(\d+)$", text_lower):
        match = re.match(r"^cite\s+(?:result|passage|retrieval)\s*(\d+)$", text, re.IGNORECASE)
        return "cite", match.group(1)
    
    # Expand patterns
    if re.match(r"^expand\s+(\d+)$", text_lower):
        match = re.match(r"^expand\s+(\d+)$", text, re.IGNORECASE)
        return "expand", match.group(1)
    
    # Add patterns
    if text_lower.startswith("add "):
        return "add", text[4:].strip()
    
    # Show/list commands
    if text_lower in ["show modes", "list modes", "modes"]:
        return "modes", ""
    
    if text_lower in ["show templates", "list templates", "templates"]:
        return "templates", ""
    
    if text_lower in ["show notes", "list notes", "notes"]:
        return "notes", ""
    
    if text_lower in ["show library", "list library", "library"]:
        return "library", ""
    
    if text_lower.startswith("inbox"):
        parts = text.split(maxsplit=1)
        args = parts[1] if len(parts) > 1 else ""
        return "inbox", args
    
    if text_lower in ["show inbox", "inbox status"]:
        return "inbox", ""

    if text_lower.startswith("details"):
        parts = text.split(maxsplit=1)
        args = parts[1] if len(parts) > 1 else ""
        return "details", args

    if text_lower.startswith("report "):
        return "report", text[7:].strip()
    
    if text_lower.startswith("recent"):
        parts = text.split(maxsplit=1)
        args = parts[1] if len(parts) > 1 else ""
        return "recent", args

    if text_lower.startswith("watch downloads"):
        parts = text.split(maxsplit=2)
        args = " ".join(parts[2:]) if len(parts) > 2 else ""
        return "watch_downloads", args

    if text_lower in ["sessions", "list sessions", "show sessions"]:
        return "sessions", ""

    # Mode switching
    if re.match(r"^(use|switch to|activate)\s+mode\s+(\d+)$", text_lower):
        match = re.match(r"^(?:use|switch to|activate)\s+mode\s+(\d+)$", text, re.IGNORECASE)
        return "mode", match.group(1)

    if re.match(r"^(use|switch to|activate)\s+mode\s+(paper|assembly|variant)$", text_lower):
        match = re.match(r"^(?:use|switch to|activate)\s+mode\s+(paper|assembly|variant)$", text, re.IGNORECASE)
        return "mode", match.group(1)
    
    if re.match(r"^mode\s+(\d+)$", text_lower):
        match = re.match(r"^mode\s+(\d+)$", text, re.IGNORECASE)
        return "mode", match.group(1)

    if re.match(r"^mode\s+(paper|assembly|variant)$", text_lower):
        match = re.match(r"^mode\s+(paper|assembly|variant)$", text, re.IGNORECASE)
        return "mode", match.group(1)
    
    if text_lower == "mode":
        return "mode", ""
    
    # Template commands
    if re.match(r"^template\s+(\d+)$", text_lower):
        match = re.match(r"^template\s+(\d+)$", text, re.IGNORECASE)
        return "template", match.group(1)
    
    if text_lower == "template off":
        return "template", "off"
    
    if text_lower == "template":
        return "templates", ""
    
    # Special commands
    if text_lower in ["search method", "search_method", "searchmethod"]:
        return "search_method", ""
    
    if re.match(r"^(search method|search_method)\s+(tfidf|bm25)$", text_lower):
        match = re.match(r"^(?:search method|search_method)\s+(tfidf|bm25)$", text, re.IGNORECASE)
        return "search_method", match.group(1)
    
    if text_lower in ["rebuild index", "rebuild_index", "rebuildindex"]:
        return "rebuild_index", ""
    
    # Note taking
    if text_lower.startswith("note "):
        return "note", text[5:].strip()
    
    if text_lower.startswith("add note "):
        return "note", text[9:].strip()

    if text_lower.startswith("session save"):
        return "session_save", text[len("session save"):].strip()

    if text_lower.startswith("session load"):
        return "session_load", text[len("session load"):].strip()

    if text_lower.startswith("session delete"):
        return "session_delete", text[len("session delete"):].strip()

    # One-shot commands
    if text_lower in ["dissect", "dissect paper", "auto dissect"]:
        return "dissect", ""
    
    if text_lower in ["qc report", "qc_report", "qcreport"]:
        return "qc_report", ""
    
    if text_lower in ["eval plan", "eval_plan", "evalplan", "evaluation plan"]:
        return "eval_plan", ""
    
    # Utility commands
    if text_lower in ["clear", "clear history", "reset"]:
        return "clear", ""
    
    if text_lower in ["save", "save session"]:
        return "save", ""
    
    if text_lower in ["help", "commands", "?"]:
        return "help", ""
    
    if text_lower in ["model", "show model"]:
        return "model", ""
    
    if text_lower in ["exit", "quit", "bye", "goodbye"]:
        return "exit", ""
    
    # If no pattern matches, treat as conversation
    return "chat", text


def looks_like_library_overview_request(text: str) -> bool:
    """Heuristically detect when the user is asking about the library itself."""
    lowered = text.lower()
    keywords = ["library", "paper", "papers", "document", "documents", "pdfs"]
    return any(word in lowered for word in keywords)


def run_search(
    library: List[DocumentIndex],
    stats: Optional[LibraryStats],
    method: str,
    query: str,
    top_k: int,
) -> List[Passage]:
    backend = search_registry.get(method)
    request = SearchRequest(query=query, top_k=top_k)
    return backend.search(library, stats, request)


def refresh_dense_index(library: List[DocumentIndex]) -> None:
    if not library:
        return
    try:
        dense_retriever.index(library)
    except Exception as exc:
        console.print(f"[yellow]Dense retriever unavailable:[/yellow] {exc}")


def extend_dense_index(documents: List[DocumentIndex]) -> None:
    if not documents:
        return
    try:
        if dense_retriever.ready():
            dense_retriever.add_documents(documents)
        else:
            dense_retriever.index(documents)
    except Exception as exc:
        console.print(f"[yellow]Dense retriever update failed:[/yellow] {exc}")


def build_evidence_set(passages: List[Passage], mode: str) -> EvidenceSet:
    spans = [
        EvidenceSpan(
            passage=p,
            label=mode,
            metadata={"doc_id": p.doc_id, "chunk_id": str(p.chunk_id)},
        )
        for p in passages
    ]
    return EvidenceSet(spans=spans, confidence=1.0 if passages else 0.0)


def run_mode_pipeline(
    *,
    mode: str,
    query: str,
    library: List[DocumentIndex],
    stats: Optional[LibraryStats],
    search_method: str,
    base_passages: Optional[List[Passage]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Tuple[str, List[Passage], List[str], Dict[str, float]]:
    if not library:
        return "", base_passages or [], ["Library is empty; ingest papers first."], {}

    target_doc_ids = infer_target_doc_ids(query or "", library)
    rewritten_query = query_rewriter.rewrite(query or "latest findings", mode)
    top_passages, timings, _ = hybrid_collect(
        library=library,
        stats=stats,
        query=rewritten_query,
        search_method=search_method,
        search_registry=search_registry,
        dense_retriever=dense_retriever,
        reranker=reranker,
        mode=mode,
        base_passages=base_passages,
        top_k=TOP_K_DEFAULT,
        target_doc_ids=target_doc_ids,
    )

    context = dict(context or {})
    context.setdefault("query", query)
    context.setdefault("target_doc_ids", target_doc_ids)
    synthesis_text = synthesizer.synthesize(mode, top_passages, **context) if top_passages else ""

    evidence_set = build_evidence_set(top_passages, mode)
    ok, verification_warnings = verifier.verify(top_passages)
    warnings: List[str] = []
    if not ok:
        warnings.extend(verification_warnings)
    warnings.extend(auditor.audit([evidence_set]))

    return synthesis_text, top_passages, warnings, timings


def parse_session_save_args(arg_str: str) -> Tuple[str, str]:
    if not arg_str:
        return "", ""

    if "--desc" not in arg_str:
        return arg_str.strip(), ""

    name_part, desc_part = arg_str.split("--desc", 1)
    name = name_part.strip()
    desc = desc_part.strip()
    if desc.startswith("="):
        desc = desc[1:].strip()

    if len(desc) >= 2 and ((desc.startswith('"') and desc.endswith('"')) or (desc.startswith("'") and desc.endswith("'"))):
        desc = desc[1:-1]

    return name, desc


def passages_to_payload(passages: List[Passage]) -> List[Dict[str, Any]]:
    return [asdict(p) for p in passages]


def payload_to_passages(items: List[Dict[str, Any]]) -> List[Passage]:
    passages: List[Passage] = []
    for item in items or []:
        try:
            passages.append(Passage(**item))
        except TypeError:
            continue
    return passages


def build_snapshot_payload(
    conversation: List[Dict[str, str]],
    working_notes: List[str],
    mode: str,
    template: Optional[str],
    search_method: str,
    pending_citations: List[Passage],
    last_evidence_sources: List[Passage],
) -> Dict[str, Any]:
    return {
        "conversation": conversation,
        "working_notes": working_notes,
        "mode": mode,
        "template": template,
        "search_method": search_method,
        "pending_citations": passages_to_payload(pending_citations),
        "last_evidence_sources": passages_to_payload(last_evidence_sources),
    }


def warn_about_missing_docs(passages: List[Passage], library_docs: Dict[str, DocumentIndex]) -> None:
    missing = sorted({p.doc_id for p in passages if p.doc_id not in library_docs})
    if missing:
        console.print(
            f"[yellow]Warning:[/yellow] {len(missing)} citation(s) reference documents that are not currently in the library: {', '.join(missing)}"
        )
def validate_model_response(
    response_text: str,
    user_ran_search: bool,
    library_size: int,
    allowed_passages: Optional[List[Passage]] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Validate Claude's response for hallucinated citations.
    
    Returns (is_safe, warning_message)
    
    is_safe: False if hallucination detected
    warning_message: Explanation if not safe
    """
    # Check for [CITE] tags
    cite_pattern = r'\[CITE[^\]]*\]'
    citations = re.findall(cite_pattern, response_text)
    
    allowed_map: Dict[str, set[str]] = {}
    if allowed_passages:
        for passage in allowed_passages:
            doc_key = pathlib.Path(passage.source_path).name.lower()
            allowed_map.setdefault(doc_key, set()).add(str(passage.chunk_id))

    if not citations:
        if allowed_map:
            return False, (
                "⚠️  Evidence was provided but the response has no citations. "
                "Ask GenoScribe to reference the queued passages explicitly."
            )
        return True, None
    
    # Citations found - check if user actually searched
    if not user_ran_search:
        return False, (
            "⚠️  HALLUCINATION DETECTED: The assistant cited sources, but you haven't searched your library yet.\n"
            "These citations are likely from the model's pretraining data, not your papers.\n"
            f"Try: 'search <your query>' to find real passages from your {library_size} documents."
        )
    
    # Verify citations map to provided passages
    if allowed_map:
        cite_detail_re = re.compile(r"\[CITE[^\]]*doc=([^\s]+)[^\]]*chunk=(\d+)[^\]]*\]", re.IGNORECASE)
        for cite in cite_detail_re.finditer(response_text):
            doc = cite.group(1).lower()
            chunk = cite.group(2)
            if doc not in allowed_map or chunk not in allowed_map[doc]:
                return False, (
                    "⚠️  The assistant cited a passage that was never provided. "
                    "Only cite excerpts that were queued as evidence."
                )

    # User searched but citations might be suspicious
    # Check for known hallucination patterns
    suspicious_patterns = [
        r'Vaswani.*2017.*Attention',
        r'Jumper.*2021.*AlphaFold',
        r'Rives.*2021.*ESM',
        r'Nature.*\d{3,4}',
        r'Science.*\d{3,4}',
        r'Cell.*\d{3,4}',
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, response_text, re.IGNORECASE):
            return False, (
                "⚠️  POSSIBLE HALLUCINATION: The assistant cited well-known papers (Vaswani, Jumper, Rives, etc.).\n"
                "These might be from general training data, not your library.\n"
                "Verify: Do these papers appear in your search results above?"
            )
    
    # Flag metric sentences lacking citations when evidence exists
    if allowed_map:
        sentence_re = re.compile(r"(?<=[.!?])\s+")
        needs_cite_re = re.compile(
            r"(\d+(?:\.\d+)?%?)|\b(p\s*=\s*\d)|\b(auc|aupr|accuracy|precision|recall|kl divergence|baseline)\b",
            re.IGNORECASE,
        )
        sentences = [s.strip() for s in sentence_re.split(response_text) if s.strip()]
        for sentence in sentences:
            if needs_cite_re.search(sentence) and "[CITE" not in sentence:
                return False, (
                    "⚠️  Numeric or metric statements must cite queued evidence. "
                    f"Offending sentence: \"{sentence[:140]}\""
                )

    # Passed checks
    return True, None


# ----------------------------
# Helpers
# ----------------------------
def ensure_dirs():
    for d in [DATA_DIR, LIBRARY_DIR, OUTPUT_DIR, LIBRARY_FILES_DIR, INBOX_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def now_ts() -> str:
    return time.strftime("%Y-%m-%d_%H-%M-%S")


def sanitize_filename(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return safe or "document"


def copy_into_library_store(src: pathlib.Path) -> pathlib.Path:
    """Copy a source file into the managed library store and return the new path."""
    LIBRARY_FILES_DIR.mkdir(parents=True, exist_ok=True)
    dest_name = f"{sanitize_filename(src.stem)}_{now_ts()}{src.suffix.lower()}"
    dest = LIBRARY_FILES_DIR / dest_name
    shutil.copy2(src, dest)
    return dest


def list_inbox_files() -> List[pathlib.Path]:
    """Return supported files currently in the inbox drop folder."""
    if not INBOX_DIR.exists():
        return []

    files: List[pathlib.Path] = []
    for ext in SUPPORTED_EXT:
        files.extend(INBOX_DIR.glob(f"*{ext}"))

    filtered: List[pathlib.Path] = []
    for f in files:
        if f.is_file():
            filtered.append(f)

    def _mtime(path: pathlib.Path) -> float:
        try:
            return path.stat().st_mtime
        except FileNotFoundError:
            return 0.0

    filtered.sort(key=_mtime, reverse=True)
    return filtered


def show_inbox_queue(files: List[pathlib.Path]) -> None:
    """Render the inbox queue as a table."""
    if not files:
        console.print(f"[yellow]Inbox is empty. Drop PDF/TXT/MD files into {str(INBOX_DIR)}.[/yellow]")
        return

    table = Table(title=f"Inbox ({len(files)} files)", show_lines=False)
    table.add_column("#", justify="right", width=3)
    table.add_column("File")
    table.add_column("Size", justify="right")
    table.add_column("Modified", justify="right")

    for idx, path in enumerate(files, start=1):
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        size_kb = stat.st_size / 1024
        mtime = time.strftime("%b %d %H:%M", time.localtime(stat.st_mtime))
        table.add_row(str(idx), path.name, f"{size_kb:.1f} KB", mtime)

    console.print(table)


def sync_inbox(idf_weights: Dict[str, float]) -> List[DocumentIndex]:
    """Import every supported file in the inbox folder."""
    pending = list_inbox_files()
    if not pending:
        return []

    imported: List[DocumentIndex] = []
    for path in pending:
        docs = add_path_to_library(
            str(path),
            idf_weights,
            copy_source=True,
            delete_original=True,
        )
        imported.extend(docs)
    return imported


def get_downloads_dir() -> pathlib.Path:
    return DEFAULT_DOWNLOADS_DIR


def move_downloads_to_inbox() -> List[pathlib.Path]:
    moved: List[pathlib.Path] = []
    downloads = get_downloads_dir()
    if not downloads.exists():
        return moved

    INBOX_DIR.mkdir(parents=True, exist_ok=True)

    for ext in SUPPORTED_EXT:
        for fp in downloads.glob(f"*{ext}"):
            if not fp.is_file():
                continue
            try:
                dest = INBOX_DIR / fp.name
                counter = 1
                while dest.exists():
                    dest = INBOX_DIR / f"{fp.stem}_{counter}{fp.suffix}"
                    counter += 1
                shutil.move(str(fp), dest)
                moved.append(dest)
            except Exception as err:
                console.print(f"[yellow]Warning:[/yellow] Could not move {fp.name} from Downloads: {err}")
    return moved


def ensure_inbox_shortcut() -> pathlib.Path:
    desktop = pathlib.Path.home() / "Desktop"
    desktop.mkdir(exist_ok=True)
    shortcut = desktop / "Open GenoScribe Inbox.cmd"
    shortcut.write_text(
        f'@echo off\nstart "" "{INBOX_DIR}"\n',
        encoding="utf-8",
    )
    return shortcut


METRIC_KEYWORDS = {"metric", "metrics", "auc", "auroc", "accuracy", "precision", "recall", "f1", "mcc", "aupr", "ap"}
DETAIL_KEYWORD_PATTERNS = [
    (re.compile(r"\bpathogenic(?:ity)?\b", re.IGNORECASE), "bright_red"),
    (re.compile(r"\bbenign\b", re.IGNORECASE), "bright_green"),
    (re.compile(r"\bVUS\b", re.IGNORECASE), "yellow"),
    (re.compile(r"\bClinVar\b", re.IGNORECASE), "cyan"),
    (re.compile(r"\bPLL?R\b", re.IGNORECASE), "bright_yellow"),
    (re.compile(r"\bKL divergence\b", re.IGNORECASE), "bright_magenta"),
]
QUERY_HIGHLIGHT_COLORS = [
    "green",
    "bright_magenta",
    "bright_cyan",
    "bright_yellow",
]


def summarize_passage_text(text: str) -> str:
    clean = re.sub(r"\s+", " ", text.strip())
    if not clean:
        return "(no preview)"

    sentences = re.split(r"(?<=[.!?])\s+", clean)
    candidates: List[str] = []

    for sentence in sentences:
        s = sentence.strip()
        if not s:
            continue
        candidates.append(s)
        first_alpha = next((ch for ch in s if ch.isalpha()), "")
        if first_alpha and first_alpha.islower():
            # Likely a mid-sentence fragment â€“ keep scanning.
            continue
        if len(s.split()) < 5:
            continue
        if s[-1] not in ".!?":
            return f"{s}..."
        return s

    fallback = " ".join(candidates[:2]).strip()
    if fallback:
        return textwrap.shorten(fallback, width=220, placeholder="...")
    return textwrap.shorten(clean, width=200, placeholder="...")


def extract_query_terms(query: str) -> List[str]:
    lowercase = query.lower()
    tokens = re.findall(r"[a-z0-9][a-z0-9._+/-]*", lowercase)
    seen = set()
    filtered: List[str] = []
    for token in tokens:
        if len(token) < 3 and not token.isdigit():
            continue
        if token in seen:
            continue
        seen.add(token)
        filtered.append(token)
    return filtered


def apply_metric_highlight(text_obj: Text, query: str) -> None:
    if not query:
        return
    lowered = query.lower()
    if not any(keyword in lowered for keyword in METRIC_KEYWORDS):
        return
    pattern = re.compile(r"\d+(?:\.\d+)?%?")
    plain = text_obj.plain
    for match in pattern.finditer(plain):
        text_obj.stylize("bold", match.start(), match.end())


def highlight_terms(text_obj: Text, query: str) -> None:
    terms = extract_query_terms(query)
    if not terms:
        return
    plain = text_obj.plain
    for idx, term in enumerate(terms):
        color = QUERY_HIGHLIGHT_COLORS[idx % len(QUERY_HIGHLIGHT_COLORS)]
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        for match in pattern.finditer(plain):
            text_obj.stylize(color, match.start(), match.end())


def build_summary_text(summary: str, query: str) -> Text:
    summary = summary.strip() if summary else "(no preview)"
    text_obj = Text(summary)
    apply_metric_highlight(text_obj, query)
    for pattern, style in DETAIL_KEYWORD_PATTERNS:
        for match in pattern.finditer(text_obj.plain):
            text_obj.stylize(style, match.start(), match.end())
    highlight_terms(text_obj, query)
    return text_obj


def style_detail_text(text: str, query: str) -> Text:
    content = text.strip() or "(no text available)"
    text_obj = Text(content)
    apply_metric_highlight(text_obj, query)
    for pattern, style in DETAIL_KEYWORD_PATTERNS:
        for match in pattern.finditer(text_obj.plain):
            text_obj.stylize(style, match.start(), match.end())
    highlight_terms(text_obj, query)
    return text_obj


def _maybe_render_key_value_table(block: str, query: str):
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    pairs: List[Tuple[str, str]] = []
    for line in lines:
        if ":" not in line:
            pairs = []
            break
        key, value = line.split(":", 1)
        if len(key) > 40:
            pairs = []
            break
        pairs.append((key.strip(), value.strip()))
    if len(pairs) >= 2:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="dim", width=24, justify="right")
        table.add_column()
        for key, value in pairs:
            table.add_row(key, style_detail_text(value, query))
        return table
    return None


def _preprocess_passage_text(text: str) -> str:
    lines: List[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            lines.append("")
            continue
        if re.fullmatch(r"[a-z]", stripped):
            continue
        if re.fullmatch(r"[0-9.\s]+", stripped):
            continue
        lines.append(stripped)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"\n([a-z])\s*\n", r"\n\n\1\n\n", cleaned)
    cleaned = re.sub(r"\n(Fig\.[^\n]+)\n", r"\n\n\1\n\n", cleaned)
    return cleaned.strip()


def build_detail_renderables(text: str, query: str) -> List[Any]:
    cleaned = _preprocess_passage_text(text)
    if not cleaned:
        return [style_detail_text(text, query)]
    blocks = re.split(r"\n\s*\n", cleaned)
    renderables: List[Any] = []
    for block in blocks:
        if not block.strip():
            continue
        table = _maybe_render_key_value_table(block, query)
        if table:
            renderables.append(table)
        else:
            renderables.append(style_detail_text(block, query))
    return renderables or [style_detail_text(text, query)]


def display_evidence_context(passages: List[Passage]) -> None:
    if not passages:
        return
    for idx, passage in enumerate(passages, start=1):
        title = pathlib.Path(passage.source_path).name
        panel_title = f"Evidence {idx}: {title} p.{passage.page or '-'}"
        console.print(Panel(passage.text.strip(), title=panel_title, border_style="cyan"))


def checklist_complete(checklist: Dict[str, bool]) -> bool:
    return all(checklist.values())


def show_first_run_checklist(checklist: Dict[str, bool]) -> None:
    if checklist_complete(checklist):
        return
    items = [
        ("Drop a paper", checklist.get("imported", False)),
        ("Run a search", checklist.get("searched", False)),
        ("Cite evidence", checklist.get("cited", False)),
    ]
    lines = []
    for label, done in items:
        prefix = "[green]✓[/green]" if done else "[yellow]•[/yellow]"
        lines.append(f"{prefix} {label}")
    console.print(Panel("\n".join(lines), title="First-run Checklist", border_style="magenta"))

def record_recent_docs(state: AssistantState, docs: List[DocumentIndex], limit: int = 5) -> None:
    if not docs:
        return
    for doc in docs:
        if doc.doc_id:
            state.recent_doc_ids.append(doc.doc_id)
    state.recent_doc_ids = state.recent_doc_ids[-limit:]


def _doc_by_id(library: List[DocumentIndex], doc_id: str) -> Optional[DocumentIndex]:
    for doc in library:
        if doc.doc_id == doc_id:
            return doc
    return None


def get_recent_doc_rows(library: List[DocumentIndex], doc_ids: List[str]) -> List[DocumentIndex]:
    rows: List[DocumentIndex] = []
    for doc_id in doc_ids:
        doc = _doc_by_id(library, doc_id)
        if doc:
            rows.append(doc)
    return rows


def show_recent_imports(library: List[DocumentIndex], doc_ids: List[str]) -> None:
    rows = get_recent_doc_rows(library, doc_ids)
    if not rows:
        console.print("[yellow]No recently imported documents yet.[/yellow]")
        return
    table = Table(title="Recently Imported", show_lines=False)
    table.add_column("#", justify="right", width=3)
    table.add_column("Title")
    table.add_column("Type", width=6)
    table.add_column("Passages", justify="right", width=10)
    for idx, doc in enumerate(rows, start=1):
        table.add_row(str(idx), doc.title, doc.ext.upper().replace(".", ""), str(len(doc.passages)))
    console.print(table)
    console.print("[dim]Use 'recent ask <n> <question>' to query a specific paper or 'recent summary <n>' for a quick digest.[/dim]")


def extract_metric_sentences(text: str, limit: int = 3) -> List[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip().replace("\n", " "))
    picks: List[str] = []
    for sent in sentences:
        lowered = sent.lower()
        if any(keyword in lowered for keyword in METRIC_KEYWORDS) and re.search(r"\d+(?:\.\d+)?%?", sent):
            picks.append(sent.strip())
        if len(picks) >= limit:
            break
    return picks or (sentences[:limit] if sentences else ["(no metrics found)"])


def summarize_document(doc: DocumentIndex, limit: int = 2) -> str:
    if not doc.passages:
        return doc.title
    sentences: List[str] = []
    for passage in doc.passages[:2]:
        sentences.extend(re.split(r"(?<=[.!?])\s+", passage.text.strip().replace("\n", " ")))
        if len(sentences) >= limit:
            break
    summary = " ".join(sentences[:limit]).strip()
    return summary or doc.title


def report_metrics_overview(
    library: List[DocumentIndex],
    stats: LibraryStats,
    method: str,
    query: str,
) -> None:
    hits = run_search(
        library=library,
        stats=stats,
        method=method,
        query=query,
        top_k=4,
    )
    if not hits:
        console.print(f'[yellow]No passages mention "{query}".[/yellow]')
        return
    table = Table(title=f"Metrics report · {query}", show_lines=False)
    table.add_column("#", justify="right", width=3)
    table.add_column("Source")
    table.add_column("Metrics", overflow="fold")
    for idx, passage in enumerate(hits, start=1):
        metrics = " ".join(extract_metric_sentences(passage.text))
        if not metrics:
            metrics = summarize_passage_text(passage.text)
        metrics_text = build_summary_text(metrics, query)
        table.add_row(
            str(idx),
            pathlib.Path(passage.source_path).name,
            metrics_text,
        )
    console.print(table)


def report_summary_recent(
    library: List[DocumentIndex],
    state: AssistantState,
    index: int,
) -> None:
    rows = get_recent_doc_rows(library, state.recent_doc_ids)
    if not rows:
        console.print("[yellow]No recent documents to summarize yet.[/yellow]")
        return
    if index < 1 or index > len(rows):
        console.print(f"[red]Choose 1-{len(rows)}[/red]")
        return
    doc = rows[index - 1]
    summary = summarize_document(doc)
    console.print(Panel(summary, title=f"Summary: {doc.title}", border_style="green"))


# ----------------------------
# Anthropic client
# ----------------------------

def create_client() -> Anthropic:
    """Create Anthropic Claude client."""
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
    if not api_key:
        raise ValueError('ANTHROPIC_API_KEY not found. Set it with: setx ANTHROPIC_API_KEY "sk-ant-..." then reopen terminal.')
    return Anthropic(api_key=api_key)


# ----------------------------
# Chat loop UI
# ----------------------------

def show_help():
    """Display help panel with all commands."""
    console.print(Panel.fit(
        "\n".join([
            "[bold]Commands (work with or without slashes):[/bold]",
            "",
            "[cyan]Library Management:[/cyan]",
            "  add <path>           Add file/folder to library",
            f"  inbox [sync]         View or import files in {str(INBOX_DIR)}",
            "  watch_downloads ...  Auto-move new downloads into the inbox",
            "  library              Show library contents",
            "  rebuild_index        Rebuild search index",
            "",
            "[cyan]Search & Retrieval:[/cyan]",
            "  search <query>       Search for passages",
            "  search_method        Show/set BM25 or TF-IDF",
            "  cite <n>             Queue passage #n as citation",
            "  expand <n>           Queue passage #n with context",
            "  details <n>          Open the full paragraph for result #n",
            "",
            "[cyan]Modes & Templates:[/cyan]",
            "  modes                List available modes",
            "  mode <n>             Switch to mode (paper/assembly/variant)",
            "  templates            List templates",
            "  template <n>         Activate template",
            "",
            "[cyan]Quick Actions:[/cyan]",
            "  dissect              Auto-dissect paper (paper mode)",
            "  qc_report            Generate QC report (assembly mode)",
            "  eval_plan            Create eval plan (variant mode)",
            "  report metrics ...   Summarize metrics for a topic",
            "  recent               Show recently imported papers",
            "",
            "[cyan]Notes & Session:[/cyan]",
            "  notes                Show notes",
            "  note <text>          Add note",
            "  save                 Save session",
            "  clear                Clear conversation",
            "",
            "[cyan]Utility:[/cyan]",
            "  model                Show current model",
            "  help                 Show this help",
            "  exit                 Quit",
            "",
            "[dim]💡 Tips:[/dim]",
            "[dim]  - Commands work with or without '/' prefix[/dim]",
            "[dim]  - Try: 'search BRCA1' or '/search BRCA1'[/dim]",
            "[dim]  - Natural language works: 'find transformers', 'cite 1'[/dim]",
        ]),
        title="GenoScribe Commands",
        border_style="cyan"
    ))


def show_first_run_tutorial():
    """Show tutorial for first-time users."""
    console.print(Panel.fit(
        "\n".join([
            "[bold cyan]Welcome to GenoScribe![/bold cyan]",
            "",
            "[bold]Quick Start:[/bold]",
            f"1. [green]Drop PDFs into {str(INBOX_DIR)}[/green] or run [green]add ~/papers/[/green]",
            "2. [green]search BRCA1[/green]       ← Find relevant passages",
            "3. [green]cite 1[/green]             ← Queue evidence",
            "4. [green]Ask questions[/green]      ← Get evidence-based answers",
            "",
            "[bold]Example Session:[/bold]",
            "[dim]You:[/dim] add C:/Documents/genomics_papers/",
            "[dim]GenoScribe:[/dim] Added 10 documents.",
            "[dim]You:[/dim] search variant pathogenicity African",
            "[dim]GenoScribe:[/dim] [Shows 6 results]",
            "[dim]You:[/dim] cite 1",
            "[dim]GenoScribe:[/dim] Queued citation.",
            "[dim]You:[/dim] What pathogenicity thresholds are reported?",
            "[dim]Claude:[/dim] [Answers using your cited evidence]",
            "",
            "[yellow]Type 'help' anytime for full command list.[/yellow]",
        ]),
        title="First Time Setup",
        border_style="green"
    ))


def show_library_contents(library: List[DocumentIndex], max_display: int = 20):
    """Show current library contents."""
    if not library:
        console.print(f"[yellow]Your library is empty. Drop files into {str(INBOX_DIR)} or use 'add <path>'.[/yellow]")
        return
    
    table = Table(title=f"Your Library ({len(library)} documents)", show_lines=False)
    table.add_column("#", justify="right", width=4)
    table.add_column("Title", overflow="fold")
    table.add_column("Type", width=6)
    table.add_column("Passages", justify="right", width=10)
    
    for i, doc in enumerate(library[:max_display], 1):
        table.add_row(
            str(i),
            doc.title[:60] + "..." if len(doc.title) > 60 else doc.title,
            doc.ext.upper().replace(".", ""),
            str(len(doc.passages))
        )
    
    console.print(table)
    
    if len(library) > max_display:
        console.print(f"[dim]... and {len(library) - max_display} more documents[/dim]")


def add_path_to_library(
    path_str: str,
    idf_weights: Dict[str, float],
    copy_source: bool = False,
    delete_original: bool = False,
) -> List[DocumentIndex]:
    """
    Add file(s) to library.
    
    Returns number of documents successfully added.
    """
    cleaned = path_str.strip().strip("\"'") or path_str.strip()
    path = pathlib.Path(cleaned).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    files = []
    if path.is_dir():
        for ext in SUPPORTED_EXT:
            files.extend(path.rglob(f"*{ext}"))
    else:
        if path.suffix.lower() not in SUPPORTED_EXT:
            raise ValueError(f"Unsupported extension: {path.suffix}. Supported: {sorted(SUPPORTED_EXT)}")
        files = [path]

    added_docs: List[DocumentIndex] = []
    for f in files:
        ingest_path = f
        copied = False

        if copy_source:
            try:
                ingest_path = copy_into_library_store(f)
                copied = True
            except Exception as err:
                console.print(f"[red]Failed to copy {f.name} into the managed library:[/red] {err}")
                continue

        try:
            di = build_index_for_file(ingest_path, idf_weights)
            save_doc_index(di)
            added_docs.append(di)

            if copy_source and delete_original:
                try:
                    f.unlink(missing_ok=True)
                except OSError as err:
                    console.print(f"[yellow]Warning:[/yellow] Could not remove {f.name} from inbox: {err}")
        except Exception as e:
            console.print(f"[red]Failed to index {f.name}:[/red] {e}")
            if copy_source and copied:
                try:
                    ingest_path.unlink(missing_ok=True)
                except OSError:
                    pass
    extend_dense_index(added_docs)
    return added_docs


TIMING_LABELS = {
    "sparse_primary_ms": "BM25",
    "sparse_fallback_ms": "TF-IDF",
    "dense_ms": "Dense",
    "fusion_ms": "Fusion",
    "rerank_ms": "Rerank",
    "quality_filter_ms": "Filter",
}


def render_retrievals(passages: List[Passage], query: str = ""):
    """Display search results in a formatted table."""
    table = Table(title="Search Results", show_lines=True)
    table.add_column("#", justify="right", width=3)
    table.add_column("Source", overflow="fold")
    table.add_column("Location", width=12)
    table.add_column("Summary", overflow="fold")

    for i, p in enumerate(passages, start=1):
        loc = f"p.{p.page}" if p.page else "-"
        if p.is_table_or_figure:
            loc += " 📊"  # Emoji indicator for tables/figures
        summary_source = p.summary or p.text or ""
        summary = summarize_passage_text(summary_source)
        summary_text = build_summary_text(summary, query)
        if p.metrics:
            first = p.metrics[0]
            unit = first.get("unit") or ""
            metric_display = f"{first['label']}: {first['value']}{unit}"
            summary_text = f"{summary_text} [dim]{metric_display}[/dim]"
        table.add_row(str(i), pathlib.Path(p.source_path).name, loc, summary_text)

    console.print(table)


def render_timing_breakdown(timings: Dict[str, float]) -> None:
    if not timings:
        return
    parts: List[str] = []
    for key in ("sparse_primary_ms", "sparse_fallback_ms", "dense_ms", "fusion_ms", "rerank_ms", "quality_filter_ms"):
        value = timings.get(key)
        if value is None:
            continue
        label = TIMING_LABELS.get(key, key.replace("_ms", ""))
        parts.append(f"{label}: {value:.1f} ms")
    if parts:
        console.print(f"[dim]Retrieval timings: {' | '.join(parts)}[/dim]")


def build_metrics_panel(metrics: List[Dict[str, str]]) -> Panel:
    table = Table(show_header=True, title="Extracted metrics")
    table.add_column("Metric", justify="left", style="cyan")
    table.add_column("Value", justify="right")
    table.add_column("Unit", justify="left")
    table.add_column("Context", justify="left")
    for metric in metrics[:6]:
        table.add_row(
            metric.get("label", "-"),
            metric.get("value", "-"),
            metric.get("unit", ""),
            metric.get("text", "-"),
        )
    return Panel(table, border_style="cyan")


def main():
    """Main application loop."""
    ensure_dirs()
    
    try:
        client = create_client()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\nSet your API key with:")
        console.print('  Windows: setx ANTHROPIC_API_KEY "sk-ant-..."')
        console.print('  Mac/Linux: export ANTHROPIC_API_KEY="sk-ant-..."')
        return

    # Load library and statistics
    library = load_library()
    refresh_dense_index(library)
    stats = load_library_stats()
    repaired = library_requires_stats_rebuild()
    
    # Initialize or rebuild stats if needed
    if not stats or stats.total_docs != len(library) or repaired:
        if library:
            console.print("[yellow]Library stats missing or outdated. Rebuilding...[/yellow]")
            stats = rebuild_library_stats(library)
        else:
            stats = LibraryStats(
                idf_weights={},
                avg_doc_length=0.0,
                total_docs=0,
                total_passages=0,
                last_updated=now_ts()
            )
            save_library_stats(stats)
    
    state = load_state()

    if state.watch_downloads_enabled:
        moved_files = move_downloads_to_inbox()
        if moved_files:
            console.print(f"[dim]Moved {len(moved_files)} new file(s) from Downloads into the GenoScribe inbox.[/dim]")

    auto_imported_docs = sync_inbox(stats.idf_weights)
    if auto_imported_docs:
        library = load_library()
        refresh_dense_index(library)
        stats = rebuild_library_stats(library)
        record_recent_docs(state, auto_imported_docs)
        state.first_run_checklist["imported"] = True
        save_state(state)
        console.print(f"[green]✓ Imported {len(auto_imported_docs)} new document(s) from inbox.[/green]")
        show_recent_imports(library, state.recent_doc_ids)
        show_first_run_checklist(state.first_run_checklist)
    else:
        save_state(state)
    session_store = SessionStore()

    conversation: List[Dict[str, str]] = []
    pending_citations: List[Passage] = []
    last_evidence_sources: List[Passage] = []
    user_just_searched = False  # Track if user ran search in last command

    current_mode = DEFAULT_MODE
    active_template_name: Optional[str] = None
    search_method = DEFAULT_SEARCH_METHOD

    # Welcome message
    console.print(Panel.fit(
        f"[bold]GenoScribe - Production Edition[/bold]\n"
        f"Model: {MODEL}\n"
        f"Library: {len(library)} docs, {stats.total_passages} passages\n"
        f"Search: [cyan]{search_method.upper()}[/cyan]\n"
        f"✅ Hallucination guards active\n"
        f"✅ Natural language commands enabled\n"
        f"Type [bold]help[/bold] or [bold]/help[/bold] for commands.",
        title="Ready",
        border_style="green"
    ))
    console.print(f"[dim]Drop PDFs/TXT/MD into {str(INBOX_DIR)} to auto-import on launch or run 'inbox sync'.[/dim]")
    show_first_run_checklist(state.first_run_checklist)
    
    # Show tutorial if library is empty
    if len(library) == 0:
        show_first_run_tutorial()

    while True:
        try:
            user_input = console.input("\n[bold cyan]You:[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nGoodbye!")
            break

        if not user_input:
            continue

        # Parse command (works with or without slashes)
        command, args = parse_user_input(user_input)
        
        # Reset search flag (will be set to True if search command is executed)
        user_just_searched = False

        # ===== COMMAND HANDLING =====

        if command == "exit":
            console.print("Goodbye!")
            break

        if command == "help":
            show_help()
            continue

        if command == "model":
            console.print(f"Current model: [bold]{MODEL}[/bold]")
            continue

        # Library command
        if command == "library":
            show_library_contents(library)
            continue
        
        if command == "inbox":
            subcommand = args.strip().lower()
            pending_files = list_inbox_files()
            if not subcommand:
                show_inbox_queue(pending_files)
                console.print(f"[dim]Drop files into {str(INBOX_DIR)} and run 'inbox sync' to import immediately.[/dim]")
            elif subcommand in {"sync", "import", "process"}:
                new_docs = sync_inbox(stats.idf_weights if stats else {})
                if new_docs:
                    library = load_library()
                    refresh_dense_index(library)
                    stats = rebuild_library_stats(library)
                    record_recent_docs(state, new_docs)
                    state.first_run_checklist["imported"] = True
                    save_state(state)
                    console.print(f"[green]✓ Imported {len(new_docs)} document(s) from inbox.[/green]")
                    show_recent_imports(library, state.recent_doc_ids)
                else:
                    console.print(f"[yellow]No PDF/TXT/MD files waiting in {str(INBOX_DIR)}.[/yellow]")
            elif subcommand == "shortcut":
                shortcut = ensure_inbox_shortcut()
                console.print(f"[green]✓ Shortcut created on your Desktop:[/green] {shortcut}")
            else:
                console.print("[yellow]Usage: inbox [sync][/yellow]")
            continue

        if command == "watch_downloads":
            choice = args.strip().lower()
            downloads_path = get_downloads_dir()
            if choice in ("", "status"):
                status = "[green]enabled[/green]" if state.watch_downloads_enabled else "[red]disabled[/red]"
                console.print(f"Auto-watch Downloads is {status}. Folder: {downloads_path}")
                console.print("Use 'watch_downloads on' or 'watch_downloads off' to toggle.")
            elif choice == "on":
                state.watch_downloads_enabled = True
                save_state(state)
                console.print(f"[green]✓ Downloads folder watching enabled.[/green] New PDFs under {downloads_path} will auto-move into the inbox.")
            elif choice == "off":
                state.watch_downloads_enabled = False
                save_state(state)
                console.print("[green]✓ Downloads folder watching disabled.[/green]")
            else:
                console.print("[yellow]Usage: watch_downloads [on|off|status][/yellow]")
            continue

        if command == "details":
            if not args:
                console.print("[yellow]Specify which result to open: details <number>[/yellow]")
                continue
            if not state.last_retrievals:
                console.print("[yellow]No search context available yet. Run a search first.[/yellow]")
                continue
            try:
                idx = int(args)
            except ValueError:
                console.print("[red]Invalid number. Use: details <result #>[/red]")
                continue
            if idx < 1 or idx > len(state.last_retrievals):
                console.print(f"[red]Choose a number between 1 and {len(state.last_retrievals)}[/red]")
                continue
            passage = state.last_retrievals[idx - 1]
            title = pathlib.Path(passage.source_path).name
            panel_title = f"{title} · p.{passage.page or '-'} · chunk {passage.chunk_id}"
            meta_entries = [
                ("Source", title),
                ("Page", str(passage.page or "-")),
                ("Chunk", str(passage.chunk_id)),
                ("Doc ID", passage.doc_id or "-"),
                ("Type", "Table/Figure" if passage.is_table_or_figure else "Text"),
            ]
            meta_line = Text()
            for i, (label, value) in enumerate(meta_entries):
                if i:
                    meta_line.append("  |  ", style="dim")
                meta_line.append(f"{label}: ", style="dim")
                meta_line.append(value, style="bold")
            body_source = passage.raw_text or passage.text or ""
            blocks = build_detail_renderables(body_source, state.last_query or "")
            renderables: List[Any] = [meta_line, Text()]
            if passage.summary:
                renderables.append(Panel(passage.summary, title="Auto-summary", border_style="green"))
                renderables.append(Text())
            if passage.metrics:
                renderables.append(build_metrics_panel(passage.metrics))
                renderables.append(Text())
            if passage.is_table_or_figure:
                renderables.append(Text("[dim]Figure/table passage—showing caption + extracted metrics.[/dim]"))
                renderables.append(Text())
            renderables.extend(blocks)
            content = Group(*renderables)
            console.print(Panel(content, title=panel_title, border_style="blue"))
            continue

        if command == "recent":
            sub = args.strip()
            if not sub:
                show_recent_imports(library, state.recent_doc_ids)
                continue
            parts = sub.split(maxsplit=2)
            action = parts[0].lower()
            if action in {"ask", "query"}:
                if len(parts) < 3:
                    console.print("[yellow]Usage: recent ask <number> <question>[/yellow]")
                    continue
                try:
                    idx = int(parts[1])
                except ValueError:
                    console.print("[red]Recent index must be a number.[/red]")
                    continue
                question = parts[2].strip()
                rows = get_recent_doc_rows(library, state.recent_doc_ids)
                if not rows:
                    console.print("[yellow]No recent documents to query yet.[/yellow]")
                    continue
                if idx < 1 or idx > len(rows):
                    console.print(f"[red]Choose 1-{len(rows)}[/red]")
                    continue
                target_doc = rows[idx - 1]
                hits = run_search(
                    library=[target_doc],
                    stats=stats,
                    method=search_method,
                    query=question,
                    top_k=TOP_K_DEFAULT,
                )
                if not hits:
                    console.print(f'[yellow]No passages matched "{question}" in {target_doc.title}.[/yellow]')
                else:
                    state.last_retrievals = hits
                    state.last_query = question
                    save_state(state)
                    render_retrievals(hits, query=question)
                    console.print("[dim]Use 'details <n>' to read the full paragraph or 'cite <n>' to queue it.[/dim]")
                continue
            if action in {"summary", "summarize"}:
                rows = get_recent_doc_rows(library, state.recent_doc_ids)
                if not rows:
                    console.print("[yellow]No recent documents to summarize yet.[/yellow]")
                    continue
                idx = 1
                if len(parts) >= 2:
                    try:
                        idx = int(parts[1])
                    except ValueError:
                        console.print("[red]Recent index must be a number.[/red]")
                        continue
                if idx < 1 or idx > len(rows):
                    console.print(f"[red]Choose 1-{len(rows)}[/red]")
                    continue
                doc = rows[idx - 1]
                snippet = summarize_passage_text(doc.passages[0].text if doc.passages else doc.title)
                console.print(Panel(snippet, title=f"Summary: {doc.title}", border_style="green"))
                continue
            console.print("[yellow]Usage: recent [ask <n> <question> | summary <n>][/yellow]")
            continue

        if command == "report":
            if not args:
                console.print("[yellow]Usage: report metrics <query> | report summary [recent_index][/yellow]")
                continue
            parts = args.split(maxsplit=1)
            action = parts[0].lower()
            payload = parts[1] if len(parts) > 1 else ""
            if action == "metrics":
                if not payload:
                    console.print("[yellow]Provide a focus, e.g., report metrics varipred[/yellow]")
                    continue
                report_metrics_overview(library, stats, search_method, payload)
            elif action in {"summary", "summarize"}:
                idx = 1
                if payload:
                    try:
                        idx = int(payload)
                    except ValueError:
                        console.print("[red]Summary index must be numeric.[/red]")
                        continue
                report_summary_recent(library, state, idx)
            else:
                console.print("[yellow]Unknown report type. Try 'report metrics <query>' or 'report summary'.[/yellow]")
            continue

        if command == "sessions":
            snapshots = session_store.list_snapshots()
            if not snapshots:
                console.print("[yellow]No session snapshots found.[/yellow]")
            else:
                table = Table(title="Session Snapshots", show_lines=False)
                table.add_column("Name")
                table.add_column("Created")
                table.add_column("Messages", justify="right")
                table.add_column("Description")
                for snap in snapshots:
                    created_local = snap.created_at.astimezone().strftime("%Y-%m-%d %H:%M")
                    table.add_row(
                        snap.name,
                        created_local,
                        str(snap.message_count),
                        snap.description or "-",
                    )
                console.print(table)
            continue

        if command == "session_save":
            name, description = parse_session_save_args(args)
            if not name:
                console.print('[yellow]Provide a snapshot name: session save <name> [--desc "notes"][/yellow]')
                continue

            payload = build_snapshot_payload(
                conversation=conversation,
                working_notes=state.working_notes,
                mode=current_mode,
                template=active_template_name,
                search_method=search_method,
                pending_citations=pending_citations,
                last_evidence_sources=last_evidence_sources,
            )

            try:
                snapshot = session_store.save_snapshot(name, payload, description=description)
            except ValueError as e:
                console.print(f"[red]Error:[/red] {e}")
                continue

            if snapshot.overwritten:
                console.print("[yellow]Overwriting existing snapshot.[/yellow]")
            console.print(f"[green]âœ“ Snapshot saved:[/green] {snapshot.path}")
            continue

        if command == "session_load":
            target = args.strip()
            if not target:
                console.print("[yellow]Provide a snapshot name: session load <name>[/yellow]")
                continue

            try:
                snapshot = session_store.load_snapshot(target)
            except (ValueError, FileNotFoundError) as e:
                console.print(f"[red]Error:[/red] {e}")
                continue

            data = snapshot.payload or {}
            conversation.clear()
            conversation.extend(data.get("conversation", []))
            state.working_notes = list(data.get("working_notes", []))
            pending_citations = payload_to_passages(data.get("pending_citations", []))
            last_evidence_sources = payload_to_passages(data.get("last_evidence_sources", []))
            active_template_name = data.get("template")
            current_mode = data.get("mode", DEFAULT_MODE)
            search_method = data.get("search_method", DEFAULT_SEARCH_METHOD)
            state.last_retrievals = []
            state.last_query = ""
            save_state(state)

            system_note = (
                f"Session restored from snapshot '{snapshot.name}' created on "
                f"{snapshot.created_at.astimezone().strftime('%Y-%m-%d %H:%M')}"
            )
            conversation.append({"role": "system", "content": system_note})

            library_docs = {doc.doc_id: doc for doc in library}
            warn_about_missing_docs(pending_citations + last_evidence_sources, library_docs)

            console.print(f"[green]âœ“ Loaded snapshot:[/green] {snapshot.name}")
            continue

        if command == "session_delete":
            target = args.strip()
            if not target:
                console.print("[yellow]Provide a snapshot name: session delete <name>[/yellow]")
                continue
            try:
                session_store.delete_snapshot(target)
            except (ValueError, FileNotFoundError) as e:
                console.print(f"[red]Error:[/red] {e}")
                continue
            console.print(f"[green]âœ“ Deleted snapshot:[/green] {target.strip()}")
            continue

        # Search method command
        if command == "search_method":
            if not args:
                console.print(f"Current search method: [bold]{search_method.upper()}[/bold]")
                console.print("Available methods: [cyan]tfidf[/cyan], [cyan]bm25[/cyan]")
                console.print("\n💡 [bold]BM25[/bold] is recommended for genomics (handles repetition and length bias)")
            else:
                method = args.lower()
                if method in ["tfidf", "bm25"]:
                    search_method = method
                    console.print(f"[green]✓ Search method set to:[/green] {search_method.upper()}")
                else:
                    console.print("[red]Invalid method. Use 'tfidf' or 'bm25'[/red]")
            continue

        # Rebuild index command
        if command == "rebuild_index":
            if not library:
                console.print(f"[yellow]No documents in library. Drop files into {str(INBOX_DIR)} or use 'add <path>' first.[/yellow]")
                continue
            
            stats = rebuild_library_stats(library)
            refresh_dense_index(library)
            console.print("[green]✓ Index rebuilt successfully! Search quality improved.[/green]")
            continue

        # Add documents
        if command == "add":
            if not args:
                console.print(f"[yellow]Please specify a path (e.g., add ~/papers/) or drop files into {str(INBOX_DIR)} and run 'inbox sync'.[/yellow]")
                continue
            
            try:
                added_docs = add_path_to_library(args, stats.idf_weights)
                library = load_library()
                refresh_dense_index(library)

                if added_docs:
                    console.print(f"[green]✓ Added {len(added_docs)} document(s).[/green] Library now has {len(library)} docs.")
                    record_recent_docs(state, added_docs)
                    state.first_run_checklist["imported"] = True
                    save_state(state)
                    show_first_run_checklist(state.first_run_checklist)
                    console.print("[dim]Refreshing search weights for the updated library...[/dim]")
                    stats = rebuild_library_stats(library)
                    show_recent_imports(library, state.recent_doc_ids)
                else:
                    console.print("[yellow]No new documents added.[/yellow]")
            except FileNotFoundError as e:
                console.print(f"[red]Error:[/red] {e}")
            except Exception as e:
                console.print(f"[red]Failed to add documents:[/red] {e}")
            continue

        # Search
        if command == "search":
            if not args:
                console.print("[yellow]Please provide a search query.[/yellow]")
                console.print("Example: search BRCA1 pathogenic variants")
                continue
            
            if not library:
                console.print(f"[yellow]Your library is empty. Drop files into {str(INBOX_DIR)} or add a path:[/yellow]")
                console.print("  add ~/papers/")
                continue
            
            hits = run_search(
                library=library,
                stats=stats,
                method=search_method,
                query=args,
                top_k=TOP_K_DEFAULT,
            )
            
            state.last_retrievals = hits
            state.last_query = args
            save_state(state)
            user_just_searched = True  # Mark that search was run
            
            if not hits:
                console.print(f'[yellow]No matches found for:[/yellow] "{args}"')
                console.print("\n💡 Suggestions:")
                console.print(f'  - Check spelling: "{args}"')
                console.print("  - Try broader terms: 'protein' instead of 'transformer protein'")
                console.print("  - Use 'library' command to see what's indexed")
            else:
                render_retrievals(hits, query=args)
                console.print(f"[dim]Search method: {search_method.upper()} | Found {len(hits)} passages[/dim]")
                console.print("[dim]Use 'cite <n>' to queue a passage as evidence[/dim]")
                console.print("[dim]Use 'details <n>' to read the full paragraph before citing[/dim]")
                state.first_run_checklist["searched"] = True
                save_state(state)
                show_first_run_checklist(state.first_run_checklist)
            continue

        # Cite
        if command == "cite":
            if not args:
                console.print("[yellow]Specify which result to cite: cite <number>[/yellow]")
                console.print("Example: cite 1")
                continue
            
            if not state.last_retrievals:
                console.print("[yellow]No search results available. Run a search first:[/yellow]")
                console.print("  search <your query>")
                continue
            
            try:
                n = int(args)
                if n < 1 or n > len(state.last_retrievals):
                    console.print(f"[red]Invalid number. Choose 1-{len(state.last_retrievals)}[/red]")
                    continue
            except ValueError:
                console.print("[red]Invalid number. Use: cite <number>[/red]")
                continue
            
            p = state.last_retrievals[n - 1]
            pending_citations.append(p)
            console.print(f"[green]✓ Queued citation:[/green] {format_citation(p)}")
            console.print("[dim]Citation will be included in your next question to Claude[/dim]")
            state.first_run_checklist["cited"] = True
            save_state(state)
            show_first_run_checklist(state.first_run_checklist)
            continue

        # Expand
        if command == "expand":
            if not args:
                console.print("[yellow]Specify which result to expand: expand <number>[/yellow]")
                console.print("Example: expand 2")
                continue
            
            if not state.last_retrievals:
                console.print("[yellow]No search results available. Run a search first.[/yellow]")
                continue
            
            try:
                n = int(args)
                if n < 1 or n > len(state.last_retrievals):
                    console.print(f"[red]Invalid number. Choose 1-{len(state.last_retrievals)}[/red]")
                    continue
            except ValueError:
                console.print("[red]Invalid number. Use: expand <number>[/red]")
                continue
            
            p = state.last_retrievals[n - 1]
            neighbors = expand_passage(library, p, radius=1)
            pending_citations.extend(neighbors)
            console.print(f"[green]✓ Queued {len(neighbors)} chunks (with context)[/green]")
            console.print(f"[dim]Includes passages before and after: {format_citation(p)}[/dim]")
            continue

        # Templates
        if command == "templates":
            console.print(Panel(
                "\n".join(f"[bold]{i+1}. {name}[/bold]" for i, name in enumerate(TEMPLATES.keys())),
                title="Available Templates"
            ))
            console.print("\n[dim]Use 'template <n>' to activate, 'template off' to disable[/dim]")
            continue

        if command == "template":
            if args == "off":
                active_template_name = None
                console.print("[green]✓ Template disabled.[/green]")
            elif args == "":
                if active_template_name:
                    console.print(f"[cyan]Active template:[/cyan] {active_template_name}")
                else:
                    console.print("[yellow]No template active. Use 'templates' to list available templates.[/yellow]")
            else:
                try:
                    idx = int(args) - 1
                    name = list(TEMPLATES.keys())[idx]
                    active_template_name = name
                    console.print(f"[green]✓ Template activated:[/green] {name}")
                except (ValueError, IndexError):
                    console.print("[red]Invalid template number. Use 'templates' to list.[/red]")
            continue

        # Modes
        if command == "modes":
            console.print(Panel(
                "\n".join(f"[bold]{i+1}. {m}[/bold]" + (" ← current" if m == current_mode else "")
                          for i, m in enumerate(MODE_ORDER)),
                title="Available Modes"
            ))
            console.print("\n[dim]Use 'mode <n>' to switch modes[/dim]")
            continue

        if command == "mode":
            if not args:
                console.print(f"[cyan]Current mode:[/cyan] {current_mode}")
                console.print("[dim]Use 'modes' to list all modes, 'mode <n>' to switch[/dim]")
            else:
                arg_clean = args.strip()
                mode_changed = False
                if arg_clean.isdigit():
                    try:
                        idx = int(arg_clean) - 1
                        current_mode = MODE_ORDER[idx]
                        mode_changed = True
                    except (ValueError, IndexError):
                        console.print("[red]Invalid mode number. Use 'modes' to list.[/red]")
                else:
                    normalized = arg_clean.lower()
                    if normalized in MODE_ORDER:
                        current_mode = normalized
                        mode_changed = True
                    else:
                        console.print("[red]Unknown mode. Use 'modes' to list available names or numbers.[/red]")
                if mode_changed:
                    console.print(f"[green]✓ Mode switched to:[/green] {current_mode}")
            continue

        # One-shot commands (dissect, qc_report, eval_plan)
        if command == "dissect":
            if current_mode != "paper":
                console.print("[yellow]Switching to paper mode for dissection...[/yellow]")
                current_mode = "paper"

            evidence_to_use: List[Passage] = last_evidence_sources[:]
            if not evidence_to_use and state.last_retrievals:
                evidence_to_use = state.last_retrievals[:4]

            mode_query = args or state.last_query or ""
            synthesis_text, pipeline_passages, pipeline_warnings, pipeline_timings = run_mode_pipeline(
                mode="paper",
                query=mode_query,
                library=library,
                stats=stats,
                search_method=search_method,
                base_passages=evidence_to_use,
                context={"title": mode_query or "Paper synthesis"},
            )
            structured_summary = synthesis_text
            if pipeline_passages and not evidence_to_use:
                evidence_to_use = pipeline_passages[:4]
            if synthesis_text:
                console.print(Panel(synthesis_text, title="GenoScribe synthesis", expand=False))
            for warn in pipeline_warnings:
                console.print(f"[yellow]Pipeline warning:[/yellow] {warn}")
            render_timing_breakdown(pipeline_timings)

            if not evidence_to_use:
                console.print("[red]No evidence available.[/red]")
                console.print("Run: search <query>, then: cite <n>")
                continue

            evidence_block = build_evidence_block(evidence_to_use, max_items=6)

            composed = (
                "Auto-dissect this paper using ONLY the Evidence excerpts.\n"
                "Follow the paper_dissect template structure.\n\n"
                "Evidence excerpts:\n"
                f"{evidence_block}\n"
            )
            if structured_summary:
                composed += "\nPipeline summary (structured template):\n" + structured_summary + "\n"


            if STRICT_ON_CITE and evidence_block:
                composed += (
                    "\nAUDIT-GRADE RULES:\n"
                    "- Use ONLY Evidence excerpts for factual claims.\n"
                    "- If something is not in the excerpts, write Unknown.\n"
                )

            conversation.append({"role": "user", "content": composed})

            try:
                resp = client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=MODE_PROMPTS[current_mode],
                    messages=conversation,
                )
                assistant_text = resp.content[0].text
                conversation.append({"role": "assistant", "content": assistant_text})
                
                # Validate response
                is_safe, warning = validate_model_response(assistant_text, True, len(library), evidence_to_use)
                if not is_safe:
                    console.print(f"\n[red]{warning}[/red]\n")
                
                console.print(f"[bold green]Claude:[/bold green] {assistant_text}\n")
                display_evidence_context(evidence_to_use)
                display_evidence_context(evidence_to_use)
                display_evidence_context(evidence_to_use)
            except Exception as e:
                console.print(f"[red]Error:[/red] {e}")
            continue

        if command == "qc_report":
            if current_mode != "assembly":
                console.print("[yellow]Switching to assembly mode...[/yellow]")
                current_mode = "assembly"

            evidence_to_use: List[Passage] = last_evidence_sources[:]
            if not evidence_to_use and state.last_retrievals:
                evidence_to_use = state.last_retrievals[:4]

            assembly_query = args or state.last_query or ""
            synthesis_text, pipeline_passages, pipeline_warnings, pipeline_timings = run_mode_pipeline(
                mode="assembly",
                query=assembly_query,
                library=library,
                stats=stats,
                search_method=search_method,
                base_passages=evidence_to_use,
                context={"sample_id": assembly_query or None},
            )
            structured_summary = synthesis_text
            if pipeline_passages and not evidence_to_use:
                evidence_to_use = pipeline_passages[:4]
            if synthesis_text:
                console.print(Panel(synthesis_text, title="Assembly evidence synthesis", expand=False))
            for warn in pipeline_warnings:
                console.print(f"[yellow]Pipeline warning:[/yellow] {warn}")
            render_timing_breakdown(pipeline_timings)

            if not evidence_to_use:
                console.print("[red]No evidence available.[/red]")
                console.print("📊 Tip: Add QUAST/BUSCO reports, search for metrics, then cite them")
                continue

            evidence_block = build_evidence_block(evidence_to_use, max_items=6)

            composed = (
                "Draft a lab-ready Assembly QC report using ONLY the Evidence excerpts.\n"
                "Structure:\n"
                "1) Assembly Snapshot\n"
                "2) QC Metrics & Interpretation\n"
                "3) Pass/Fail flags\n"
                "4) Recommended next steps\n"
                "5) Reproducible commands checklist\n\n"
                "Evidence excerpts:\n"
                f"{evidence_block}\n"
            )
            if structured_summary:
                composed += "\nPipeline summary (structured template):\n" + structured_summary + "\n"


            if STRICT_ON_CITE and evidence_block:
                composed += (
                    "\nAUDIT-GRADE RULES:\n"
                    "- Do not invent metrics not shown in Evidence excerpts.\n"
                    "- If a metric/value is missing, write Unknown.\n"
                )

            conversation.append({"role": "user", "content": composed})

            try:
                resp = client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=MODE_PROMPTS[current_mode],
                    messages=conversation,
                )
                assistant_text = resp.content[0].text
                conversation.append({"role": "assistant", "content": assistant_text})
                
                # Validate response
                is_safe, warning = validate_model_response(assistant_text, True, len(library), evidence_to_use)
                if not is_safe:
                    console.print(f"\n[red]{warning}[/red]\n")
                
                console.print(f"[bold green]Claude:[/bold green] {assistant_text}\n")
            except Exception as e:
                console.print(f"[red]Error:[/red] {e}")
            continue

        if command == "eval_plan":
            if current_mode != "variant":
                console.print("[yellow]Switching to variant mode...[/yellow]")
                current_mode = "variant"

            evidence_to_use: List[Passage] = last_evidence_sources[:]
            if not evidence_to_use and state.last_retrievals:
                evidence_to_use = state.last_retrievals[:4]

            variant_query = args or state.last_query or ""
            synthesis_text, pipeline_passages, pipeline_warnings, pipeline_timings = run_mode_pipeline(
                mode="variant",
                query=variant_query,
                library=library,
                stats=stats,
                search_method=search_method,
                base_passages=evidence_to_use,
                context={"variant_id": variant_query or "variant"},
            )
            structured_summary = synthesis_text
            if pipeline_passages and not evidence_to_use:
                evidence_to_use = pipeline_passages[:4]
            if synthesis_text:
                console.print(Panel(synthesis_text, title="Variant evidence synthesis", expand=False))
            for warn in pipeline_warnings:
                console.print(f"[yellow]Pipeline warning:[/yellow] {warn}")
            render_timing_breakdown(pipeline_timings)

            evidence_block = build_evidence_block(evidence_to_use, max_items=6) if evidence_to_use else ""

            composed = (
                "Create a leakage-safe, ancestry-aware evaluation plan for a variant pathogenicity model.\n"
                "Include:\n"
                "- Data splitting strategy\n"
                "- Baselines\n"
                "- Metrics (AUC, PR-AUC, calibration, subgroup metrics)\n"
                "- Ancestry-stratified reporting requirements\n"
                "- External validation plan\n"
                "- Reproducibility checklist\n"
            )
            if structured_summary:
                composed += "\nPipeline summary (structured template):\n" + structured_summary + "\n"


            if evidence_block:
                composed += "\n\nEvidence excerpts:\n" + evidence_block + "\n"
                if STRICT_ON_CITE:
                    composed += (
                        "\nAUDIT-GRADE RULES:\n"
                        "- If you reference specifics from the study, cite them.\n"
                        "- If not supported by Evidence excerpts, label as general best practice.\n"
                    )

            conversation.append({"role": "user", "content": composed})

            try:
                resp = client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=MODE_PROMPTS[current_mode],
                    messages=conversation,
                )
                assistant_text = resp.content[0].text
                conversation.append({"role": "assistant", "content": assistant_text})
                
                # Validate response
                is_safe, warning = validate_model_response(assistant_text, evidence_block != "", len(library), evidence_to_use)
                if not is_safe:
                    console.print(f"\n[red]{warning}[/red]\n")
                
                console.print(f"[bold green]Claude:[/bold green] {assistant_text}\n")
            except Exception as e:
                console.print(f"[red]Error:[/red] {e}")
            continue

        # Notes
        if command == "notes":
            if not state.working_notes:
                console.print("[yellow]No working notes yet.[/yellow]")
                console.print("[dim]Use 'note <text>' to add notes[/dim]")
            else:
                console.print(Panel(
                    "\n".join(f"{i+1}. {n}" for i, n in enumerate(state.working_notes)),
                    title=f"Working Notes ({len(state.working_notes)})"
                ))
            continue

        if command == "note":
            if not args:
                console.print("[yellow]Please provide note text: note <your note>[/yellow]")
                continue
            
            state.working_notes.append(args)
            save_state(state)
            console.print(f'[green]✓ Note saved:[/green] "{args[:60]}..."' if len(args) > 60 else f'[green]✓ Note saved:[/green] "{args}"')
            continue

        if command == "clear":
            conversation.clear()
            pending_citations.clear()
            console.print("[green]✓ Cleared conversation history.[/green]")
            console.print("[dim]Library and notes preserved[/dim]")
            continue

        if command == "save":
            out = OUTPUT_DIR / f"session_{now_ts()}.json"
            payload = {
                "model": MODEL,
                "mode": current_mode,
                "template": active_template_name,
                "search_method": search_method,
                "conversation": conversation,
                "working_notes": state.working_notes,
            }
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            console.print(f"[green]✓ Saved session to:[/green] {out}")
            continue

        # ===== CHAT (Conversation with Claude) =====
        
        if command == "chat":
            # Build "evidence pack" from queued citations
            evidence_block = ""
            evidence_sources: List[Passage] = []
            if pending_citations:
                evidence_sources = pending_citations[-6:]
                evidence_block = build_evidence_block(evidence_sources, max_items=6)
                pending_citations.clear()

            # Remember last evidence sources (so one-shot commands can reuse)
            if evidence_sources:
                last_evidence_sources = evidence_sources[:]
            auto_search_triggered = False

            # If no evidence was provided, automatically search the library with the question text
            if not evidence_sources and library and args:
                auto_hits = run_search(
                    library=library,
                    stats=stats,
                    method=search_method,
                    query=args,
                    top_k=TOP_K_DEFAULT,
                )
                if auto_hits:
                    auto_search_triggered = True
                    evidence_sources = auto_hits[:6]
                    evidence_block = build_evidence_block(evidence_sources, max_items=6)
                    state.last_retrievals = auto_hits
                    state.last_query = args
                    save_state(state)
                    last_evidence_sources = evidence_sources[:]
                    console.print(
                        f'[dim]Auto-searched your library for "{args[:60]}" and queued the top passages.[/dim]'
                    )
                    render_retrievals(evidence_sources, query=args)
                    console.print("[dim]Use 'details <n>' for context or 'cite <n>' to reference a passage.[/dim]")
                elif looks_like_library_overview_request(args):
                    fallback_sources: List[Passage] = []
                    for doc in library:
                        if not doc.passages:
                            continue
                        fallback_sources.append(doc.passages[0])
                        if len(fallback_sources) >= TOP_K_DEFAULT:
                            break
                    if fallback_sources:
                        evidence_sources = fallback_sources
                        evidence_block = build_evidence_block(evidence_sources, max_items=6)
                        state.last_retrievals = fallback_sources
                        state.last_query = args
                        save_state(state)
                        last_evidence_sources = fallback_sources[:]
                        console.print(
                            "[dim]No direct retrieval matches; using the opening passage from each document as context.[/dim]"
                        )

            # Add working notes context (short)
            notes_block = ""
            if state.working_notes:
                recent_notes = state.working_notes[-8:]
                notes_block = "Working notes (user-curated):\n" + "\n".join(f"- {n}" for n in recent_notes)

            # Compose user message with attachments
            composed = args  # The actual user input
            if notes_block:
                composed += "\n\n" + notes_block
            if evidence_block:
                composed += "\n\nEvidence excerpts:\n" + evidence_block

            # Apply template (if active)
            if active_template_name:
                composed += "\n\nTEMPLATE INSTRUCTIONS:\n" + TEMPLATES[active_template_name]

            # Automatically enforce strict evidence discipline when evidence is attached
            if STRICT_ON_CITE and evidence_block:
                composed += (
                    "\n\nAUDIT-GRADE RULES:\n"
                    "- Use the Evidence excerpts as the only primary evidence.\n"
                    "- Separate evidence-backed claims from background definitions.\n"
                    "- If something is not supported by Evidence excerpts, label it Unknown or place it under 'Background (not from cited text)'.\n"
                    "- Prefer structured outputs (tables/checklists) when helpful.\n"
                )

            # Conversation memory
            conversation.append({"role": "user", "content": composed})

            try:
                resp = client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=MODE_PROMPTS[current_mode],
                    messages=conversation,
                )
                assistant_text = resp.content[0].text
                conversation.append({"role": "assistant", "content": assistant_text})
                
                # CRITICAL: Validate response for hallucinations
                has_evidence = evidence_block != ""
                is_safe, warning = validate_model_response(
                    assistant_text,
                    has_evidence or user_just_searched or auto_search_triggered,
                    len(library),
                    evidence_sources,
                )
                
                if not is_safe and warning:
                    console.print(f"\n[bold red]{warning}[/bold red]\n")
                
                console.print(f"[bold green]Claude:[/bold green] {assistant_text}\n")
                display_evidence_context(evidence_sources)

            except Exception as e:
                console.print(f"[red]Error calling Claude API:[/red] {e}")


if __name__ == "__main__":
    main()
