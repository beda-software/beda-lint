"""Command-line plumbing shared by every check: file discovery, baseline and report."""

import argparse
import ast
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

NOQA = re.compile(r"#\s*noqa:\s*(?P<codes>[\w\s,]+)", re.IGNORECASE)
NOQA_CODE_SEPARATOR = re.compile(r"[\s,]+")


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    code: str
    symbol: str
    message: str

    @property
    def key(self) -> str:
        """Baseline identity: no line number, so an edit elsewhere in the file keeps it matched."""
        path = self.path.resolve()
        root = Path.cwd()
        relative = path.relative_to(root) if path.is_relative_to(root) else path
        return f"{relative}::{self.symbol}"


CheckTree = Callable[[ast.Module, Path], list[Finding]]


def run_check(check_tree: CheckTree, description: str | None, argv: Sequence[str] | None) -> int:
    args = parse_args(description, argv)
    findings = [
        finding
        for path in collect_python_files(args.paths)
        for finding in check_file(path, check_tree)
    ]
    if args.update_baseline:
        return write_baseline(args.baseline, findings)

    return report(findings, read_baseline(args.baseline) if args.baseline else set())


def parse_args(description: str | None, argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("paths", nargs="+", type=Path, help="Python files or directories")
    parser.add_argument(
        "--baseline", type=Path, help="file of known findings to skip, one `path::symbol` per line"
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="rewrite the baseline from the findings in the given paths",
    )
    args = parser.parse_args(argv)
    if args.update_baseline and not args.baseline:
        parser.error("--update-baseline needs --baseline")

    return args


def collect_python_files(paths: Iterable[Path]) -> list[Path]:
    files = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
        elif path.suffix == ".py":
            files.append(path)
    return files


def check_file(path: Path, check_tree: CheckTree) -> list[Finding]:
    source = path.read_text()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as error:
        return [Finding(path, error.lineno or 1, "PARSE", "", str(error))]

    lines = source.splitlines()
    return [finding for finding in check_tree(tree, path) if not _is_suppressed(finding, lines)]


def _is_suppressed(finding: Finding, lines: list[str]) -> bool:
    """A `# noqa: CODE` comment on the finding's line, as ruff reads it."""
    match = NOQA.search(lines[finding.line - 1]) if finding.line <= len(lines) else None
    return match is not None and finding.code in NOQA_CODE_SEPARATOR.split(match["codes"])


def write_baseline(baseline: Path, findings: Iterable[Finding]) -> int:
    keys = sorted({finding.key for finding in findings})
    baseline.write_text("".join(f"{key}\n" for key in keys))
    print(f"wrote {len(keys)} baselined findings to {baseline}")
    return 0


def read_baseline(baseline: Path) -> set[str]:
    if not baseline.exists():
        return set()

    return {line.strip() for line in baseline.read_text().splitlines() if line.strip()}


def report(findings: Iterable[Finding], baseline: set[str]) -> int:
    unbaselined = [finding for finding in findings if finding.key not in baseline]
    for finding in sorted(unbaselined, key=lambda f: (f.path, f.line)):
        print(f"{finding.path}:{finding.line}: {finding.code} {finding.message}")
    return 1 if unbaselined else 0
