#!/usr/bin/env python3
"""
SPM-Kit Data Hunter
===================

Curador de datasets públicos para validar SPM-Kit.

Busca en APIs oficiales de Zenodo y Figshare, clasifica archivos como datos
crudos, resultados procesados, código, documentación o archivos comprimidos,
puntúa cada registro como Gold/Silver/Bronze y, opcionalmente, descarga los
mejores candidatos con reanudación y verificación de checksums.

Principio central:
    No buscar "archivos AFM" aislados, sino cadenas de evidencia:
    datos crudos -> método/código -> resultados procesados -> publicación.

Dependencias:
    pip install requests tqdm

Ejemplos:
    # Solo descubrir y rankear, sin descargar
    python spmkit_data_hunter.py --preset all --limit 25 --top 30

    # Buscar curvas de fuerza y descargar solo candidatos Gold/Silver
    python spmkit_data_hunter.py \
        --preset force \
        --levels gold silver \
        --download \
        --max-file-mb 1500

    # Consultas propias, repetibles
    python spmkit_data_hunter.py \
        --query "AFM raw processed data" \
        --query "atomic force microscopy source data analysis script" \
        --source all \
        --top 50

    # Ejecutar pruebas internas sin acceder a internet
    python spmkit_data_hunter.py --self-test

Autor:
    José Labarca, SPM-Kit
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import ipaddress
import json
import logging
import os
import re
import sqlite3
import tarfile
import threading
import time
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    tqdm = None


VERSION = "2.2.0"
DEFAULT_OUTPUT = Path("./spm_benchmarks")
ZENODO_API = "https://zenodo.org/api/records"
FIGSHARE_API = "https://api.figshare.com/v2"
DEFAULT_USER_AGENT = (
    f"SPM-Kit-DataHunter/{VERSION} "
    "(https://github.com/kegouro/spmkit-data-hunter; scientific dataset discovery)"
)

LOG = logging.getLogger("spmkit-data-hunter")


# ---------------------------------------------------------------------------
# Consultas sugeridas
# ---------------------------------------------------------------------------

QUERY_PRESETS: dict[str, list[str]] = {
    "topography": [
        '"atomic force microscopy" raw processed topography',
        '"AFM" source data roughness profile',
        '"AFM" raw data Gwyddion processed',
        '"scanning probe microscopy" raw processed image',
    ],
    "force": [
        '"force spectroscopy" raw curves processed results',
        '"AFM force curve" raw calibration modulus',
        '"JPK force" source data analysis',
        '"nanoindentation AFM" raw processed Young modulus',
    ],
    "kpfm": [
        '"KPFM" raw processed data',
        '"Kelvin probe force microscopy" source data analysis',
        '"surface potential" AFM raw processed',
    ],
    "grains": [
        '"AFM" raw processed grain analysis',
        '"atomic force microscopy" segmentation source data',
        '"TopoStats" raw data results',
    ],
    "resonance": [
        '"AFM thermal tune" raw data fit',
        '"cantilever resonance" AFM raw processed',
        '"thermal noise" cantilever spectrum dataset',
    ],
    "all": [
        '"AFM" raw processed data',
        '"atomic force microscopy" source data analysis script',
        '"force spectroscopy" raw curves processed results',
        '"KPFM" raw processed data',
        '"scanning probe microscopy" raw processed',
        '"AFM" Gwyddion raw export',
        '"AFM" calibration results dataset',
        '"AFM" source data figures',
    ],
}


# ---------------------------------------------------------------------------
# Clasificación de archivos
# ---------------------------------------------------------------------------

RAW_EXTENSIONS = {
    ".nid",
    ".nhf",
    ".gwy",
    ".jpk",
    ".jpk-force",
    ".jpk-qi-data",
    ".spm",
    ".ibw",
    ".mi",
    ".mtrx",
    ".sxm",
    ".wsxm",
    ".aris",
    ".mdt",
    ".sm4",
    ".stp",
    ".top",
    ".xqd",
    ".ardf",
    ".asd",
    ".h5-jpk",
    ".jpk-qi-image",
    ".topostats",
    ".gsf",
    ".sdf",
    ".sur",
    ".x3p",
    ".bcr",
    ".bcrf",
    ".nan",
    ".nao",
    ".sm2",
    ".sm3",
    ".cur",
    ".afm",
}

PROCESSED_EXTENSIONS = {
    ".csv",
    ".tsv",
    ".xlsx",
    ".xls",
    ".ods",
    ".json",
    ".yaml",
    ".yml",
    ".txt",
    ".dat",
    ".npy",
    ".npz",
    ".parquet",
    ".feather",
    ".h5",
    ".hdf5",
    ".mat",
    ".tif",
    ".tiff",
}

AMBIGUOUS_DATA_EXTENSIONS = {
    ".csv",
    ".tsv",
    ".txt",
    ".dat",
    ".h5",
    ".hdf5",
    ".tif",
    ".tiff",
    ".mat",
    ".npy",
    ".npz",
}

CODE_EXTENSIONS = {
    ".py",
    ".ipynb",
    ".m",
    ".r",
    ".jl",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".sh",
    ".bash",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
}

DOCUMENT_EXTENSIONS = {
    ".md",
    ".rst",
    ".pdf",
    ".docx",
    ".odt",
    ".tex",
    ".bib",
    ".html",
}

IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".gif",
    ".svg",
    ".webp",
}

ARCHIVE_SUFFIXES = (
    ".zip",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tbz2",
    ".tar.xz",
    ".txz",
    ".7z",
    ".rar",
)

RAW_WORDS = {
    "raw",
    "original",
    "native",
    "unprocessed",
    "source data",
    "source_data",
    "instrument",
    "scan",
    "curve",
    "curves",
    "trace",
    "retrace",
    "approach",
    "retract",
}

PROCESSED_WORDS = {
    "processed",
    "result",
    "results",
    "summary",
    "statistics",
    "analysis",
    "analyzed",
    "analysed",
    "export",
    "profile",
    "roughness",
    "modulus",
    "adhesion",
    "height",
    "segmentation",
    "grain",
    "fit",
    "fitted",
    "figure data",
    "source data",
}

CODE_WORDS = {
    "script",
    "scripts",
    "code",
    "notebook",
    "pipeline",
    "workflow",
    "matlab",
    "python",
    "gwyddion",
    "topostats",
    "analysis software",
}

METHOD_WORDS = {
    "method",
    "methods",
    "calibration",
    "spring constant",
    "deflection sensitivity",
    "cantilever",
    "tip radius",
    "poisson",
    "young modulus",
    "contact model",
    "hertz",
    "dmt",
    "jkr",
    "sneddon",
    "wlc",
    "fjc",
    "leveling",
    "levelling",
    "flatten",
    "filter",
    "threshold",
    "pixel size",
    "scan size",
}

SPM_WORDS = {
    "afm",
    "spm",
    "atomic force microscopy",
    "scanning probe microscopy",
    "kpfm",
    "kelvin probe force microscopy",
    "force spectroscopy",
    "force curve",
    "nanomechanical",
    "nanoindentation",
    "cantilever",
    "topography",
}

OPEN_LICENSE_HINTS = {
    "cc0",
    "cc-by",
    "creative commons",
    "mit",
    "bsd",
    "apache",
    "gpl",
    "public domain",
    "open data",
}


def full_suffix(name: str) -> str:
    """Devuelve la extensión compuesta más informativa."""
    lowered = name.lower()
    for suffix in ARCHIVE_SUFFIXES:
        if lowered.endswith(suffix):
            return suffix
    if lowered.endswith(".jpk-force"):
        return ".jpk-force"
    for suffix in (".jpk-qi-data", ".jpk-qi-image", ".h5-jpk", ".topostats"):
        if lowered.endswith(suffix):
            return suffix
    return Path(lowered).suffix


@lru_cache(maxsize=2048)
def _term_pattern(term: str) -> re.Pattern[str]:
    """Compile a conservative term matcher.

    Word-like terms use Unicode-aware token boundaries so ``raw`` does not
    match ``drawings`` and ``code`` does not match ``decode``. Multi-word and
    punctuation-bearing terms allow flexible whitespace while retaining
    boundaries at their edges.
    """

    normalized = re.sub(r"\s+", " ", term.casefold().strip())
    escaped = re.escape(normalized).replace(r"\ ", r"\s+")
    left = r"(?<!\w)" if normalized and normalized[0].isalnum() else ""
    right = r"(?!\w)" if normalized and normalized[-1].isalnum() else ""
    return re.compile(left + escaped + right, flags=re.IGNORECASE)


def contains_any(text: str, terms: Iterable[str]) -> bool:
    normalized = re.sub(r"[_\-]+", " ", text.casefold())
    return any(_term_pattern(term).search(normalized) for term in terms)


def strip_html(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_doi(value: Any) -> str:
    normalized = strip_html(value).strip()
    if not normalized:
        return ""
    normalized = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", normalized, flags=re.I)
    normalized = re.sub(r"^doi:\s*", "", normalized, flags=re.I)
    return normalized.rstrip(".,;)").strip().casefold()


def normalize_url(value: Any, *, github_root: bool = False) -> str:
    raw = strip_html(value)
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return raw

    host = parsed.netloc.casefold()
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    is_github = host in {"github.com", "www.github.com"}
    if is_github:
        host = "github.com"
        path = path.rstrip("/")
        if path.endswith(".git"):
            path = path[:-4]
        if github_root:
            parts = [part for part in path.split("/") if part]
            if len(parts) >= 2:
                parts[1] = parts[1].removesuffix(".git")
                path = "/" + "/".join(parts[:2])

    query = "" if github_root and is_github else parsed.query
    return urlunparse(("https", host, path or "/", "", query, ""))


def normalize_identifier(value: Any) -> str:
    return strip_html(value).strip()


def sanitize_component(value: str, max_length: int = 120) -> str:
    value = strip_html(value)
    value = re.sub(r"[^\w.\-+() ]+", "_", value, flags=re.UNICODE)
    value = re.sub(r"\s+", "_", value).strip("._ ")
    value = value[:max_length].rstrip("._ ")
    return value or "untitled"


def is_safe_https_url(url: str) -> bool:
    """Reject non-HTTPS URLs and literal non-public IP destinations."""

    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def infer_categories(name: str) -> set[str]:
    """Classify a file conservatively from its name and suffix.

    Generic containers such as CSV, HDF5 and TIFF are ambiguous. An explicit
    ``raw`` signal suppresses their default ``processed`` label unless the name
    independently contains a processed-result signal. This prevents a single
    file such as ``raw_data.csv`` from fabricating a complete validation chain.
    """

    lowered = name.casefold()
    suffix = full_suffix(name)
    categories: set[str] = set()
    raw_signal = contains_any(lowered, RAW_WORDS)
    processed_signal = contains_any(lowered, PROCESSED_WORDS)
    code_signal = contains_any(
        lowered,
        {"script", "scripts", "code", "notebook", "pipeline", "workflow"},
    )

    if suffix in RAW_EXTENSIONS:
        categories.add("raw")
    if suffix in PROCESSED_EXTENSIONS:
        categories.add("processed")
    if suffix in CODE_EXTENSIONS:
        categories.add("code")
    if suffix in DOCUMENT_EXTENSIONS:
        categories.add("documentation")
    if suffix in IMAGE_EXTENSIONS:
        categories.add("image")
    if suffix in ARCHIVE_SUFFIXES:
        categories.add("archive")

    if raw_signal and suffix not in IMAGE_EXTENSIONS and suffix not in DOCUMENT_EXTENSIONS:
        categories.add("raw")
        if suffix in AMBIGUOUS_DATA_EXTENSIONS and not processed_signal:
            categories.discard("processed")
    if processed_signal:
        categories.add("processed")
    if code_signal:
        categories.add("code")
    if contains_any(lowered, {"readme", "method", "methods", "protocol", "manual"}):
        categories.add("documentation")

    if not categories:
        categories.add("other")
    return categories


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FileAsset:
    name: str
    url: str
    size: int | None = None
    checksum: str = ""
    categories: list[str] = field(default_factory=list)
    source_file_id: str = ""
    downloaded_path: str = ""
    download_status: str = "pending"
    checksum_status: str = "not_checked"
    sha256: str = ""
    verification_status: str = "not_checked"
    verification_notes: str = ""

    @classmethod
    def build(
        cls,
        *,
        name: str,
        url: str,
        size: int | None = None,
        checksum: str = "",
        source_file_id: str = "",
    ) -> FileAsset:
        return cls(
            name=strip_html(name).strip() or "unnamed",
            url=normalize_url(url),
            size=size,
            checksum=checksum or "",
            categories=sorted(infer_categories(strip_html(name))),
            source_file_id=normalize_identifier(source_file_id),
        )


@dataclass(slots=True)
class DatasetRecord:
    source: str
    source_id: str
    title: str
    description: str = ""
    doi: str = ""
    landing_url: str = ""
    license: str = ""
    published: str = ""
    modified: str = ""
    creators: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    related_identifiers: list[dict[str, str]] = field(default_factory=list)
    files: list[FileAsset] = field(default_factory=list)
    matched_query: str = ""
    score: int = 0
    level: str = "bronze"
    score_reasons: list[str] = field(default_factory=list)
    benchmark_score: int = 0
    relevance_score: int = 0
    domain_relevant: bool = False
    relevance_reasons: list[str] = field(default_factory=list)
    utility_class: str = "incomplete"
    utility_reasons: list[str] = field(default_factory=list)
    discovered_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def key(self) -> str:
        doi = normalize_doi(self.doi)
        if doi:
            return f"doi:{doi}"
        landing = normalize_url(self.landing_url, github_root=True)
        if landing:
            return f"url:{landing.casefold()}"
        return f"{self.source}:{normalize_identifier(self.source_id)}"

    @property
    def categories(self) -> set[str]:
        result: set[str] = set()
        for asset in self.files:
            result.update(asset.categories)
        return result

    @property
    def total_size(self) -> int:
        return sum(asset.size or 0 for asset in self.files)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_record(record: DatasetRecord) -> DatasetRecord:
    record.source = normalize_identifier(record.source).casefold()
    record.source_id = normalize_identifier(record.source_id)
    record.title = strip_html(record.title) or "Sin título"
    record.description = strip_html(record.description)
    record.doi = normalize_doi(record.doi)
    record.landing_url = normalize_url(record.landing_url, github_root=True)
    record.license = strip_html(record.license)
    record.published = normalize_identifier(record.published)
    record.modified = normalize_identifier(record.modified)
    record.creators = list(
        dict.fromkeys(strip_html(value) for value in record.creators if strip_html(value))
    )
    record.keywords = list(
        dict.fromkeys(strip_html(value) for value in record.keywords if strip_html(value))
    )

    related: list[dict[str, str]] = []
    seen_related: set[tuple[str, str, str]] = set()
    for item in record.related_identifiers:
        identifier = item.get("identifier", "")
        scheme = item.get("scheme", "")
        identifier = (
            normalize_doi(identifier) if scheme.casefold() == "doi" else normalize_url(identifier)
        )
        relation = normalize_identifier(item.get("relation", ""))
        key = (identifier.casefold(), relation.casefold(), scheme.casefold())
        if identifier and key not in seen_related:
            seen_related.add(key)
            related.append({"identifier": identifier, "relation": relation, "scheme": scheme})
    record.related_identifiers = related

    unique_files: dict[str, FileAsset] = {}
    for asset in record.files:
        asset.name = strip_html(asset.name) or "unnamed"
        asset.url = normalize_url(asset.url)
        asset.checksum = normalize_identifier(asset.checksum)
        asset.source_file_id = normalize_identifier(asset.source_file_id)
        asset.categories = sorted(infer_categories(asset.name))
        if asset.url and asset.url not in unique_files:
            unique_files[asset.url] = asset
    record.files = list(unique_files.values())
    return record


# ---------------------------------------------------------------------------
# Evaluación de relevancia de dominio AFM/SPM
# ---------------------------------------------------------------------------

# Frases fuertes no ambiguas. Cada una es suficiente por sí sola.
_STRONG_PHRASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE), phrase)
    for phrase in [
        "atomic force microscopy",
        "atomic force microscope",
        "scanning probe microscopy",
        "scanning probe microscope",
        "scanning tunneling microscopy",
        "scanning tunneling microscope",
        "kelvin probe force microscopy",
        "magnetic force microscopy",
        "electrostatic force microscopy",
        "afm force spectroscopy",
        "afm force curve",
    ]
]

# Siglas con límite de palabra.
_ACRONYM_LABELS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"\b{re.escape(acr)}\b", re.IGNORECASE), acr)
    for acr in ["AFM", "SPM", "KPFM", "MFM", "EFM", "STM"]
]

# Señales contextuales agrupadas en familias semánticas independientes.
_CONTEXTUAL_FAMILIES: dict[str, list[tuple[re.Pattern[str], str]]] = {
    "cantilever_mechanics": [
        (re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE), term)
        for term in [
            "cantilever",
            "spring constant",
            "deflection sensitivity",
            "thermal tune",
            "force curve",
            "force spectroscopy",
            "nanoindentation",
            "nanomechanical",
        ]
    ],
    "topography": [
        (re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE), term)
        for term in ["topography", "topographic", "roughness"]
    ],
    "spm_software": [
        (re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE), term)
        for term in ["Gwyddion", "JPK", "Nanoscope", "WSxM", "TopoStats"]
    ],
    "force_spectroscopy": [
        (re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE), term)
        for term in [
            "force curve",
            "force spectroscopy",
            "force-distance",
            "force volume",
        ]
    ],
    "scanning_modality": [
        (re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE), term)
        for term in [
            "contact mode",
            "tapping mode",
            "peakforce",
            "peak force",
            "intermittent contact",
            "phase imaging",
            "amplitude modulation",
            "frequency modulation",
            "piezo",
            "piezoelectric",
        ]
    ],
}

# Extensiones nativas SPM: señal fuerte por sí sola.
_NATIVE_SPM_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".nid",
        ".nhf",
        ".gwy",
        ".jpk",
        ".jpk-force",
        ".jpk-qi-data",
        ".spm",
        ".ibw",
        ".mtrx",
        ".sxm",
        ".mdt",
        ".sm4",
    }
)


def _check_file_signals(record: DatasetRecord) -> dict[str, bool]:
    """Detecta señales de AFM/SPM en nombres y extensiones de archivos."""
    has_native = False
    has_software = False
    native_exts: list[str] = []
    for asset in record.files:
        suffix = full_suffix(asset.name)
        if suffix in _NATIVE_SPM_EXTENSIONS:
            has_native = True
            native_exts.append(suffix)
    return {"has_native": has_native, "has_software": has_software, "native_exts": native_exts}


def _check_text_signals(text: str) -> dict[str, list[str]]:
    """Escanea un texto en busca de frases fuertes, acrónimos y familias contextuales."""
    result: dict[str, list[str]] = {
        "strong_phrases": [],
        "acronyms": [],
        "families": {},
    }
    for pattern, label in _STRONG_PHRASES:
        if pattern.search(text):
            result["strong_phrases"].append(label)

    for pattern, label in _ACRONYM_LABELS:
        if pattern.search(text):
            result["acronyms"].append(label)

    for family_name, entries in _CONTEXTUAL_FAMILIES.items():
        for pattern, label in entries:
            if pattern.search(text):
                result["families"].setdefault(family_name, []).append(label)

    return result


def _build_relevance_text(record: DatasetRecord) -> str:
    """Combina los textos relevantes del registro para evaluación de dominio."""
    parts: list[str] = [record.title]
    if record.description:
        parts.append(record.description)
    if record.keywords:
        parts.append(" ".join(record.keywords))
    # Nombres de archivos como texto adicional (no extensiones)
    file_names = [asset.name for asset in record.files]
    if file_names:
        parts.append(" ".join(file_names))
    return " ".join(parts)


def assess_domain_relevance(record: DatasetRecord) -> DatasetRecord:
    """Evalúa si un registro pertenece al dominio AFM/SPM.

    Detecta señales fuertes (frases exactas, extensiones nativas) y débiles
    (siglas, familias contextuales).  Aplica una regla de gate documentada.

    La función es pura, determinista y no depende de la red.
    """
    reasons: list[str] = []
    score = 0

    # ── Señales desde archivos ─────────────────────────────────────────
    file_sigs = _check_file_signals(record)

    if file_sigs["has_native"]:
        exts = file_sigs["native_exts"]
        score += 60
        reasons.append(f"+60 formato SPM nativo: {', '.join(exts)}")
        record.relevance_score = min(100, score)
        record.domain_relevant = True
        record.relevance_reasons = reasons
        return record

    # ── Señales desde texto ────────────────────────────────────────────
    text = _build_relevance_text(record)
    sigs = _check_text_signals(text)

    # Frases fuertes (inequívocas).
    for phrase in sigs["strong_phrases"]:
        score += 60
        reasons.append(f'+60 frase AFM/SPM inequívoca: "{phrase}"')
        break  # Una sola frase fuerte basta

    if score >= 60:
        record.relevance_score = min(100, score)
        record.domain_relevant = True
        record.relevance_reasons = reasons
        return record

    # Acrónimos (señal débil, no suficiente sola).
    for acr in sigs["acronyms"]:
        score += 20
        reasons.append(f"+20 sigla AFM/SPM: {acr}")
        break  # No repetir la misma familia de acrónimos

    # Familias contextuales (cada familia cuenta una vez).
    family_bonus = 15
    families_detected: list[str] = []
    for fam_name, hits in sigs["families"].items():
        families_detected.append(fam_name)
        reasons.append(f"+{family_bonus} señal contextual ({fam_name}): {', '.join(hits[:3])}")
        score += family_bonus

    # Gate: se requiere al menos una señal fuerte, o dos familias independientes.
    independent_families = len(sigs["acronyms"]) + len(families_detected)
    if score >= 60 or independent_families >= 2:
        record.domain_relevant = True
        reasons.append("gate aprobado: evidencia AFM/SPM suficiente")
    else:
        record.domain_relevant = False
        if reasons:
            reasons.append("gate rechazado: evidencia AFM/SPM insuficiente")
        else:
            reasons.append("gate rechazado: sin evidencia de AFM/SPM")

    record.relevance_score = max(0, min(100, score))
    record.relevance_reasons = reasons
    return record


# ---------------------------------------------------------------------------
# Puntuación de benchmarks
# ---------------------------------------------------------------------------


def calculate_benchmark_score(record: DatasetRecord) -> tuple[int, list[str]]:
    """Calcula la calidad de la cadena de evidencia (0-100), sin evaluar relevancia AFM/SPM."""
    score = 0
    reasons: list[str] = []
    cats = record.categories

    if "raw" in cats:
        score += 32
        reasons.append("+32 contiene datos aparentemente crudos")
    else:
        score -= 18
        reasons.append("-18 no se detectaron datos crudos")

    if "processed" in cats:
        score += 24
        reasons.append("+24 contiene resultados procesados")

    if "code" in cats:
        score += 18
        reasons.append("+18 contiene código o notebooks")

    if "documentation" in cats:
        score += 10
        reasons.append("+10 contiene documentación o métodos")

    if "archive" in cats:
        score += 4
        reasons.append("+4 contiene archivos comprimidos inspeccionables")

    combined = " ".join(
        [
            record.title,
            record.description,
            " ".join(record.keywords),
            " ".join(asset.name for asset in record.files),
        ]
    ).casefold()

    if contains_any(combined, RAW_WORDS):
        score += 5
        reasons.append("+5 el texto menciona datos crudos/originales")

    if contains_any(combined, PROCESSED_WORDS):
        score += 5
        reasons.append("+5 el texto menciona resultados o procesamiento")

    if contains_any(combined, METHOD_WORDS):
        score += 8
        reasons.append("+8 incluye señales de método o calibración")

    if record.doi:
        score += 4
        reasons.append("+4 tiene DOI")

    if record.related_identifiers:
        score += 5
        reasons.append("+5 enlaza recursos o publicaciones relacionadas")

    if record.license and contains_any(record.license, OPEN_LICENSE_HINTS):
        score += 4
        reasons.append("+4 licencia abierta reconocible")

    useful = cats.intersection({"raw", "processed", "code", "documentation"})
    if cats.issubset({"image", "documentation", "other"}) and "raw" not in cats:
        score -= 15
        reasons.append("-15 parece contener solo imágenes/documentos")

    if len(record.files) == 0:
        score -= 30
        reasons.append("-30 registro sin archivos públicos")

    if len(useful) >= 4:
        score += 5
        reasons.append("+5 cadena de evidencia muy completa")

    return max(0, min(100, score)), reasons


def _distinct_evidence_assets(record: DatasetRecord) -> tuple[set[str], set[str]]:
    raw = {asset.url or asset.name for asset in record.files if "raw" in asset.categories}
    processed = {
        asset.url or asset.name for asset in record.files if "processed" in asset.categories
    }
    return raw, processed


def classify_utility(record: DatasetRecord) -> DatasetRecord:
    """Assign a scientific-use class without pretending to establish ground truth."""

    cats = record.categories
    raw_assets, processed_assets = _distinct_evidence_assets(record)
    distinct_chain = bool(raw_assets and processed_assets and raw_assets != processed_assets)
    companion = bool(cats.intersection({"code", "documentation"}))

    if not record.domain_relevant:
        utility = "incomplete"
        reasons = ["AFM/SPM domain relevance has not been established"]
    elif distinct_chain and companion:
        utility = "benchmark_ready"
        reasons = ["distinct raw and processed assets", "method/code companion present"]
    elif distinct_chain:
        utility = "crosscheck_candidate"
        reasons = ["distinct raw and processed assets", "method/code companion missing"]
    elif raw_assets:
        utility = "reader_fixture"
        reasons = ["raw/native evidence without an independent processed reference"]
    elif processed_assets:
        utility = "processed_reference_only"
        reasons = ["processed/reference output without recoverable raw input"]
    elif companion:
        utility = "documentation_only"
        reasons = ["documentation or code found without usable data assets"]
    else:
        utility = "incomplete"
        reasons = ["insufficient evidence for a validation or reader fixture"]

    record.utility_class = utility
    record.utility_reasons = reasons
    return record


def score_record(record: DatasetRecord) -> DatasetRecord:
    normalize_record(record)

    # 1. Evaluar relevancia de dominio (gate).
    assess_domain_relevance(record)

    # 2. Calcular calidad documental (benchmark).
    benchmark, bm_reasons = calculate_benchmark_score(record)
    record.benchmark_score = benchmark

    # 3. Calcular score final.
    cats = record.categories
    reasons: list[str] = []

    if record.domain_relevant:
        # El registro pertenece a AFM/SPM: score basado en calidad documental.
        score = benchmark

        if (
            score >= 72
            and {"raw", "processed"}.issubset(cats)
            and bool(cats.intersection({"code", "documentation"}))
        ):
            level = "gold"
        elif (
            score >= 48
            and "raw" in cats
            and bool(cats.intersection({"processed", "code", "documentation"}))
        ):
            level = "silver"
        else:
            level = "bronze"

        reasons.extend(bm_reasons)
    else:
        # Registro irrelevante: score limitado. No puede ser Gold ni Silver.
        score = min(benchmark, 39)
        level = "bronze"
        reasons.append(
            f"gate de dominio: sin evidencia AFM/SPM suficiente (score limitado a {score})"
        )
        reasons.extend(bm_reasons)

    record.score = score
    record.level = level
    record.score_reasons = reasons
    classify_utility(record)

    # Gold and Silver describe validation-chain completeness, not merely a high
    # metadata score. A raw-only reader fixture must remain Bronze.
    if record.utility_class == "benchmark_ready" and score >= 72:
        record.level = "gold"
    elif record.utility_class in {"benchmark_ready", "crosscheck_candidate"} and score >= 48:
        record.level = "silver"
    else:
        record.level = "bronze"
    return record


# ---------------------------------------------------------------------------
# HTTP robusto y límites responsables
# ---------------------------------------------------------------------------


class HostRateLimiter:
    def __init__(self, interval_seconds: float = 1.05) -> None:
        self.interval = max(0.0, interval_seconds)
        self._lock = threading.Lock()
        self._last_call: dict[str, float] = {}

    def wait(self, url: str) -> None:
        host = urlparse(url).netloc.casefold()
        with self._lock:
            last = self._last_call.get(host, 0.0)
            delay = self.interval - (time.monotonic() - last)
            if delay > 0:
                time.sleep(delay)
            self._last_call[host] = time.monotonic()


class HttpClient:
    def __init__(
        self,
        *,
        timeout: float = 45.0,
        user_agent: str = DEFAULT_USER_AGENT,
        rate_seconds: float = 1.05,
    ) -> None:
        self.timeout = timeout
        self.rate_limiter = HostRateLimiter(rate_seconds)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/json",
            }
        )

        retry = Retry(
            total=5,
            connect=5,
            read=5,
            status=5,
            backoff_factor=1.0,
            status_forcelist=(408, 425, 429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST", "HEAD"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
        self.session.mount("https://", adapter)

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        self.rate_limiter.wait(url)
        kwargs.setdefault("timeout", self.timeout)
        response = self.session.request(method, url, **kwargs)
        if response.status_code >= 400:
            snippet = strip_html(response.text[:500])
            raise requests.HTTPError(
                f"{method} {url} -> HTTP {response.status_code}: {snippet}",
                response=response,
            )
        return response

    def get_json(self, url: str, **kwargs: Any) -> Any:
        response = self.request("GET", url, **kwargs)
        return response.json()

    def post_json(self, url: str, payload: dict[str, Any]) -> Any:
        response = self.request("POST", url, json=payload)
        return response.json()


# ---------------------------------------------------------------------------
# Fuentes
# ---------------------------------------------------------------------------


class Source:
    name = "base"

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def search(self, query: str, limit: int) -> list[DatasetRecord]:
        raise NotImplementedError


class ZenodoSource(Source):
    name = "zenodo"

    @staticmethod
    def _file_url(item: dict[str, Any]) -> str:
        links = item.get("links") or {}
        return (
            links.get("content")
            or links.get("self")
            or links.get("download")
            or item.get("download")
            or ""
        )

    def _parse_hit(self, hit: dict[str, Any], query: str) -> DatasetRecord:
        metadata = hit.get("metadata") or {}
        files_raw = hit.get("files") or []

        files: list[FileAsset] = []
        for item in files_raw:
            name = str(item.get("key") or item.get("filename") or "unnamed")
            url = self._file_url(item)
            if not url or not is_safe_https_url(url):
                continue
            files.append(
                FileAsset.build(
                    name=name,
                    url=url,
                    size=_safe_int(item.get("size")),
                    checksum=str(item.get("checksum") or ""),
                    source_file_id=str(item.get("id") or ""),
                )
            )

        license_value = metadata.get("license") or ""
        if isinstance(license_value, dict):
            license_value = (
                license_value.get("id")
                or license_value.get("title")
                or license_value.get("url")
                or ""
            )

        creators = []
        for creator in metadata.get("creators") or []:
            if isinstance(creator, dict):
                creators.append(
                    str(creator.get("name") or creator.get("person_or_org", {}).get("name") or "")
                )
            elif creator:
                creators.append(str(creator))

        related: list[dict[str, str]] = []
        for item in metadata.get("related_identifiers") or []:
            if isinstance(item, dict):
                identifier = str(item.get("identifier") or "")
                relation = str(item.get("relation") or "")
                scheme = str(item.get("scheme") or item.get("resource_type") or "")
                if identifier:
                    related.append(
                        {"identifier": identifier, "relation": relation, "scheme": scheme}
                    )

        links = hit.get("links") or {}
        record_id = str(hit.get("id") or hit.get("record_id") or "")
        landing_url = (
            links.get("html")
            or links.get("self_html")
            or (f"https://zenodo.org/records/{record_id}" if record_id else "")
        )

        keywords_raw = metadata.get("keywords") or []
        if isinstance(keywords_raw, str):
            keywords = [keywords_raw]
        else:
            keywords = [str(value) for value in keywords_raw if value]

        doi = str(hit.get("doi") or metadata.get("doi") or "")
        record = DatasetRecord(
            source=self.name,
            source_id=record_id,
            title=strip_html(metadata.get("title") or "Sin título"),
            description=strip_html(
                metadata.get("description")
                or metadata.get("notes")
                or metadata.get("additional_descriptions")
                or ""
            ),
            doi=doi,
            landing_url=landing_url,
            license=str(license_value),
            published=str(hit.get("created") or metadata.get("publication_date") or ""),
            modified=str(hit.get("updated") or ""),
            creators=[value for value in creators if value],
            keywords=keywords,
            related_identifiers=related,
            files=files,
            matched_query=query,
        )
        return score_record(record)

    def search(self, query: str, limit: int) -> list[DatasetRecord]:
        unlimited = limit == 0
        page_size = 25 if unlimited else min(25, max(1, limit))
        page = 1
        records: list[DatasetRecord] = []

        # Zenodo usa sintaxis de Elasticsearch. El filtro reduce registros cerrados,
        # pero igualmente validamos que existan URLs públicas.
        search_query = f"({query}) AND access_right:open"

        while unlimited or len(records) < limit:
            params = {
                "q": search_query,
                "size": page_size if unlimited else min(page_size, limit - len(records)),
                "page": page,
                "sort": "bestmatch",
                "all_versions": "false",
            }
            payload = self.client.get_json(ZENODO_API, params=params)

            if isinstance(payload, list):
                hits = payload
            else:
                hits = (payload.get("hits") or {}).get("hits") or []

            if not hits:
                break

            records.extend(self._parse_hit(hit, query) for hit in hits)
            if len(hits) < params["size"]:
                break
            page += 1

        return records if unlimited else records[:limit]


class FigshareSource(Source):
    name = "figshare"

    def _parse_detail(self, detail: dict[str, Any], query: str) -> DatasetRecord:
        files: list[FileAsset] = []
        for item in detail.get("files") or []:
            name = str(item.get("name") or "unnamed")
            url = str(item.get("download_url") or "")
            if not url or not is_safe_https_url(url):
                continue

            checksum = ""
            supplied_md5 = item.get("supplied_md5") or item.get("computed_md5")
            if supplied_md5:
                checksum = f"md5:{supplied_md5}"

            files.append(
                FileAsset.build(
                    name=name,
                    url=url,
                    size=_safe_int(item.get("size")),
                    checksum=checksum,
                    source_file_id=str(item.get("id") or ""),
                )
            )

        license_value = detail.get("license") or ""
        if isinstance(license_value, dict):
            license_value = (
                license_value.get("name")
                or license_value.get("url")
                or str(license_value.get("id") or "")
            )

        creators = []
        for author in detail.get("authors") or []:
            if isinstance(author, dict):
                creators.append(str(author.get("full_name") or author.get("name") or ""))
            elif author:
                creators.append(str(author))

        related: list[dict[str, str]] = []
        resource_doi = str(detail.get("resource_doi") or "")
        if resource_doi:
            related.append(
                {
                    "identifier": resource_doi,
                    "relation": "isSupplementTo",
                    "scheme": "doi",
                }
            )
        for reference in detail.get("references") or []:
            if reference:
                related.append(
                    {
                        "identifier": str(reference),
                        "relation": "references",
                        "scheme": "url",
                    }
                )

        article_id = str(detail.get("id") or "")
        landing_url = str(
            detail.get("url_public_html")
            or detail.get("url")
            or (f"https://figshare.com/articles/dataset/{article_id}" if article_id else "")
        )

        keywords: list[str] = []
        for tag in detail.get("tags") or []:
            if isinstance(tag, dict):
                value = tag.get("name")
            else:
                value = tag
            if value:
                keywords.append(str(value))

        record = DatasetRecord(
            source=self.name,
            source_id=article_id,
            title=strip_html(detail.get("title") or "Sin título"),
            description=strip_html(detail.get("description") or ""),
            doi=str(detail.get("doi") or ""),
            landing_url=landing_url,
            license=str(license_value),
            published=str(detail.get("published_date") or detail.get("created_date") or ""),
            modified=str(detail.get("modified_date") or ""),
            creators=[value for value in creators if value],
            keywords=keywords,
            related_identifiers=related,
            files=files,
            matched_query=query,
        )
        return score_record(record)

    def search(self, query: str, limit: int) -> list[DatasetRecord]:
        unlimited = limit == 0
        page_size = 100 if unlimited else min(100, max(1, limit))
        page = 1
        records: list[DatasetRecord] = []

        while unlimited or len(records) < limit:
            payload = {
                "search_for": query,
                "item_type": 3,  # Dataset
                "page": page,
                "page_size": page_size if unlimited else min(page_size, limit - len(records)),
                "order": "published_date",
                "order_direction": "desc",
            }
            items = self.client.post_json(f"{FIGSHARE_API}/articles/search", payload)
            if not isinstance(items, list) or not items:
                break

            for item in items:
                article_id = item.get("id")
                if article_id is None:
                    continue
                try:
                    detail = self.client.get_json(f"{FIGSHARE_API}/articles/{article_id}")
                    records.append(self._parse_detail(detail, query))
                except (requests.RequestException, ValueError) as exc:
                    LOG.warning("Figshare %s no pudo leerse: %s", article_id, exc)

                if not unlimited and len(records) >= limit:
                    break

            if len(items) < payload["page_size"]:
                break
            page += 1

        return records if unlimited else records[:limit]


# ---------------------------------------------------------------------------
# Catálogo persistente
# ---------------------------------------------------------------------------


class Catalog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._create_schema()

    def _create_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS records (
                record_key TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                title TEXT NOT NULL,
                doi TEXT,
                landing_url TEXT,
                license TEXT,
                published TEXT,
                modified TEXT,
                score INTEGER NOT NULL,
                level TEXT NOT NULL,
                matched_query TEXT,
                metadata_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS assets (
                record_key TEXT NOT NULL,
                source_file_id TEXT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                size INTEGER,
                checksum TEXT,
                categories TEXT NOT NULL,
                downloaded_path TEXT,
                download_status TEXT,
                checksum_status TEXT,
                sha256 TEXT NOT NULL DEFAULT '',
                verification_status TEXT NOT NULL DEFAULT 'not_checked',
                verification_notes TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (record_key, url),
                FOREIGN KEY (record_key) REFERENCES records(record_key)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_records_score
                ON records(score DESC);
            CREATE INDEX IF NOT EXISTS idx_records_level
                ON records(level);
            """
        )
        self._migrate_schema()
        self.conn.commit()

    def _migrate_schema(self) -> None:
        """Agrega columnas de v2.1.0 a catálogos creados con v2.0.0."""
        existing = {row[1] for row in self.conn.execute("PRAGMA table_info(records)").fetchall()}
        if "benchmark_score" not in existing:
            self.conn.execute(
                "ALTER TABLE records ADD COLUMN benchmark_score INTEGER NOT NULL DEFAULT 0"
            )
        if "relevance_score" not in existing:
            self.conn.execute(
                "ALTER TABLE records ADD COLUMN relevance_score INTEGER NOT NULL DEFAULT 0"
            )
        if "domain_relevant" not in existing:
            self.conn.execute(
                "ALTER TABLE records ADD COLUMN domain_relevant INTEGER NOT NULL DEFAULT 0"
            )
        if "utility_class" not in existing:
            self.conn.execute(
                "ALTER TABLE records ADD COLUMN utility_class TEXT NOT NULL DEFAULT 'incomplete'"
            )
        asset_existing = {
            row[1] for row in self.conn.execute("PRAGMA table_info(assets)").fetchall()
        }
        if "sha256" not in asset_existing:
            self.conn.execute("ALTER TABLE assets ADD COLUMN sha256 TEXT NOT NULL DEFAULT ''")
        if "verification_status" not in asset_existing:
            self.conn.execute(
                "ALTER TABLE assets ADD COLUMN verification_status TEXT NOT NULL DEFAULT 'not_checked'"
            )
        if "verification_notes" not in asset_existing:
            self.conn.execute(
                "ALTER TABLE assets ADD COLUMN verification_notes TEXT NOT NULL DEFAULT ''"
            )
        self.conn.commit()

    def upsert(self, record: DatasetRecord) -> None:
        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            """
            INSERT INTO records (
                record_key, source, source_id, title, doi, landing_url, license,
                published, modified, score, level, matched_query, metadata_json,
                updated_at, benchmark_score, relevance_score, domain_relevant,
                utility_class
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(record_key) DO UPDATE SET
                title=excluded.title,
                doi=excluded.doi,
                landing_url=excluded.landing_url,
                license=excluded.license,
                published=excluded.published,
                modified=excluded.modified,
                score=MAX(records.score, excluded.score),
                level=CASE
                    WHEN excluded.score >= records.score THEN excluded.level
                    ELSE records.level
                END,
                matched_query=CASE
                    WHEN instr(records.matched_query, excluded.matched_query) > 0
                    THEN records.matched_query
                    ELSE records.matched_query || ' | ' || excluded.matched_query
                END,
                metadata_json=CASE
                    WHEN excluded.score >= records.score THEN excluded.metadata_json
                    ELSE records.metadata_json
                END,
                updated_at=excluded.updated_at,
                benchmark_score=excluded.benchmark_score,
                relevance_score=excluded.relevance_score,
                domain_relevant=CASE
                    WHEN records.domain_relevant = 1 THEN 1
                    ELSE excluded.domain_relevant
                END,
                utility_class=CASE
                    WHEN excluded.score >= records.score THEN excluded.utility_class
                    ELSE records.utility_class
                END
            """,
            (
                record.key,
                record.source,
                record.source_id,
                record.title,
                record.doi,
                record.landing_url,
                record.license,
                record.published,
                record.modified,
                record.score,
                record.level,
                record.matched_query,
                json.dumps(record.to_dict(), ensure_ascii=False),
                now,
                record.benchmark_score,
                record.relevance_score,
                1 if record.domain_relevant else 0,
                record.utility_class,
            ),
        )

        for asset in record.files:
            self.conn.execute(
                """
                INSERT INTO assets (
                    record_key, source_file_id, name, url, size, checksum,
                    categories, downloaded_path, download_status, checksum_status,
                    sha256, verification_status, verification_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(record_key, url) DO UPDATE SET
                    name=excluded.name,
                    size=excluded.size,
                    checksum=excluded.checksum,
                    categories=excluded.categories,
                    source_file_id=excluded.source_file_id
                """,
                (
                    record.key,
                    asset.source_file_id,
                    asset.name,
                    asset.url,
                    asset.size,
                    asset.checksum,
                    json.dumps(asset.categories, ensure_ascii=False),
                    asset.downloaded_path,
                    asset.download_status,
                    asset.checksum_status,
                    asset.sha256,
                    asset.verification_status,
                    asset.verification_notes,
                ),
            )
        self.conn.commit()

    def update_asset_status(
        self,
        record_key: str,
        url: str,
        *,
        downloaded_path: str,
        download_status: str,
        checksum_status: str,
        sha256: str = "",
    ) -> None:
        self.conn.execute(
            """
            UPDATE assets
            SET downloaded_path=?, download_status=?, checksum_status=?, sha256=?
            WHERE record_key=? AND url=?
            """,
            (
                downloaded_path,
                download_status,
                checksum_status,
                sha256,
                record_key,
                url,
            ),
        )
        self.conn.commit()

    def update_asset_verification(
        self,
        record_key: str,
        url: str,
        *,
        verification_status: str,
        verification_notes: str,
        observed_size: int | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE assets
            SET verification_status=?, verification_notes=?,
                size=COALESCE(size, ?)
            WHERE record_key=? AND url=?
            """,
            (verification_status, verification_notes, observed_size, record_key, url),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


# ---------------------------------------------------------------------------
# Descarga segura, reanudable y verificable
# ---------------------------------------------------------------------------


def parse_checksum(value: str) -> tuple[str, str] | None:
    if not value:
        return None
    cleaned = value.strip().casefold()
    if ":" in cleaned:
        algorithm, digest = cleaned.split(":", 1)
    else:
        digest = cleaned
        if len(digest) == 32:
            algorithm = "md5"
        elif len(digest) == 64:
            algorithm = "sha256"
        else:
            return None

    algorithm = algorithm.replace("-", "")
    if algorithm not in {"md5", "sha1", "sha256", "sha512"}:
        return None
    if not re.fullmatch(r"[0-9a-f]+", digest):
        return None
    return algorithm, digest


def digest_file(path: Path, algorithm: str, chunk_size: int = 1024 * 1024) -> str:
    hasher = hashlib.new(algorithm)
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_checksum(path: Path, expected: str) -> str:
    parsed = parse_checksum(expected)
    if parsed is None:
        return "not_available"
    algorithm, digest = parsed
    actual = digest_file(path, algorithm)
    return "ok" if actual.casefold() == digest.casefold() else "mismatch"


def _progress_bar(total: int | None, initial: int, name: str):
    if tqdm is None:
        return None
    return tqdm(
        total=total or None,
        initial=initial,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        desc=name[:45],
        leave=False,
    )


def download_asset(
    client: HttpClient,
    asset: FileAsset,
    destination: Path,
    *,
    max_file_bytes: int,
    chunk_size: int = 1024 * 1024,
) -> tuple[str, str]:
    """
    Descarga con archivo .part y HTTP Range. Devuelve:
        (download_status, checksum_status)
    """
    if not is_safe_https_url(asset.url):
        return "rejected_url", "not_checked"

    if asset.size is not None and asset.size > max_file_bytes:
        return "skipped_too_large", "not_checked"

    destination.parent.mkdir(parents=True, exist_ok=True)
    part_path = destination.with_name(destination.name + ".part")

    if destination.exists():
        if asset.size is None or destination.stat().st_size == asset.size:
            checksum_status = verify_checksum(destination, asset.checksum)
            if checksum_status in {"ok", "not_available"}:
                return "already_present", checksum_status

    initial = part_path.stat().st_size if part_path.exists() else 0
    headers: dict[str, str] = {}
    if initial > 0:
        headers["Range"] = f"bytes={initial}-"

    client.rate_limiter.wait(asset.url)
    response = client.session.get(
        asset.url,
        stream=True,
        timeout=max(client.timeout, 120.0),
        headers=headers,
    )

    if not is_safe_https_url(str(response.url)):
        response.close()
        return "rejected_redirect", "not_checked"

    if response.status_code == 416 and asset.size and initial == asset.size:
        part_path.replace(destination)
        checksum_status = verify_checksum(destination, asset.checksum)
        return "downloaded", checksum_status

    if response.status_code not in {200, 206}:
        raise requests.HTTPError(
            f"GET {asset.url} -> HTTP {response.status_code}",
            response=response,
        )

    if initial > 0 and response.status_code == 200:
        # El servidor ignoró Range. Reiniciamos para evitar concatenar basura.
        initial = 0
        part_path.unlink(missing_ok=True)

    reported = _safe_int(response.headers.get("Content-Length"))
    total = asset.size or ((reported + initial) if reported is not None else None)

    if total is not None and total > max_file_bytes:
        response.close()
        return "skipped_too_large", "not_checked"

    bar = _progress_bar(total, initial, destination.name)
    mode = "ab" if initial else "wb"

    try:
        with part_path.open(mode) as handle:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                handle.write(chunk)
                if bar is not None:
                    bar.update(len(chunk))

                current_size = handle.tell()
                if current_size > max_file_bytes:
                    raise RuntimeError(f"El archivo excedió el límite de {max_file_bytes} bytes")
    finally:
        if bar is not None:
            bar.close()
        response.close()

    if asset.size is not None and part_path.stat().st_size != asset.size:
        return "size_mismatch", "not_checked"

    part_path.replace(destination)
    checksum_status = verify_checksum(destination, asset.checksum)
    if checksum_status == "mismatch":
        destination.rename(destination.with_suffix(destination.suffix + ".bad-checksum"))
        return "checksum_mismatch", checksum_status

    return "downloaded", checksum_status


def archive_inventory(path: Path, max_entries: int = 20_000) -> dict[str, Any]:
    """Inventory an archive without extracting it.

    The report includes path-safety signals and compressed/uncompressed totals.
    It is an integrity screen, not a guarantee that extraction is safe.
    """

    inventory: dict[str, Any] = {
        "archive": path.name,
        "entries": [],
        "truncated": False,
        "detected_categories": [],
        "unsafe_paths": [],
        "encrypted_entries": 0,
        "total_uncompressed_bytes": 0,
        "total_compressed_bytes": None,
        "compression_ratio": None,
        "error": "",
    }

    def unsafe_member(name: str) -> bool:
        normalized = name.replace("\\", "/")
        pure = PurePosixPath(normalized)
        return pure.is_absolute() or ".." in pure.parts

    try:
        entries: list[dict[str, Any]] = []
        lowered = path.name.casefold()
        if lowered.endswith(".zip"):
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    entries.append(
                        {
                            "name": info.filename,
                            "size": info.file_size,
                            "compressed_size": info.compress_size,
                            "encrypted": bool(info.flag_bits & 0x1),
                        }
                    )
            inventory["total_compressed_bytes"] = sum(
                int(entry["compressed_size"] or 0) for entry in entries
            )
        elif lowered.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")):
            with tarfile.open(path, mode="r:*") as archive:
                for member in archive.getmembers():
                    if member.isfile():
                        entries.append(
                            {
                                "name": member.name,
                                "size": member.size,
                                "compressed_size": None,
                                "encrypted": False,
                            }
                        )
            inventory["total_compressed_bytes"] = path.stat().st_size
        else:
            inventory["error"] = "Formato de archivo no inspeccionable con la biblioteca estándar"
            return inventory

        total_entries = len(entries)
        if total_entries > max_entries:
            inventory["truncated"] = True
            entries = entries[:max_entries]

        categories: set[str] = set()
        clean_entries: list[dict[str, Any]] = []
        unsafe_paths: list[str] = []
        encrypted_count = 0
        total_uncompressed = 0
        for entry in entries:
            name = str(entry["name"])
            entry_categories = sorted(infer_categories(name))
            categories.update(entry_categories)
            is_unsafe = unsafe_member(name)
            if is_unsafe:
                unsafe_paths.append(name)
            if entry.get("encrypted"):
                encrypted_count += 1
            total_uncompressed += int(entry.get("size") or 0)
            clean_entries.append(
                {
                    "name": name,
                    "categories": entry_categories,
                    "size": entry.get("size"),
                    "compressed_size": entry.get("compressed_size"),
                    "unsafe_path": is_unsafe,
                    "encrypted": bool(entry.get("encrypted")),
                }
            )

        compressed = inventory["total_compressed_bytes"]
        inventory["entries"] = clean_entries
        inventory["entry_count"] = total_entries
        inventory["detected_categories"] = sorted(categories)
        inventory["unsafe_paths"] = unsafe_paths
        inventory["encrypted_entries"] = encrypted_count
        inventory["total_uncompressed_bytes"] = total_uncompressed
        if isinstance(compressed, int) and compressed > 0:
            inventory["compression_ratio"] = round(total_uncompressed / compressed, 3)
    except (zipfile.BadZipFile, tarfile.TarError, OSError) as exc:
        inventory["error"] = str(exc)

    return inventory


# ---------------------------------------------------------------------------
# Exportes legibles
# ---------------------------------------------------------------------------


def export_catalog(records: Sequence[DatasetRecord], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "catalog.json"
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(
            [record.to_dict() for record in records],
            handle,
            indent=2,
            ensure_ascii=False,
        )

    jsonl_path = output_dir / "catalog.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    csv_path = output_dir / "catalog.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "level",
                "score",
                "benchmark_score",
                "relevance_score",
                "domain_relevant",
                "utility_class",
                "source",
                "source_id",
                "title",
                "doi",
                "license",
                "published",
                "files",
                "total_size_bytes",
                "categories",
                "matched_query",
                "landing_url",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "level": record.level,
                    "score": record.score,
                    "benchmark_score": record.benchmark_score,
                    "relevance_score": record.relevance_score,
                    "domain_relevant": "yes" if record.domain_relevant else "no",
                    "source": record.source,
                    "source_id": record.source_id,
                    "title": record.title,
                    "doi": record.doi,
                    "license": record.license,
                    "published": record.published,
                    "files": len(record.files),
                    "total_size_bytes": record.total_size,
                    "categories": ",".join(sorted(record.categories)),
                    "matched_query": record.matched_query,
                    "landing_url": record.landing_url,
                }
            )

    report_path = output_dir / "REPORT.md"
    counts = {
        level: sum(record.level == level for record in records)
        for level in ("gold", "silver", "bronze")
    }
    with report_path.open("w", encoding="utf-8") as handle:
        handle.write("# SPM-Kit Data Hunter Report\n\n")
        handle.write(f"Generado: {datetime.now(UTC).isoformat()}\n\n")
        handle.write(
            f"Registros únicos: **{len(records)}**  \n"
            f"Gold: **{counts['gold']}**, Silver: **{counts['silver']}**, "
            f"Bronze: **{counts['bronze']}**\n\n"
        )
        handle.write("## Ranking\n\n")
        handle.write(
            "| Nivel | Score | Benchmark | Relevancia | Domain | Fuente | Título | Categorías | DOI |\n"
        )
        handle.write("|---|---:|---:|---:|---:|---|---|---|---|\n")
        for record in records[:100]:
            title = record.title.replace("|", "\\|")
            cats = ", ".join(sorted(record.categories))
            doi = record.doi or ""
            relevance = "yes" if record.domain_relevant else "no"
            handle.write(
                f"| {record.level.title()} | {record.score} | {record.benchmark_score} "
                f"| {record.relevance_score} | {relevance} | {record.source} | "
                f"{title} | {cats} | {doi} |\n"
            )


def print_ranking(records: Sequence[DatasetRecord], top: int) -> None:
    if not records:
        print("No se encontraron candidatos.")
        return

    print()
    print("=" * 100)
    print(f"{'NIVEL':<8} {'PTS':>3}  DOMAIN  {'FUENTE':<10} TÍTULO")
    print("=" * 100)
    for record in records[:top]:
        title = record.title
        if len(title) > 58:
            title = title[:55] + "..."
        domain_mark = "✓" if record.domain_relevant else "✗"
        print(
            f"{record.level.upper():<8} {record.score:>3}  {domain_mark:<6} "
            f"{record.source:<10} {title}"
        )
        print(f"{'':<24} {record.landing_url}")
        cats_str = ", ".join(sorted(record.categories))
        if not record.domain_relevant:
            cats_str += " | gate: sin evidencia AFM/SPM"
        print(f"{'':<24} categorías: {cats_str}")
    print("=" * 100)


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------


def merge_records(records: Iterable[DatasetRecord]) -> list[DatasetRecord]:
    merged: dict[str, DatasetRecord] = {}
    queries: dict[str, list[str]] = {}

    for record in records:
        normalize_record(record)
        existing = merged.get(record.key)
        queries.setdefault(record.key, [])
        if record.matched_query and record.matched_query not in queries[record.key]:
            queries[record.key].append(record.matched_query)

        if existing is None:
            merged[record.key] = record
            continue

        # Preferir versión relevante sobre irrelevante, incluso si tiene menor score.
        if record.domain_relevant and not existing.domain_relevant:
            primary, secondary = record, existing
        elif existing.domain_relevant and not record.domain_relevant:
            primary, secondary = existing, record
        elif record.score > existing.score:
            primary, secondary = record, existing
        else:
            primary, secondary = existing, record

        files = {asset.url: asset for asset in primary.files if asset.url}
        for asset in secondary.files:
            if asset.url and asset.url not in files:
                files[asset.url] = asset
        primary.files = list(files.values())
        primary.keywords = list(dict.fromkeys(primary.keywords + secondary.keywords))
        primary.related_identifiers = primary.related_identifiers + [
            item
            for item in secondary.related_identifiers
            if item not in primary.related_identifiers
        ]
        for field_name in ("doi", "landing_url", "license", "published", "modified"):
            if not getattr(primary, field_name):
                setattr(primary, field_name, getattr(secondary, field_name))
        normalize_record(primary)
        score_record(primary)
        merged[record.key] = primary

    for key, record in merged.items():
        record.matched_query = " | ".join(queries[key])
        score_record(record)

    return sorted(
        merged.values(),
        key=lambda item: (
            1 if item.domain_relevant else 0,
            {"gold": 3, "silver": 2, "bronze": 1}.get(item.level, 0),
            item.score,
            item.published,
        ),
        reverse=True,
    )


def license_allowed(record: DatasetRecord, require_open_license: bool) -> bool:
    if not require_open_license:
        return True
    return bool(record.license and contains_any(record.license, OPEN_LICENSE_HINTS))


def select_assets(
    record: DatasetRecord,
    categories: set[str],
) -> list[FileAsset]:
    if not categories:
        return list(record.files)
    return [asset for asset in record.files if categories.intersection(asset.categories)]


def write_record_metadata(record: DatasetRecord, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "metadata.json").open("w", encoding="utf-8") as handle:
        json.dump(record.to_dict(), handle, indent=2, ensure_ascii=False)

    with (folder / "WHY_THIS_DATASET.md").open("w", encoding="utf-8") as handle:
        handle.write(f"# {record.title}\n\n")
        handle.write(f"- Nivel: **{record.level.title()}**\n")
        handle.write(f"- Puntaje final: **{record.score}/100**\n")
        handle.write(f"- Benchmark score: **{record.benchmark_score}/100**\n")
        handle.write(f"- Relevance score: **{record.relevance_score}/100**\n")
        handle.write(f"- Domain relevant: **{'yes' if record.domain_relevant else 'no'}**\n")
        handle.write(f"- Utility class: **{record.utility_class}**\n")
        handle.write(f"- Fuente: `{record.source}`\n")
        handle.write(f"- DOI: `{record.doi or 'no informado'}`\n")
        handle.write(f"- Licencia: `{record.license or 'no informada'}`\n")
        handle.write(f"- URL: {record.landing_url}\n\n")
        handle.write("## Razones de relevancia\n\n")
        for reason in record.relevance_reasons:
            handle.write(f"- {reason}\n")
        handle.write("\n## Razones del benchmark\n\n")
        for reason in record.score_reasons:
            handle.write(f"- {reason}\n")


def download_record(
    record: DatasetRecord,
    *,
    client: HttpClient,
    catalog: Catalog,
    output_dir: Path,
    categories: set[str],
    max_file_bytes: int,
    max_record_bytes: int,
    inspect_archives: bool,
) -> None:
    folder_name = (
        f"{record.level}_{record.score:03d}_"
        f"{sanitize_component(record.source)}_"
        f"{sanitize_component(record.source_id)}_"
        f"{sanitize_component(record.title, 70)}"
    )
    record_folder = output_dir / "datasets" / folder_name
    write_record_metadata(record, record_folder)

    assets = select_assets(record, categories)
    known_total = sum(asset.size or 0 for asset in assets)
    if known_total > max_record_bytes:
        LOG.warning(
            "Se omite %s: tamaño conocido del registro %.2f GB supera el límite.",
            record.title,
            known_total / (1024**3),
        )
        return

    downloaded_total = 0
    inventory_entries: list[dict[str, Any]] = []

    for index, asset in enumerate(assets, start=1):
        if asset.size is not None and downloaded_total + asset.size > max_record_bytes:
            LOG.warning("Límite por registro alcanzado en %s", record.title)
            break

        filename = sanitize_component(Path(asset.name).name, 180)
        if not filename:
            filename = f"file_{index}"
        destination = record_folder / filename

        try:
            status, checksum_status = download_asset(
                client,
                asset,
                destination,
                max_file_bytes=max_file_bytes,
            )
        except (requests.RequestException, OSError, RuntimeError) as exc:
            LOG.error("Error descargando %s: %s", asset.name, exc)
            status, checksum_status = "error", "not_checked"

        asset.download_status = status
        asset.checksum_status = checksum_status
        if destination.exists():
            asset.downloaded_path = str(destination.resolve())
            asset.sha256 = digest_file(destination, "sha256")
            downloaded_total += destination.stat().st_size

        catalog.update_asset_status(
            record.key,
            asset.url,
            downloaded_path=asset.downloaded_path,
            download_status=status,
            checksum_status=checksum_status,
            sha256=asset.sha256,
        )

        if inspect_archives and destination.exists() and "archive" in asset.categories:
            inventory_entries.append(archive_inventory(destination))

    if inventory_entries:
        with (record_folder / "archive_inventory.json").open("w", encoding="utf-8") as handle:
            json.dump(inventory_entries, handle, indent=2, ensure_ascii=False)

    # Reescribir metadata con estados finales de descarga.
    write_record_metadata(record, record_folder)


def resolve_queries(args: argparse.Namespace) -> list[str]:
    queries: list[str] = []
    if args.preset:
        for preset in args.preset:
            queries.extend(QUERY_PRESETS[preset])
    if args.query:
        queries.extend(args.query)

    if not queries:
        queries.extend(QUERY_PRESETS["all"])

    deduplicated: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = query.strip()
        if normalized and normalized.casefold() not in seen:
            seen.add(normalized.casefold())
            deduplicated.append(normalized)
    return deduplicated


def build_sources(names: Sequence[str], client: HttpClient) -> list[Source]:
    selected = set(names)
    if "all" in selected:
        selected = {"zenodo", "figshare"}

    sources: list[Source] = []
    if "zenodo" in selected:
        sources.append(ZenodoSource(client))
    if "figshare" in selected:
        sources.append(FigshareSource(client))
    return sources


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Descubre y cura datasets públicos con datos SPM/AFM crudos, "
            "resultados procesados, métodos y código."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--source",
        action="append",
        choices=["all", "zenodo", "figshare"],
        default=None,
        help="Fuente. Se puede repetir.",
    )
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="Consulta de búsqueda. Se puede repetir.",
    )
    parser.add_argument(
        "--preset",
        action="append",
        choices=sorted(QUERY_PRESETS),
        default=[],
        help="Conjunto de consultas temáticas. Se puede repetir.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Máximo de resultados por fuente y consulta; 0 recorre hasta agotar.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=30,
        help="Cantidad de candidatos mostrados en pantalla.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Carpeta del catálogo y las descargas.",
    )
    parser.add_argument(
        "--levels",
        nargs="+",
        choices=["gold", "silver", "bronze"],
        default=["gold", "silver"],
        help="Niveles elegibles para descarga.",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=0,
        help="Puntaje mínimo para conservar un candidato.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Descargar archivos. Sin esta opción solo se crea el catálogo.",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        choices=[
            "raw",
            "processed",
            "code",
            "documentation",
            "archive",
            "image",
            "other",
        ],
        default=["raw", "processed", "code", "documentation", "archive"],
        help="Categorías de archivos a descargar.",
    )
    parser.add_argument(
        "--max-file-mb",
        type=float,
        default=2048.0,
        help="Tamaño máximo por archivo; 0 significa sin límite funcional.",
    )
    parser.add_argument(
        "--max-record-gb",
        type=float,
        default=10.0,
        help="Tamaño máximo por registro; 0 significa sin límite funcional.",
    )
    parser.add_argument(
        "--require-open-license",
        action="store_true",
        help="Conservar solo registros con una licencia abierta reconocible.",
    )
    parser.add_argument(
        "--inspect-archives",
        action="store_true",
        help="Inventariar ZIP/TAR descargados sin extraerlos.",
    )
    parser.add_argument(
        "--rate-seconds",
        type=float,
        default=1.05,
        help="Espera mínima por host entre solicitudes.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=45.0,
        help="Timeout HTTP para búsquedas.",
    )
    parser.add_argument(
        "--user-agent",
        default=os.getenv("SPMKIT_HUNTER_USER_AGENT", DEFAULT_USER_AGENT),
        help="User-Agent responsable. Puede definirse por variable de entorno.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Mostrar más detalles de ejecución.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Ejecutar pruebas internas y salir.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )
    return parser


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def run_self_tests() -> None:
    assert full_suffix("curve.jpk-force") == ".jpk-force"
    assert full_suffix("bundle.tar.gz") == ".tar.gz"
    assert "raw" in infer_categories("sample_raw.nid")
    assert "processed" in infer_categories("roughness_results.csv")
    assert "code" in infer_categories("analysis.ipynb")
    assert "documentation" in infer_categories("README.md")
    assert "archive" in infer_categories("all_data.zip")
    assert sanitize_component("../../evil:name") == "evil_name"
    assert parse_checksum("md5:d41d8cd98f00b204e9800998ecf8427e") == (
        "md5",
        "d41d8cd98f00b204e9800998ecf8427e",
    )

    # ── Gold AFM válido ──────────────────────────────────────────────
    sample = DatasetRecord(
        source="test",
        source_id="1",
        title="AFM raw and processed force spectroscopy benchmark",
        description=(
            "Includes calibration, cantilever spring constant, scripts and "
            "processed Young modulus results."
        ),
        doi="10.0000/example",
        license="CC-BY-4.0",
        related_identifiers=[
            {"identifier": "10.0000/paper", "relation": "isSupplementTo", "scheme": "doi"}
        ],
        files=[
            FileAsset.build(
                name="raw_curves.jpk-force",
                url="https://example.org/raw_curves.jpk-force",
            ),
            FileAsset.build(
                name="processed_results.csv",
                url="https://example.org/processed_results.csv",
            ),
            FileAsset.build(
                name="analysis.ipynb",
                url="https://example.org/analysis.ipynb",
            ),
            FileAsset.build(
                name="README.md",
                url="https://example.org/README.md",
            ),
        ],
    )
    score_record(sample)
    assert sample.level == "gold", (sample.score, sample.score_reasons)
    assert sample.score >= 72
    assert sample.domain_relevant is True

    # ── Falso positivo ecológico ─────────────────────────────────────
    eco = DatasetRecord(
        source="test",
        source_id="fp-eco",
        title="Regional niche differentiation and reciprocal transfer analyses for Polistes rothneyi",
        description="Ecological study with statistical models and field observations.",
        doi="10.0000/eco",
        license="CC-BY-4.0",
        files=[
            FileAsset.build(name="raw_data.csv", url="https://example.org/raw_data.csv"),
            FileAsset.build(name="processed_results.csv", url="https://example.org/results.csv"),
            FileAsset.build(name="analysis.py", url="https://example.org/analysis.py"),
            FileAsset.build(name="README.md", url="https://example.org/README.md"),
            FileAsset.build(name="methods.pdf", url="https://example.org/methods.pdf"),
        ],
    )
    score_record(eco)
    assert eco.domain_relevant is False, eco.relevance_reasons
    assert eco.level == "bronze"
    assert eco.score <= 39, eco.score

    # ── Formato nativo .nid aprueba relevancia ───────────────────────
    nid = DatasetRecord(
        source="test",
        source_id="nid-test",
        title="Surface characterization measurements",
        files=[
            FileAsset.build(name="sample.nid", url="https://example.org/sample.nid"),
        ],
    )
    score_record(nid)
    assert nid.domain_relevant is True, nid.relevance_reasons
    assert nid.relevance_score >= 60

    # ── Frase exacta "atomic force microscopy" ────────────────────────
    afm_phrase = DatasetRecord(
        source="test",
        source_id="afm-phrase",
        title="Atomic force microscopy topography dataset",
        files=[
            FileAsset.build(name="raw_data.csv", url="https://example.org/raw_data.csv"),
            FileAsset.build(name="results.csv", url="https://example.org/results.csv"),
        ],
    )
    score_record(afm_phrase)
    assert afm_phrase.domain_relevant is True, afm_phrase.relevance_reasons

    # ── AFM aislado sin corroboración ────────────────────────────────
    afm_isolated = DatasetRecord(
        source="test",
        source_id="afm-iso",
        title="AFM dataset",
        files=[
            FileAsset.build(name="raw_data.csv", url="https://example.org/raw_data.csv"),
            FileAsset.build(name="results.csv", url="https://example.org/results.csv"),
        ],
    )
    score_record(afm_isolated)
    assert afm_isolated.domain_relevant is False or afm_isolated.level == "bronze", (
        afm_isolated.domain_relevant,
        afm_isolated.level,
        afm_isolated.relevance_reasons,
    )

    # ── Substring no debe activar sigla ──────────────────────────────
    no_afm = DatasetRecord(
        source="test",
        source_id="no-afm",
        title="Staff meeting notes and metrics dashboard",
        files=[
            FileAsset.build(name="data.csv", url="https://example.org/data.csv"),
        ],
    )
    score_record(no_afm)
    assert (
        "AFM" not in " ".join(no_afm.relevance_reasons).upper() or no_afm.domain_relevant is False
    )

    print("Self-test: OK")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_test:
        run_self_tests()
        return 0

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s | %(message)s",
    )

    if args.limit < 0:
        parser.error("--limit no puede ser negativo")
    if not 0 <= args.min_score <= 100:
        parser.error("--min-score debe estar entre 0 y 100")
    if args.max_file_mb < 0 or args.max_record_gb < 0:
        parser.error("Los límites de tamaño no pueden ser negativos")

    output_dir: Path = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    client = HttpClient(
        timeout=args.timeout,
        user_agent=args.user_agent,
        rate_seconds=args.rate_seconds,
    )
    source_names = args.source or ["all"]
    sources = build_sources(source_names, client)
    queries = resolve_queries(args)
    catalog = Catalog(output_dir / "catalog.sqlite3")

    discovered: list[DatasetRecord] = []

    try:
        for query_index, query in enumerate(queries, start=1):
            LOG.info(
                "Consulta %d/%d: %s",
                query_index,
                len(queries),
                query,
            )
            for source in sources:
                try:
                    LOG.info("Buscando en %s...", source.name)
                    records = source.search(query, args.limit)
                    LOG.info(
                        "%s devolvió %d candidatos",
                        source.name,
                        len(records),
                    )
                    for record in records:
                        if record.score < args.min_score:
                            continue
                        if not license_allowed(record, args.require_open_license):
                            continue
                        catalog.upsert(record)
                        discovered.append(record)
                except (requests.RequestException, ValueError, KeyError) as exc:
                    LOG.error("Falló la búsqueda en %s: %s", source.name, exc)

        records = merge_records(discovered)
        export_catalog(records, output_dir)
        print_ranking(records, args.top)

        print(f"\nCatálogo JSON/CSV/SQLite guardado en: {output_dir.resolve()}")
        print(
            f"Candidatos: {len(records)} "
            f"(Gold {sum(r.level == 'gold' for r in records)}, "
            f"Silver {sum(r.level == 'silver' for r in records)}, "
            f"Bronze {sum(r.level == 'bronze' for r in records)})"
        )

        if args.download:
            chosen = [record for record in records if record.level in set(args.levels)]
            print(f"\nDescargando {len(chosen)} registros seleccionados...")
            for record in chosen:
                LOG.info(
                    "[%s %d] %s",
                    record.level.upper(),
                    record.score,
                    record.title,
                )
                download_record(
                    record,
                    client=client,
                    catalog=catalog,
                    output_dir=output_dir,
                    categories=set(args.categories),
                    max_file_bytes=(
                        int(args.max_file_mb * 1024**2) if args.max_file_mb else 2**63 - 1
                    ),
                    max_record_bytes=(
                        int(args.max_record_gb * 1024**3) if args.max_record_gb else 2**63 - 1
                    ),
                    inspect_archives=args.inspect_archives,
                )

            # Reflejar estados de descarga en los JSON finales.
            export_catalog(records, output_dir)
            print(f"Descargas guardadas en: {(output_dir / 'datasets').resolve()}")
        else:
            print(
                "\nModo catálogo: no se descargó ningún archivo. "
                "Usa --download después de revisar REPORT.md."
            )

        return 0
    finally:
        catalog.close()


if __name__ == "__main__":
    raise SystemExit(main())
