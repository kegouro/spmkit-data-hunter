from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import spmkit_data_hunter as hunter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _record(**kwargs):
    defaults = {
        "source": "test",
        "source_id": "1",
        "title": "Test",
    }
    defaults.update(kwargs)
    return hunter.DatasetRecord(**defaults)


def _file(name, url=None):
    return hunter.FileAsset.build(
        name=name,
        url=url or f"https://example.org/{name}",
    )


# ---------------------------------------------------------------------------
# File classification
# ---------------------------------------------------------------------------


def test_compound_suffixes() -> None:
    assert hunter.full_suffix("curve.jpk-force") == ".jpk-force"
    assert hunter.full_suffix("dataset.tar.gz") == ".tar.gz"


def test_normalize_doi_and_github_url() -> None:
    assert hunter.normalize_doi("https://doi.org/10.5281/Zenodo.123.") == "10.5281/zenodo.123"
    assert (
        hunter.normalize_url(
            "http://www.github.com/kegouro/spmkit-data-hunter.git/tree/main?tab=readme",
            github_root=True,
        )
        == "https://github.com/kegouro/spmkit-data-hunter"
    )


def test_file_classification() -> None:
    assert "raw" in hunter.infer_categories("sample_raw.nid")
    assert "processed" in hunter.infer_categories("roughness_results.csv")
    assert "code" in hunter.infer_categories("analysis.ipynb")
    assert "documentation" in hunter.infer_categories("README.md")
    assert "archive" in hunter.infer_categories("all_data.zip")


# ---------------------------------------------------------------------------
# merge_records
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Domain relevance gate
# ---------------------------------------------------------------------------


def test_strong_phrase_approves() -> None:
    rec = _record(
        title="Atomic force microscopy topography dataset",
        files=[_file("raw_data.csv"), _file("results.csv")],
    )
    hunter.score_record(rec)
    assert rec.domain_relevant is True


def test_native_extension_approves() -> None:
    rec = _record(
        title="Surface characterization measurements",
        files=[_file("sample.nid")],
    )
    hunter.score_record(rec)
    assert rec.domain_relevant is True
    assert rec.relevance_score >= 60


def test_jpk_force_approves() -> None:
    rec = _record(
        title="Force curves",
        files=[_file("force_curves.jpk-force")],
    )
    hunter.score_record(rec)
    assert rec.domain_relevant is True


def test_kpfm_phrase_approves() -> None:
    rec = _record(
        title="Kelvin probe force microscopy surface potential measurements",
        description="KPFM data with surface potential maps.",
    )
    hunter.score_record(rec)
    assert rec.domain_relevant is True


def test_contextual_two_families_approves() -> None:
    rec = _record(
        title="AFM topography processed with Gwyddion",
        files=[_file("data.csv"), _file("analysis.py")],
    )
    hunter.score_record(rec)
    assert rec.domain_relevant is True


def test_cantilever_mechanics_approves() -> None:
    rec = _record(
        title="Cantilever calibration dataset",
        description="Includes cantilever spring constant, deflection sensitivity and force curve calibration.",
    )
    hunter.score_record(rec)
    assert rec.domain_relevant is True


def test_afm_isolated_fails_or_bronze() -> None:
    rec = _record(
        title="AFM dataset",
        files=[_file("raw_data.csv"), _file("results.csv")],
    )
    hunter.score_record(rec)
    assert rec.domain_relevant is False or rec.level == "bronze"


def test_substring_not_afm() -> None:
    rec = _record(
        title="Staff meeting notes and team metrics",
        files=[_file("data.csv")],
    )
    hunter.score_record(rec)
    # The word "staff" contains "afm" internally but should not trigger
    for reason in rec.relevance_reasons:
        if "AFM" in reason and "sigla" in reason:
            raise AssertionError(f"False AFM match in: {reason}")
    assert rec.domain_relevant is False


def test_case_insensitive_matching() -> None:
    rec = _record(
        title="atomic force microscopy study",
    )
    hunter.score_record(rec)
    assert rec.domain_relevant is True

    rec2 = _record(
        title="SCANNING PROBE MICROSCOPY DATA",
    )
    hunter.score_record(rec2)
    assert rec2.domain_relevant is True


