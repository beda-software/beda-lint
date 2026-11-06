# beda-lint

Custom lint checks for Beda Software projects — the conventions ruff and mypy don't cover. Each check is a
standalone command and a [pre-commit](https://pre-commit.com) hook; pick the ones a project wants.

| Hook / command | Language | What it checks |
| --- | --- | --- |
| `call-tree-order` | Python | Each function sits below its last caller (`ORDER001`) |
| `function-verb-names` | Python | Function names start with a verb (`NAME001`); bool functions read as predicates (`NAME002`) |

## call-tree-order

A module should read top-down like a call tree: the public entry point first, then its helpers in the order they're
first used, each helper's own helpers below it. The check flags any function or method defined above a function that
calls it:

```
app/orders.py:12: ORDER001 `_total` is defined above its caller `build_invoice` (line 30); move helpers below their last caller
```

What counts:

- A call or a reference to the function (`sorted(items, key=_key)`) inside another function's body.
- Methods are checked within their class, through `self.x`, `cls.x` and `ClassName.x`.
- Functions that call each other in a cycle are not ordered among themselves.
- Decorators and default values run at definition time, so they are not counted as uses.
- `@property` getters are read as attributes and never need to sit below their users.

### Use with pre-commit

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/beda-software/beda-lint
    rev: main
    hooks:
      - id: call-tree-order
        # optional, for an existing codebase:
        args: [--baseline, lint/order-baseline.txt]
```

While beda-lint is in active development there are no release tags, so pin `main`. pre-commit warns about a mutable
rev and caches the first checkout; run `pre-commit clean` to pick up newer checks.

### Run directly

No install needed with [uv](https://docs.astral.sh/uv/):

```bash
uvx --from git+https://github.com/beda-software/beda-lint call-tree-order src tests
```

Or add it as a dev dependency (`uv add --dev git+https://github.com/beda-software/beda-lint`, or the poetry
equivalent) and call `call-tree-order <paths>` from a Makefile or CI.

### Adopting it in a legacy project

A legacy codebase usually has hundreds of violations. Rather than reorder everything at once, record the existing ones
in a baseline file: the check then skips them and fails only on new violations, and old modules get fixed as they're
touched.

1. **Create the baseline** from the folder you will always run the check from (usually the project root), over every
   path the check will cover:

   ```bash
   uvx --from git+https://github.com/beda-software/beda-lint \
     call-tree-order src tests --baseline lint/order-baseline.txt --update-baseline
   ```

   It writes one `path::symbol` line per existing violation, sorted, for example:

   ```
   src/billing/invoices.py::_total
   src/billing/invoices.py::InvoiceBuilder._add_line
   ```

2. **Commit the baseline** next to the code.

3. **Wire the check in** with the same `--baseline` path — the pre-commit hook above, or a Makefile/CI step:

   ```bash
   call-tree-order src tests --baseline lint/order-baseline.txt
   ```

4. **Shrink it over time.** After moving some helpers below their callers, rerun step 1 and commit the shorter file.
   Always regenerate over the whole tree, never from pre-commit: pre-commit passes only the changed files, so a
   baseline written from them would drop every other entry.

How entries match:

- No line numbers: a baselined function stays skipped when code above it changes, or when it moves within its file.
- A new violation in a baselined file still fails, and so does a baselined function once it is renamed or its file
  moves.
- Paths are relative to the working directory, so create and check the baseline from the same folder.

## function-verb-names

A function does something, so its name starts with what it does: `fetch_patient`, `_build_payload`, `sync`. A
function returning `bool` answers a question about its argument, so its name reads as a statement: `is_closed`,
`has_slots`, `should_retry`, `matches_requirement`. An imperative name on a bool function (`record_satisfier() -> bool`)
promises an action it does not take.

```
app/billing.py:12: NAME001 `invoice_total` does not start with a verb; name it for what it does (`fetch_`, `build_`, ...) or add `invoice` to extra-verbs
app/billing.py:30: NAME002 `check_paid` returns bool, so name it as a statement about its argument: `is_`, `has_`, `should_`, `can_`, or a third-person verb such as `matches_`
```

How a name is read:

- The first word counts, after leading underscores, split on `_` or camelCase: `_fetch_x` → `fetch`, `setUp` → `set`.
- **NAME001**: the first word must be in the verb list — the built-in [`verbs.txt`](beda_lint/verbs.txt) plus
  `extra-verbs`. A predicate-style first word (`is_`, `matches_`) also passes.
- **NAME002**: a function returns bool when it is annotated `-> bool`, `TypeGuard[...]` or `TypeIs[...]`, or — without
  an annotation — when every `return` gives `True`/`False`, a comparison, `not …`, `and`/`or` of those, or a call such
  as `isinstance`, `any`, `all`, `bool`. Its first word must be `is`, `are`, `has`, `have`, `can`, `should`, an
  `extra-predicate-prefixes` entry, or the third-person form of a listed verb (`matches`, `applies`, `belongs`).
- Exempt: dunder methods, `main`, `@property` and its setter/getter/deleter, `@cached_property`, `@overload` stubs,
  `@pytest.fixture` functions, names matching `*_op` (Aidbox operations), and aiohttp lifecycle hooks the same module
  registers — `app.cleanup_ctx.append(db)`, `app.on_startup.append(...)` and the other app signals. `test_*` passes
  because `test` is a verb.

### Configuration

Optional, in the `pyproject.toml` of the folder the check runs from:

```toml
[tool.beda-lint.function-verb-names]
# Verbs specific to the project, added to the built-in list.
extra-verbs = ["reconcile", "repull"]
# Extra bool-name prefixes, besides is/are/has/have/can/should and third-person verbs.
extra-predicate-prefixes = ["needs"]
# Decorated functions named by framework convention.
ignore-decorators = ["sdk.operation", "sdk.subscription"]
# Shell-style globs over the full function name.
ignore-patterns = ["m_*", "action_*", "*_op", "*_handler"]
```

An unknown key or a non-list value stops the run with an error, so a typo never silently disables a setting. A verb
missing from the built-in list that most projects would use belongs in `verbs.txt` — open a PR.

### Use

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/beda-software/beda-lint
    rev: main
    hooks:
      - id: function-verb-names
        args: [--baseline, lint/names-baseline.txt]
```

```bash
uvx --from git+https://github.com/beda-software/beda-lint function-verb-names src tests
```

The baseline works as for `call-tree-order`: entries are `path::Class.function`, so see
[Adopting it in a legacy project](#adopting-it-in-a-legacy-project) — use a separate baseline file per check.

## Suppressing one finding

Every check honours `# noqa: CODE` on the line it reports — the `def` line, not a decorator line:

```python
def dt(time_str: str) -> datetime:  # noqa: NAME001 — short on purpose, used in test tables
```

Several codes can share one comment with ruff's: `# noqa: E501, NAME001`. With ruff's `RUF100` (unused `noqa`)
enabled, tell ruff these codes are external so it keeps them:

```toml
[tool.ruff.lint]
external = ["NAME", "ORDER"]
```

## Development

```bash
uv sync
uv run pytest
uv run ruff format --check . && uv run ruff check . && uv run mypy
```

A new check goes in `beda_lint/<check>.py` with a `main()`, a `[project.scripts]` entry in `pyproject.toml`, a hook
in `.pre-commit-hooks.yaml`, tests in `tests/`, and a row in the table above.
