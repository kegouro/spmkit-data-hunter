# Threat Model

Data Hunter consumes untrusted metadata, URLs, filenames, and archives from
public repositories.

## Assets to protect

- local filesystem;
- network boundary;
- API tokens;
- catalog integrity;
- downloaded scientific evidence;
- user disk space and time.

## Primary threats

1. Path traversal in filenames or archive entries.
2. Redirects to loopback, private, link-local, or metadata-service addresses.
3. Oversized files and deceptive `Content-Length`.
4. Zip bombs and extreme archive entry counts.
5. Checksum mismatch.
6. Partial-file corruption.
7. Malformed JSON and schema drift.
8. Tokens leaked into logs, prompts, or exports.
9. Duplicate identifiers causing evidence from unrelated records to merge.
10. False confidence caused by weak classification.

## Controls

- HTTPS requirement;
- filename sanitization;
- no archive extraction during inventory;
- explicit download acknowledgement for unbounded runs;
- resumable `.part` files;
- repository checksum verification plus persisted local SHA-256 after download;
- unique constraints and conservative identity rules;
- offline fixtures for malformed responses;
- no credential values in `doctor` output;
- utility classes that separate reader fixtures from benchmarks.

## Residual risks

The current release does not perform full DNS rebinding protection and does not
yet implement a format-aware archive bomb score. These remain high-priority
hardening tasks.