def test_html_description_normalized() -> None:
    rec = _record(
        title="Dataset",
        description="<p>This study uses <b>atomic force microscopy</b> for imaging.</p>",
    )
    hunter.score_record(rec)
    assert rec.domain_relevant is True


# ---------------------------------------------------------------------------
# False positives (ecological / non-AFM/SPM datasets)
# ---------------------------------------------------------------------------


def test_false_positive_ecology_polistes() -> None:
    rec = _record(
        title="Regional niche differentiation and reciprocal transfer analyses for Polistes rothneyi in Jeju Island and mainland Korea",
        description="Ecological field study.",
        doi="10.0000/eco",
        license="CC-BY-4.0",
        files=[
            _file("raw_data.csv"),
            _file("processed_results.csv"),
            _file("analysis.py"),
            _file("README.md"),
            _file("methods.pdf"),
        ],
    )
    hunter.score_record(rec)
    assert rec.domain_relevant is False, rec.relevance_reasons
    assert rec.level == "bronze"
    assert rec.score <= 39


def test_false_positive_parasitoid() -> None:
    rec = _record(
        title="Host manipulation by an ichneumonid spider ectoparasitoid",
        description="Behavioral ecology study.",
        files=[
            _file("raw_data.csv"),
            _file("results.csv"),
            _file("analysis.py"),
            _file("README.md"),
        ],
    )
    hunter.score_record(rec)
    assert rec.domain_relevant is False
    assert rec.level == "bronze"


def test_false_positive_asphalt() -> None:
    rec = _record(
        title="Dynamic Modulus Master Curve for Hot Mix Asphalt",
        description="Civil engineering pavement study.",
        files=[
            _file("raw_measurements.csv"),
            _file("fitted_results.csv"),
            _file("pipeline.py"),
            _file("methodology.pdf"),
        ],
    )
    hunter.score_record(rec)
    assert rec.domain_relevant is False
    assert rec.level == "bronze"


def test_false_positive_oceanography() -> None:
    rec = _record(
        title="Underwater spectral irradiance data, tropical seamount, eastern Atlantic",
        description="Oceanographic light measurements.",
        files=[_file("data.csv"), _file("README.md")],
    )
    hunter.score_record(rec)
    assert rec.domain_relevant is False


def test_false_positive_diatom() -> None:
    rec = _record(
        title="Priority effects in a planktonic bloom-forming marine diatom",
        description="Marine biology competition experiment.",
        files=[_file("raw_data.csv"), _file("results.csv"), _file("code.py")],
    )
    hunter.score_record(rec)
    assert rec.domain_relevant is False


# ---------------------------------------------------------------------------
# Score and classification
# ---------------------------------------------------------------------------


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
    assert record.domain_relevant is True


def test_irrelevant_never_gold() -> None:
    rec = _record(
        title="Generic ecology data",
        description="Well-documented non-AFM study.",
        doi="10.0000/x",
        license="CC-BY-4.0",
        files=[_file("raw.csv"), _file("processed.csv"), _file("code.py"), _file("README.md")],
    )
    hunter.score_record(rec)
    assert rec.domain_relevant is False
    assert rec.level != "gold"
    assert rec.level != "silver"


def test_irrelevant_never_silver() -> None:
    rec = _record(
        title="Generic ocean data",
        description="Well-documented non-AFM study.",
        doi="10.0000/y",
        files=[_file("raw.csv"), _file("code.py")],
    )
    hunter.score_record(rec)
    assert rec.domain_relevant is False
    assert rec.level != "silver"
    assert rec.level == "bronze"


def test_benchmark_score_preserved() -> None:
    """El benchmark_score no debe reducirse por fallar relevancia."""
    rec = _record(
        title="Generic well-documented data",
        doi="10.0000/z",
        license="CC-BY-4.0",
        files=[_file("raw.csv"), _file("processed.csv"), _file("code.py"), _file("README.md")],
    )
    hunter.score_record(rec)
    assert rec.benchmark_score >= 70  # calidad documental alta
    assert rec.score <= 39  # score final limitado


