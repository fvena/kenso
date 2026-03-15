# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in kenso, please report it responsibly.

**Do not open a public issue.** Instead, send an email to:

**fvena32@gmail.com**

Please include:

- A description of the vulnerability
- Steps to reproduce the issue
- Any relevant logs or screenshots
- Your suggested fix (if any)

## Response Timeline

- **Acknowledgment**: within 48 hours
- **Initial assessment**: within 5 business days
- **Fix release**: as soon as practical, depending on severity

## Scope

kenso runs locally and uses SQLite for storage. The primary security concerns are:

- **SQL injection** via crafted search queries or document content
- **Path traversal** via manipulated file paths in MCP tool calls
- **Denial of service** via excessively large documents or queries

## Disclosure Policy

We follow coordinated disclosure. Once a fix is released, we will:

1. Credit the reporter (unless they prefer anonymity)
2. Publish a GitHub Security Advisory
3. Release a patched version to PyPI
