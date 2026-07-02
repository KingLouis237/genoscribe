from __future__ import annotations

from genoscribe import retrieval_hybrid as rh
from genoscribe.retrieval_hybrid import infer_target_doc_ids
from genoscribe.schemas.document import DocumentIndex


def _doc(*, doc_id: str, source_path: str, title: str) -> DocumentIndex:
    return DocumentIndex(
        doc_id=doc_id,
        source_path=source_path,
        ext=".pdf",
        title=title,
        passages=[],
        vectors=[],
        term_counts=[],
        doc_lengths=[],
        doc_type="paper",
    )


def test_infer_target_prefers_exact_title_not_generic_model_tokens() -> None:
    library = [
        _doc(
            doc_id="Gene-Pathogenicity-Prediction-using-Genomic-Foundation-Models_2026-03-09_18-50-46-1773078646",
            source_path="Gene-Pathogenicity-Prediction-using-Genomic-Foundation-Models_2026-03-09_18-50-46.pdf",
            title="Gene Pathogenicity Prediction using Genomic Foundation Models",
        ),
        _doc(
            doc_id="Evolutionary-scale_prediction_of_atomic_level_protein_structure_with_a_language_model_2026-03-09_18-53-12-1773078792",
            source_path="Evolutionary-scale_prediction_of_atomic_level_protein_structure_with_a_language_model_2026-03-09_18-53-12.pdf",
            title="Evolutionary-scale prediction of atomic level protein structure with a language model",
        ),
    ]
    query = "In the Gene Pathogenicity Prediction using Genomic Foundation Models paper, summarize results."
    targets = infer_target_doc_ids(query, library)
    assert targets == [
        "Gene-Pathogenicity-Prediction-using-Genomic-Foundation-Models_2026-03-09_18-50-46-1773078646"
    ]


def test_infer_target_uses_doi_aliases() -> None:
    library = [
        _doc(
            doc_id="PLOSGenetics_10.1371_journal.pgen.1011540-1776346750",
            source_path="PLOSGenetics_10.1371_journal.pgen.1011540.pdf",
            title="PLOS Genetics DOI 10.1371/journal.pgen.1011540",
        )
    ]
    query = "In PLOS Genetics DOI 10.1371/journal.pgen.1011540, what metrics are reported?"
    targets = infer_target_doc_ids(query, library)
    assert targets == ["PLOSGenetics_10.1371_journal.pgen.1011540-1776346750"]


def test_infer_target_keeps_surname_style_alias_for_scoped_queries() -> None:
    library = [
        _doc(
            doc_id="papadimitriou-et-al-2019-predicting-disease-causing-variant-combinations_1__2026-03-09_18-53-49-1773772719",
            source_path="papadimitriou-et-al-2019-predicting-disease-causing-variant-combinations_1__2026-03-09_18-53-49.pdf",
            title="Predicting disease-causing variant combinations",
        )
    ]
    query = "In the papadimitriou paper, summarize the main findings."
    targets = infer_target_doc_ids(query, library)
    assert targets == [
        "papadimitriou-et-al-2019-predicting-disease-causing-variant-combinations_1__2026-03-09_18-53-49-1773772719"
    ]


def test_infer_target_uses_manifest_scope_alias_for_deictic_benchmark_query(monkeypatch) -> None:
    gene_doc_id = "Gene-Pathogenicity-Prediction-using-Genomic-Foundation-Models_2026-03-09_18-50-46-1773078646"
    library = [
        _doc(
            doc_id=gene_doc_id,
            source_path="Gene-Pathogenicity-Prediction-using-Genomic-Foundation-Models_2026-03-09_18-50-46.pdf",
            title="Gene Pathogenicity Prediction using Genomic Foundation Models",
        ),
        _doc(
            doc_id="other_doc",
            source_path="Other.pdf",
            title="Other benchmark paper",
        ),
    ]
    monkeypatch.setattr(
        rh,
        "_manifest_scope_aliases_for_library",
        lambda _: {gene_doc_id: ("benchmark paper nucleotide transformer hyenadna genalm",)},
    )
    query = (
        "Does this benchmark paper support the claim that Nucleotide Transformer "
        "outperforms HyenaDNA and GenaLM in this evaluation?"
    )
    targets = infer_target_doc_ids(query, library)
    assert targets == [gene_doc_id]


def test_infer_target_uses_manifest_scope_alias_for_deictic_plos_query(monkeypatch) -> None:
    plos_doc_id = "PLOSGenetics_10.1371_journal.pgen.1011540-1776346750"
    library = [
        _doc(
            doc_id=plos_doc_id,
            source_path="PLOSGenetics_10.1371_journal.pgen.1011540.pdf",
            title="PLOS Genetics DOI 10.1371/journal.pgen.1011540",
        ),
        _doc(
            doc_id="other_doc",
            source_path="Other.pdf",
            title="Other paper",
        ),
    ]
    monkeypatch.setattr(
        rh,
        "_manifest_scope_aliases_for_library",
        lambda _: {plos_doc_id: ("this plos paper",)},
    )
    targets = infer_target_doc_ids("In this PLOS paper, summarize the main evidence claims.", library)
    assert targets == [plos_doc_id]


def test_infer_target_prefers_unresolved_for_deictic_weak_only_matches(monkeypatch) -> None:
    library = [
        _doc(
            doc_id="Varcopp_Nassim_2026-03-09_18-53-41-1773078821",
            source_path="Varcopp_Nassim_2026-03-09_18-53-41.pdf",
            title="VarCoPP",
        )
    ]
    monkeypatch.setattr(rh, "_manifest_scope_aliases_for_library", lambda _: {})
    targets = infer_target_doc_ids(
        "What limitations or uncertainty are reported for VarCoPP predictions in this paper?",
        library,
    )
    assert targets == []
