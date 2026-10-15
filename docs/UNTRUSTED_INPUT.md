# Untrusted input

Untrusted input is anything a user, an upload, retrieved source or a model produced.
None of it is trusted as code, a query, a path or an instruction.
Each place where such text becomes an action is a sink, and each sink has one named defense at one choke point, pinned by a test.
The defense sits at the sink because the same bytes are harmless in one place and dangerous in another.
Request inspection at the edge, such as a web application firewall, is defense in depth and never the defense.

## Sinks

| Sink | Untrusted input | Defense | Choke point | Pinned by |
| --- | --- | --- | --- | --- |
| SQL | Chat text, filenames, identifiers | SQLAlchemy expressions with bound parameters; `text()` holds constants only | `backend/app/services/db/` | `backend/tests/services/db/test_no_dynamic_sql.py` |
| Source and upload paths | Model-chosen paths and globs | One resolver: root allowlist, `..` and absolute-path rejection, extension allowlist, size cap, denied subdirectories, symlink containment | `backend/app/core/tools/source_paths.py:189` (`resolve_safe_path`), `:154` (`iter_searchable_files`) | `backend/tests/core/tools/test_source_paths.py`, `backend/tests/core/tools/test_source_paths_tenant.py` |
| Storage keys | Tenant, user, session and file identifiers | Keys are built only here, every segment matches `[A-Za-z0-9_-]+`, and no segment is ever a name | `backend/app/core/storage_keys.py` | `backend/tests/core/test_storage_keys.py` |
| Upload filenames | User-chosen names | Sanitized for display; never used as a storage path, because the stored key is the file id | `backend/app/services/uploads/sanitize.py:18` (`sanitize_filename`) | `backend/tests/services/uploads/test_sanitize.py` |
| Regex engine | Model-chosen grep patterns | Linear-time RE2; a pattern RE2 rejects runs on the `regex` package with a timeout and the global interpreter lock released | `backend/app/core/tools/line_patterns.py` (`compile_line_pattern`) | `backend/tests/core/tools/test_mpmb_tools.py` |
| Tool results | File text, extracted text, search hits | Byte cap on every result before it reaches the model | `backend/app/core/tools/budget.py` (`cap_result`) | `backend/tests/core/tools/test_budget.py` |
| PDF parser | Uploaded PDF bytes | Page, byte and time bounds on extraction; a pixel budget before any page is rendered for OCR; one lock around PDFium | `backend/app/services/documents/ops/pdf.py` | `backend/tests/services/documents/test_pdf_limits.py` |
| CSV parser | Uploaded CSV bytes | Bounded summary fields and a capped sniffer sample | `backend/app/services/documents/ops/csv.py` | `backend/tests/services/documents/test_csv_adapter.py` |
| Request bodies | Any HTTP body, before authentication | Size limit enforced before the body is read or parsed | `backend/app/api/body_limit.py` (`BodyLimitMiddleware`) | `backend/tests/api/test_body_limit.py` |
| Client IP | Forwarding headers | A forwarding header is read only when the socket peer is a configured trusted proxy | `backend/app/api/client_ip.py` (`TrustedProxyMiddleware`) | `backend/tests/api/test_client_ip.py` |
| Chat markdown in the browser | Model output and pasted text | Raw HTML is dropped and unsafe URL schemes are blanked by `react-markdown` defaults; `rehype-raw` and a permissive `urlTransform` are never added | `frontend/src/components/chat/message-bubble.tsx:98` | `frontend/test/components/chat/message-bubble.test.tsx` |
| Images in chat markdown | Model output, which an injected instruction can steer | Never rendered as an `<img>`: shown as inert alt text plus the URL; the page policy limits `img-src` to `'self' data: blob:` | `frontend/src/components/chat/message-bubble.tsx:98`, `frontend/index.html:14` | `frontend/test/components/chat/message-bubble.test.tsx` |
| Downloads | Stored uploads served back | `Content-Disposition: attachment`, `application/octet-stream`, `X-Content-Type-Options: nosniff` | `backend/app/api/uploads.py:136` | `backend/tests/api/test_uploads.py` (`test_download_sets_attachment_and_nosniff`) |
| Script validator | User and model scripts | Fixed argv, the script on stdin, parsed by the ESLint `Linter` and never executed, wall-clock timeout | `backend/app/core/tools/validator_client.py:34` (`_spawn`) | `backend/tests/core/tools/test_validator_client.py` |
| Model prompt | Uploads, retrieved source, tool output | Labeled regions; the system prompt states uploads are data, never instructions; every tool is read-only; write tools require human approval | `backend/app/core/prompts.py:169`, `backend/app/services/uploads/manifest.py:56` | `backend/tests/core/test_prompts.py` (`test_addendum_names_uploaded_files_section`) |

## Rules for new code

- A new sink ships with a row here, a single choke point and a test that fails when the defense is removed
- SQL is built from SQLAlchemy expressions; `text()`, `exec_driver_sql` and `execute` never receive a formatted string
- Every read of source or uploaded files goes through `resolve_safe_path`
- Every storage path comes from `backend/app/core/storage_keys.py`
- A model-supplied pattern never reaches the standard library `re` engine
- Rendered markdown never enables raw HTML or a permissive URL transform, and never renders a remote image
- Text from uploads, retrieved source and tool results reaches the model inside a labeled region and is described there as data
- A new route that accepts code or documents in its body joins the WAF exemptions below

## WAF exemptions

No web application firewall is deployed by default.
When one is enabled, these request bodies skip OWASP Core Rule Set body inspection:

| Route | Body | Why |
| --- | --- | --- |
| `POST /api/chat`, `POST /api/chat/stream` | JSON whose `message` holds pasted AcroJS | Users paste JavaScript as normal use, and body rules for cross-site scripting and code injection would block it |
| `POST /api/uploads` | Multipart `.js`, `.pdf`, `.csv` | Script and document uploads are the product's input, and their contents match the same rules |

Header, URI, rate-limit and bot rules still apply to these routes.
The exemption is safe only because every sink above defends these bodies.
Removing a defense from the table requires removing the exemption first.

## Reporting

Known weaknesses that are not fixed yet are tracked privately and are not listed here.
Report a weakness through `.github/SECURITY.md`.
