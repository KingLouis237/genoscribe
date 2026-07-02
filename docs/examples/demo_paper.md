# GenoScribe-Scout: A Synthetic Genomics Methods Benchmark

## Abstract

GenoScribe-Scout is a synthetic genomics methods paper created only for the public GenoScribe demo. It evaluates whether an evidence-review pipeline can retrieve method claims, extract simple benchmark metrics, and surface limitations with provenance. The study uses simulated sequence annotations and simulated benchmark labels. It does not contain real patient data, clinical records, diagnostic claims, or pathogenicity interpretations.

## Method

GenoScribe-Scout combines lexical retrieval, dense passage embeddings, and structured evidence assembly to review short genomics methods documents. The method is intended to test evidence traceability rather than clinical performance.

The synthetic benchmark contains 120 simulated gene-method passages. Each passage was assigned a non-clinical relevance label by the demo authors. Labels indicate whether the passage discusses benchmark evidence, method limitations, or unrelated technical background.

## Synthetic Benchmark Results

The benchmark compares GenoScribe-Scout against two simple baselines. All numbers are synthetic and are included only to exercise metric extraction.

| Method | AUROC | AUPRC | Accuracy | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Keyword Baseline | 0.71 | 0.64 | 0.68 | 0.66 | 0.62 | 0.64 |
| Dense Baseline | 0.82 | 0.77 | 0.76 | 0.74 | 0.79 | 0.76 |
| GenoScribe-Scout | 0.89 | 0.84 | 0.81 | 0.83 | 0.80 | 0.81 |

GenoScribe-Scout had the highest AUROC and AUPRC in this synthetic benchmark. The evidence supports only the claim that the method performed best on this toy benchmark. It does not support claims about clinical utility, disease diagnosis, or variant pathogenicity.

## Limitations

This demo benchmark is intentionally small and synthetic. It does not test noisy OCR, scanned figures, supplementary spreadsheets, non-English papers, or real-world publication bias. The labels were created for demonstration and should not be treated as independent scientific evidence.

The method may miss metrics when values appear only in figures, captions, or narrative text without clear labels. It may also surface insufficient evidence when a query asks for unsupported clinical conclusions.

## Non-Clinical Use Statement

GenoScribe-Scout is not a clinical tool. The demo does not provide medical advice, clinical interpretation, diagnostic recommendations, or variant pathogenicity classification.
