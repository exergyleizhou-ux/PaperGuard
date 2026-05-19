# Security & Responsible Disclosure

If you discover a vulnerability that could let PaperGuard mishandle untrusted
input files (e.g. crafted .docx / .pdf / .xlsx triggering parser crashes or
arbitrary code execution), please report it privately.

**Do not open a public issue.** Instead, open a private security advisory on
GitHub, or email the maintainer listed in `pyproject.toml`.

We will acknowledge reports within 7 days and aim to release a patched version
within 30 days for valid issues.

## Scope

PaperGuard parses files supplied by users. The following are in scope:

- Path traversal or sandbox escape via crafted archives (xlsx/docx are ZIP).
- Memory exhaustion via crafted PDFs or large XML payloads.
- Code injection via malformed metadata.

## Out of Scope

- Issues that require attacker control of the user's local filesystem.
- Network API misuse (OpenAlex, CrossRef, Unpaywall are external services).
- Cosmetic bugs in the terminal report.
