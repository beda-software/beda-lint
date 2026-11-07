# beda-lint

Custom lint checks for Beda Software projects — the conventions ruff and mypy don't cover. Each check is a
standalone command and a [pre-commit](https://pre-commit.com) hook; pick the ones a project wants. Requires
Python 3.11+ (the checks read their config with `tomllib`); the checked code can target any Python 3 version.

| Hook / command | Language | What it checks | Style guide |
| --- | --- | --- | --- |
| `call-tree-order` | Python | Each function sits below its last caller (`BCT001`) | [good](examples/call_tree_order/good.py) / [bad](examples/call_tree_order/bad.py) |
| `function-verb-names` | Python | Function names start with a verb (`BVN001`); bool functions read as predicates (`BVN002`) | [good](examples/function_verb_names/good.py) / [bad](examples/function_verb_names/bad.py) |

Each rule's style guide is a pair of files under [`examples/`](examples): `good.py` passes, `bad.py` shows every
finding with the fix in a comment. Tests run the checks on both, so the examples always match what the checks do.

## call-tree-order

A module should read top-down like a call tree: the public entry point first, then its helpers in the order they're
first used, each helper's own helpers below it. The check flags any function or method defined above a function that
calls it:

```
app/orders.py:12: BCT001 `_total` is defined above its caller `build_invoice` (line 30); move helpers below their last caller
```

See the style guide: [good](examples/call_tree_order/good.py) / [bad](examples/call_tree_order/bad.py).

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
app/billing.py:12: BVN001 `invoice_total` does not start with a verb; name it for what it does (`fetch_`, `build_`, ...) or add `invoice` to extra-verbs
app/billing.py:30: BVN002 `check_paid` returns bool, so name it as a statement about its argument: `is_`, `has_`, `should_`, `can_`, or a third-person verb such as `matches_`
```

See the style guide: [good](examples/function_verb_names/good.py) / [bad](examples/function_verb_names/bad.py),
each bad name with its fix.

How a name is read:

- The first word counts, after leading underscores, split on `_` or camelCase: `_fetch_x` → `fetch`, `setUp` → `set`,
  `Total` → `total`.
- **BVN001**: the first word must be in the verb list — the built-in [`verbs.txt`](beda_lint/verbs.txt) plus
  `extra-verbs` — or a predicate prefix (`is_`, `has_`, ...). A third-person form (`matches_`, `records`) passes only
  on a bool function, so `records() -> list` is flagged.
- **BVN002**: a function returns bool when it is annotated `-> bool`, `TypeGuard[...]` or `TypeIs[...]`, or — without
  an annotation — when every `return` gives `True`/`False`, a comparison, `not …`, `and`/`or` of those, a call such
  as `isinstance`, `any`, `all`, `bool`, or a call to a predicate-named function (`self._is_valid()`). Its first word
  must be `is`, `are`, `has`, `have`, `can`, `should`, `does`, an `extra-predicate-prefixes` entry, or the
  third-person form of a listed verb (`matches`, `applies`, `belongs`).
- Exempt: dunder methods, `main`, `@property` and its setter/getter/deleter, `@cached_property`, `@overload` stubs,
  `@pytest.fixture` functions, names matching `*_op` (Aidbox operations), and aiohttp lifecycle hooks registered in
  the same module — `app.cleanup_ctx.append(db)`, `app.on_startup += [warmup]` and the other app signals. A hook
  registered from another module is not seen; list it in `ignore-patterns` or add `# noqa: BVN001`. `test_*` passes
  because `test` is a verb.

### Configuration

Optional, in the `pyproject.toml` of the folder the check runs from:

```toml
[tool.beda-lint.function-verb-names]
# Verbs specific to the project, added to the built-in list.
extra-verbs = ["rehydrate", "debit"]
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
def dt(time_str: str) -> datetime:  # noqa: BVN001 — short on purpose, used in test tables
```

Several codes can share one comment with ruff's: `# noqa: E501, BVN001`. With ruff's `RUF100` (unused `noqa`)
enabled, tell ruff these codes are external so it keeps them:

```toml
[tool.ruff.lint]
external = ["BVN", "BCT"]
```

## Use with flake8 (errors in the editor)

The checks are also flake8 plugins, so an editor running flake8 underlines findings as you type. Baselines are not
supported there: use flake8's `per-file-ignores` for legacy files, and keep the commands above for pre-commit and CI.
flake8 also honours a bare `# noqa` without codes, which the commands ignore.

In VS Code, install the [Flake8 extension](https://marketplace.visualstudio.com/items?itemName=ms-python.flake8) and
beda-lint into the project environment (`uv add --dev git+https://github.com/beda-software/beda-lint`), then limit
flake8 to these codes so it does not duplicate ruff:

```json
// .vscode/settings.json
{ "flake8.args": ["--select=BCT,BVN"] }
```

## Development

```bash
uv sync
uv run pytest
uv run ruff format --check . && uv run ruff check . && uv run mypy
```

A new check goes in `beda_lint/<check>.py` with a `main()`, a `[project.scripts]` entry in `pyproject.toml`, a
plugin class in `beda_lint/flake8_plugin.py` with its `flake8.extension` entry point, a hook
in `.pre-commit-hooks.yaml`, tests in `tests/`, a style guide in `examples/<check>/good.py` and `bad.py` (registered
in `tests/test_examples.py`, which fails until every script in `[project.scripts]` has a folder), and a row in the
table above.
