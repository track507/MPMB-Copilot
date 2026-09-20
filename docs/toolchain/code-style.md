# Code style

House style for this repo. Formatting that a tool enforces is listed for reference
only - ruff, prettier, eslint and `.editorconfig` are the authority there. What
follows is the part no formatter checks.

Newer files already follow this; older ones predate it. **Do not mass-rewrite** -
apply it to code you are already touching, per the refactor-in-context rule.

## Comments

Better Comments markers, and only these three:

| Marker | Means |
| --- | --- |
| `# !` / `// !` | Critical - a correctness or security constraint that breaks if ignored |
| `# *` / `// *` | Important - a section header or a fact worth finding later |
| `# ?` / `// ?` | Context - why this is the way it is, for a reader who would otherwise change it |

**Single line only.** A marker comment that needs a paragraph belongs in a docstring
or a tracked doc.

```python
# ! Fail closed: a cookie we cannot verify is not a login
# ? Uniform 401: unknown, revoked and expired are indistinguishable to the caller
# * Sessions
```

**No trailing periods.** Comments are labels, not prose.

**One sentence per line.** Never split a sentence across two lines. If it does not
fit in 120 characters, it is two sentences or it belongs in a docstring.

```python
# ! wrong - one sentence wrapped across lines
# ! The boundary is the user, so a flat hash-keyed directory would put one
# ! account's text in a namespace shared with every other account

# ! right - each line stands alone
# ! The boundary is the user, so a flat directory would share one namespace across accounts
```

## Docstrings

Opening `"""` on its own line, summary on the next, blank line before the body:

```python
def _owned(user_id: str) -> list:
    """
    Owner predicate for every session-scoped query

    Admins deliberately do not bypass this: chat history is personal data
    That differs from uploads, where role == "admin" bypasses (services/uploads/service.py:46)
    """
    return [Session.user_id == user_id]
```

Same rules as comments: no trailing periods, one sentence per line.

A one-line docstring may stay on one line (`"""Soft-delete a session"""`), still
without a trailing period.

## Never cite an uncommitted document

`docs/superpowers/` is gitignored - specs, plans and research never reach a clone.
A comment pointing at `ROADMAP:37` or a plan file is a dead reference for everyone
but the person who wrote it.

State the reason inline instead, and cite **committed** code freely:

```python
# ! wrong - the reader cannot open this
# ! Owner-keyed because ROADMAP:37 says the boundary is the user

# ! right - the reason travels with the code
# ! Derived data inherits the security properties of its source, so the cache is owner-keyed
# ? Uploads take the opposite line and let admins through (services/uploads/service.py:46)
```

If a decision needs more explanation than a comment holds, it belongs in a tracked
doc (`README.md`, `docs/`), not in a link to an untracked one.

## ASCII only

Source files are ASCII. No unicode dashes, quotes, arrows or symbols - use `-`,
`"`, `->`. This keeps diffs and terminals predictable across Windows and Linux.

## Formatting (tool-enforced, listed for reference)

| Language | Indent | Width | Authority |
| --- | --- | --- | --- |
| Python | 4 spaces | 120 | ruff (`E`, `F`, `I`, `N`; `E501` off - the formatter owns width) |
| JS / TS / JSON | tabs, size 4 | 160 | prettier (double quotes, semicolons, trailing comma es5) |
| Markdown | 4 spaces | off | markdownlint-cli2 |

LF endings and a final newline everywhere (`.editorconfig`, `.gitattributes`).

## Python

- **Services take primitives, never `Principal`.** `app/api` imports services, so a
  service importing `app.api` is a cycle. Pass `user_id: str` and `role: str`.
- **Security-relevant parameters are keyword-only and required.** A filter with a
  default of `None` fails open when a caller forgets it; one with no default fails
  at the call site. This is why session methods take `*, user_id: str`.
- **ORM models use `Mapped[...]` / `mapped_column`**, not bare `Column`.
- **Behavioral knobs go in `settings.py`** (hot-reloadable JSON, applied next query).
  **Infrastructure goes in `config.py`** (env, read at startup). A tunable in
  `config.py` is a bug.
- Imports: stdlib, third-party, first-party (`app`), enforced by ruff isort.

## Frontend

- **No raw `fetch`, `XMLHttpRequest` or `EventSource`.** Everything goes through
  `lib/http`.
- Explicit return types on exported functions. `exactOptionalPropertyTypes` is on,
  so never pass `undefined` to an optional prop.
- `import type` in its own statement.
- `snake_case` only for property names mirroring backend JSON.
- **`Temporal`, never `Date`.** `Temporal.Now.instant()` for anything stored or
  transmitted; `plainDateTimeISO()` only for output a human reads.
- `components/ui/**` is vendored shadcn - exempt from several rules, do not restyle.

## Tests

**Never co-located with source.** `backend/tests/` and `frontend/test/` mirror their
source trees.

Backend has two distinct test styles, and using the wrong one wastes a cycle:

| Location | Style | Database |
| --- | --- | --- |
| `tests/api/` | Monkeypatch the service layer (`monkeypatch.setattr(mod.session_service, ...)`) and patch `db` with `SimpleNamespace(is_connected=True)` | **Never touches one** |
| `tests/services/db/` | Integration against a real Postgres via the `db_session_scope` fixture in the package conftest | Skips unless `TEST_DATABASE_URL` is set |

`asyncio_mode = "auto"` is set, so **async tests need no `@pytest.mark.asyncio`**.
Neither existing db test file has one.

The split is deliberate: API tests prove the *wiring* (does the principal's id reach
the service, does a miss render as 404) and run in the fast gate without a database;
service tests prove the *behavior* (does the filter actually exclude another owner).

Security fixes ship with abuse-case tests that encode the review permanently - see
`tests/api/test_auth_abuse.py`.

## Commits

commitlint enforces it: conventional type from the enum, **sentence-case subject**,
header <= 100 characters, scope warned but not blocked. Never `--no-verify`.

Bodies are bullet lists, one point per line, no trailing periods:

```text
fix(chat): Scope session history and creation to the caller

- Pass principal.user_id into _load_history, which previously loaded history for any session id a caller supplied
- Stamp the owner in _ensure_session, which had the principal available and dropped it
```

No `Co-Authored-By` trailers.