def test_score_record_idempotent() -> None:
    rec = _record(
        title="AFM topography with Gwyddion processing",
        files=[_file("data.csv"), _file("analysis.py")],
    )
    hunter.score_record(rec)
    first_score = rec.score
    first_level = rec.level
    hunter.score_record(rec)
    assert rec.score == first_score
    assert rec.level == first_level


def test_scores_in_range() -> None:
    rec = _record(title="AFM topography with Gwyddion", files=[_file("data.csv")])
    hunter.score_record(rec)
    assert 0 <= rec.score <= 100
    assert 0 <= rec.benchmark_score <= 100
    assert 0 <= rec.relevance_score <= 100


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def test_relevant_before_irrelevant() -> None:
    relevant = _record(
        source="test",
        source_id="r1",
        title="AFM topography dataset",
        doi="10.0000/afm1",
        files=[_file("sample.nid")],
    )
    irrelevant = _record(
        source="test",
        source_id="i1",
        title="Completely unrelated well-documented data",
        doi="10.0000/other",
        files=[_file("raw.csv"), _file("processed.csv"), _file("code.py"), _file("README.md")],
    )
    merged = hunter.merge_records([relevant, irrelevant])
    assert merged[0].domain_relevant is True


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_to_dict_includes_new_fields() -> None:
    rec = _record(
        title="AFM topography with Gwyddion",
        files=[_file("data.csv")],
    )
    hunter.score_record(rec)
    d = rec.to_dict()
    assert "benchmark_score" in d
    assert "relevance_score" in d
    assert "domain_relevant" in d
    assert "relevance_reasons" in d


def test_json_serialization_preserves_types() -> None:
    rec = _record(
        title="Atomic force microscopy study",
        files=[_file("raw.nid")],
    )
    hunter.score_record(rec)
    serialized = json.dumps(rec.to_dict())
    data = json.loads(serialized)
    assert isinstance(data["benchmark_score"], int)
    assert isinstance(data["relevance_score"], int)
    assert isinstance(data["domain_relevant"], bool)
    assert isinstance(data["score"], int)
    assert data["domain_relevant"] is True


# ---------------------------------------------------------------------------
# SQLite catalog
# ---------------------------------------------------------------------------


def test_new_catalog_has_columns() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.sqlite3"
        catalog = hunter.Catalog(path)
        try:
            cols = {row[1] for row in catalog.conn.execute("PRAGMA table_info(records)").fetchall()}
            assert "benchmark_score" in cols
            assert "relevance_score" in cols
            assert "domain_relevant" in cols
        finally:
            catalog.close()


def test_migration_from_old_schema() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "old.sqlite3"
        conn = sqlite3.connect(str(path))
        conn.executescript(
            """CREATE TABLE records (
                record_key TEXT PRIMARY KEY,
                source TEXT, source_id TEXT, title TEXT,
                score INTEGER, level TEXT,
                metadata_json TEXT, updated_at TEXT
            );"""
        )
        conn.commit()
        conn.close()

        catalog = hunter.Catalog(path)
        try:
            cols = {row[1] for row in catalog.conn.execute("PRAGMA table_info(records)").fetchall()}
            assert "benchmark_score" in cols, f"Migration failed, cols: {cols}"
            assert "relevance_score" in cols
            assert "domain_relevant" in cols
        finally:
            catalog.close()


def test_upsert_persists_new_fields() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.sqlite3"
        catalog = hunter.Catalog(path)
        try:
            rec = _record(
                source="test",
                source_id="99",
                title="AFM with Gwyddion study",
                doi="10.0000/test-upsert",
                files=[_file("sample.nid")],
            )
            hunter.score_record(rec)
            catalog.upsert(rec)

            row = catalog.conn.execute(
                "SELECT benchmark_score, relevance_score, domain_relevant FROM records WHERE record_key=?",
                (rec.key,),
            ).fetchone()
            assert row is not None
            assert row[2] == 1  # domain_relevant as int
            assert row[0] > 0  # benchmark_score
        finally:
            catalog.close()
