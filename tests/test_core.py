from __future__ import annotations

import spmkit_data_hunter as hunter


def test_compound_suffixes() -> None:
    assert hunter.full_suffix("curve.jpk-force") == ".jpk-force"
    assert hunter.full_suffix("dataset.tar.gz") == ".tar.gz"


def test_normalize_doi_and_github_url() -> None:
    assert hunter.normalize_doi("https://doi.org/10.5281/Zenodo.123.") == "10.5281/zenodo.123"
    assert hunter.normalize_url("http://www.github.com/kegouro/spmkit-data-hunter.git/tree/main?tab=readme", github_root=True) == "https://github.com/kegouro/spmkit-data-hunter"


def test_merge_records_combines_equivalent_evidence() -> None:
    first = hunter.DatasetRecord(
        source="zenodo",
        source_id="1",
        title="AFM benchmark",
        doi="10.5281/zenodo.123",
        landing_url="https://zenodo.org/records/1",
        files=[hunter.FileAsset.build(name="raw.nid", url="https://example.org/raw")],
        matched_query="AFM raw",
    )
    second = hunter.DatasetRecord(
        source="figshare",
        source_id="2",
        title="AFM benchmark",
        doi="DOI: 10.5281/ZENODO.123",
        landing_url="https://figshare.com/articles/dataset/2",
        files=[hunter.FileAsset.build(name="results.csv", url="https://example.org/results")],
        matched_query="AFM processed",
    )

    merged = hunter.merge_records([first, second])

    assert len(merged) == 1
    assert {asset.name for asset in merged[0].files} == {"raw.nid", "results.csv"}
    assert merged[0].matched_query == "AFM raw | AFM processed"


def test_file_classification() -> None:
    assert "raw" in hunter.infer_categories("sample_raw.nid")
    assert "processed" in hunter.infer_categories("roughness_results.csv")
    assert "code" in hunter.infer_categories("analysis.ipynb")
    assert "documentation" in hunter.infer_categories("README.md")
    assert "archive" in hunter.infer_categories("all_data.zip")


def test_gold_record_scoring() -> None:
    record = hunter.DatasetRecord(
        source="test",
        source_id="1",
        title="AFM raw and processed force spectroscopy benchmark",
        description=(
            "Includes calibration, cantilever spring constant, scripts "
            "and processed Young modulus results."
        ),
        doi="10.0000/example",
        license="CC-BY-4.0",
        related_identifiers=[
            {
                "identifier": "10.0000/paper",
                "relation": "isSupplementTo",
                "scheme": "doi",
            }
        ],
        files=[
            hunter.FileAsset.build(
                name="raw_curves.jpk-force",
                url="https://example.org/raw_curves.jpk-force",
            ),
            hunter.FileAsset.build(
                name="processed_results.csv",
                url="https://example.org/processed_results.csv",
            ),
            hunter.FileAsset.build(
                name="analysis.ipynb",
                url="https://example.org/analysis.ipynb",
            ),
            hunter.FileAsset.build(
                name="README.md",
                url="https://example.org/README.md",
            ),
        ],
    )

    hunter.score_record(record)

    assert record.level == "gold"
    assert record.score >= 72
