"""Lightweight remote file probes.

These checks establish reachability and obvious transport problems. They do not
validate scientific content and do not replace checksum verification after a
full download.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import requests

from .legacy import FileAsset, HttpClient, is_safe_https_url


@dataclass(slots=True)
class VerificationResult:
    status: str
    notes: str
    observed_size: int | None = None
    final_url: str = ""
    checked_at: str = ""

    def __post_init__(self) -> None:
        if not self.checked_at:
            self.checked_at = datetime.now(UTC).isoformat()


def _content_length(response: requests.Response) -> int | None:
    value = response.headers.get("Content-Length")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def probe_asset(client: HttpClient, asset: FileAsset) -> VerificationResult:
    if not is_safe_https_url(asset.url):
        return VerificationResult("rejected_url", "URL is not an allowed public HTTPS URL")

    response: requests.Response | None = None
    try:
        try:
            response = client.request("HEAD", asset.url, allow_redirects=True)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status not in {403, 405}:
                raise
            # Some repositories reject HEAD. A one-byte range request verifies
            # reachability without downloading the whole object.
            response = client.session.get(
                asset.url,
                headers={"Range": "bytes=0-0"},
                stream=True,
                allow_redirects=True,
                timeout=client.timeout,
            )
            if response.status_code not in {200, 206}:
                raise requests.HTTPError(
                    f"GET range {asset.url} -> HTTP {response.status_code}",
                    response=response,
                ) from exc

        final_url = str(response.url)
        if not is_safe_https_url(final_url):
            return VerificationResult(
                "rejected_redirect",
                "Redirect resolved to a disallowed destination",
                final_url=final_url,
            )

        observed_size = _content_length(response)
        content_range = response.headers.get("Content-Range", "")
        if "/" in content_range:
            tail = content_range.rsplit("/", 1)[-1]
            if tail.isdigit():
                observed_size = int(tail)

        if observed_size == 0:
            return VerificationResult("empty", "Remote object reports zero bytes", 0, final_url)
        if asset.size is not None and observed_size is not None and asset.size != observed_size:
            return VerificationResult(
                "size_mismatch",
                f"Repository metadata size={asset.size}, remote size={observed_size}",
                observed_size,
                final_url,
            )
        return VerificationResult(
            "reachable",
            "Remote object is reachable; content was not fully downloaded",
            observed_size,
            final_url,
        )
    except requests.RequestException as exc:
        return VerificationResult("failed", str(exc)[:500])
    finally:
        if response is not None:
            response.close()
