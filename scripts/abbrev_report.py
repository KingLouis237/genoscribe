import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from genoscribe.config import OUTPUT_DIR
from genoscribe.ingestion.abbrev_utils import extract_short_tokens, suggested_long_form
from genoscribe.retrieval_hybrid import SHORT_TOKEN_WHITELIST
from genoscribe.storage.provenance_store import load_library

MAX_CONTEXTS = 5


def collect_candidates() -> list[dict]:
    library = load_library()
    stats: dict[str, dict] = {}

    for doc in library:
        doc_mode = getattr(doc, "doc_type", "paper") or "paper"
        for passage in doc.passages:
            text = passage.text or ""
            tokens = passage.short_tokens or extract_short_tokens(text)
            if not tokens:
                continue
            snippet = (passage.summary or text).strip()
            for token in tokens:
                entry = stats.setdefault(
                    token,
                    {
                        "frequency": 0,
                        "doc_counts": Counter(),
                        "mode_counts": Counter(),
                        "contexts": [],
                    },
                )
                entry["frequency"] += 1
                entry["doc_counts"][doc.doc_id] += 1
                entry["mode_counts"][doc_mode] += 1
                if len(entry["contexts"]) < MAX_CONTEXTS:
                    entry["contexts"].append(
                        {
                            "doc_id": doc.doc_id,
                            "chunk_id": passage.chunk_id,
                            "context": snippet[:200],
                        }
                    )

    candidates = []
    for token, info in sorted(stats.items(), key=lambda kv: kv[1]["frequency"], reverse=True):
        freq = info["frequency"]
        mode_counts = info["mode_counts"]
        total = sum(mode_counts.values())
        mode_distribution = dict(mode_counts)
        dominant_fraction = max((count / total for count in mode_counts.values()), default=0.0)
        confidence = round(min(1.0, 0.3 + 0.5 * dominant_fraction + 0.02 * min(freq, 25)), 3)
        doc_distribution = dict(info["doc_counts"].most_common(10))
        candidates.append(
            {
                "token": token,
                "frequency": freq,
                "doc_distribution": doc_distribution,
                "mode_distribution": mode_distribution,
                "sample_contexts": info["contexts"],
                "long_form_hint": suggested_long_form(token),
                "confidence": confidence,
                "review_for_promotion": token not in SHORT_TOKEN_WHITELIST and freq >= 3,
            }
        )
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate abbreviation candidate report.")
    parser.add_argument("--min-frequency", type=int, default=2, help="Minimum frequency to include in report.")
    args = parser.parse_args()

    candidates = [c for c in collect_candidates() if c["frequency"] >= args.min_frequency]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_DIR / "abbrev"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"abbrev_candidates_{timestamp}.json"
    payload = {
        "generated_at": timestamp,
        "min_frequency": args.min_frequency,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[abbrev] Saved candidate report to {path}")


if __name__ == "__main__":
    main()
