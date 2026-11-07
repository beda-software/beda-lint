import ast
import textwrap
from pathlib import Path

import pytest

from beda_lint.call_tree_order import check_call_tree_order, main


def test_check_call_tree_order__flags_a_helper_defined_above_its_only_caller() -> None:
    tree = ast.parse("def _helper():\n    return 1\n\n\ndef root():\n    return _helper()\n")
    findings = check_call_tree_order(tree, Path("f.py"))
    assert [(f.code, f.line) for f in findings] == [("BCT001", 1)]


def test_check_call_tree_order__accepts_a_helper_defined_below_its_caller() -> None:
    tree = ast.parse("def root():\n    return _helper()\n\n\ndef _helper():\n    return 1\n")
    assert check_call_tree_order(tree, Path("f.py")) == []


def test_check_call_tree_order__flags_a_helper_above_its_last_caller() -> None:
    tree = ast.parse(
        "def first_caller():\n    return _helper()\n\n\n"
        "def _helper():\n    return 1\n\n\n"
        "def second_caller():\n    return _helper()\n"
    )
    findings = check_call_tree_order(tree, Path("f.py"))
    assert [(f.symbol, f.line) for f in findings] == [("_helper", 5)]


def test_check_call_tree_order__ignores_calls_within_a_cycle() -> None:
    tree = ast.parse(
        "def ping(n):\n    return pong(n - 1)\n\n\n"
        "def pong(n):\n    return ping(n - 1) if n else 0\n"
    )
    assert check_call_tree_order(tree, Path("f.py")) == []


def test_check_call_tree_order__flags_a_cycle_above_an_outside_caller() -> None:
    tree = ast.parse(
        "def ping(n):\n    return pong(n - 1)\n\n\n"
        "def pong(n):\n    return ping(n - 1) if n else 0\n\n\n"
        "def root():\n    return ping(3)\n"
    )
    findings = check_call_tree_order(tree, Path("f.py"))
    assert [f.symbol for f in findings] == ["ping"]


def test_check_call_tree_order__places_overloads_at_the_first_stub() -> None:
    source = textwrap.dedent(
        """
        @overload
        def parse(value: int) -> int: ...
        @overload
        def parse(value: str) -> str: ...
        def parse(value):
            return _normalize(value)

        def _normalize(value):
            return value

        def root():
            return parse(1)
        """
    )
    findings = check_call_tree_order(ast.parse(source), Path("f.py"))
    assert [(f.symbol, f.line) for f in findings] == [("parse", 3)]


def test_check_call_tree_order__ignores_a_self_recursive_call() -> None:
    tree = ast.parse("def countdown(n):\n    return countdown(n - 1) if n else 0\n")
    assert check_call_tree_order(tree, Path("f.py")) == []


def test_check_call_tree_order__ignores_calls_to_names_outside_the_module() -> None:
    tree = ast.parse("def root():\n    return len([1, 2, 3])\n")
    assert check_call_tree_order(tree, Path("f.py")) == []


def test_check_call_tree_order__flags_a_method_above_its_last_caller() -> None:
    source = textwrap.dedent(
        """
        class Batch:
            def unstage(self, ref):
                self._unstage_all({ref})

            def _unstage_all(self, refs):
                pass

            def unstage_unchanged(self):
                self._unstage_all(set())
        """
    )
    findings = check_call_tree_order(ast.parse(source), Path("f.py"))
    assert [f.symbol for f in findings] == ["Batch._unstage_all"]


def test_check_call_tree_order__ignores_self_calls_of_a_class_nested_in_a_method() -> None:
    source = textwrap.dedent(
        """
        class Outer:
            def _h(self):
                pass

            def build(self):
                class Inner:
                    def go(self):
                        self._h()
        """
    )
    assert check_call_tree_order(ast.parse(source), Path("f.py")) == []


def test_check_call_tree_order__names_a_nested_class_method_with_its_outer_class() -> None:
    source = textwrap.dedent(
        """
        class Outer:
            class Inner:
                def _h(self):
                    pass

                def run(self):
                    self._h()
        """
    )
    findings = check_call_tree_order(ast.parse(source), Path("f.py"))
    assert [f.symbol for f in findings] == ["Outer.Inner._h"]
    assert "`Outer.Inner.run`" in findings[0].message


def test_check_call_tree_order__counts_a_method_calling_a_module_function() -> None:
    source = textwrap.dedent(
        """
        def _helper():
            pass

        class A:
            def m(self):
                _helper()
        """
    )
    findings = check_call_tree_order(ast.parse(source), Path("f.py"))
    assert [f.symbol for f in findings] == ["_helper"]
    assert "`A.m`" in findings[0].message


def test_check_call_tree_order__counts_a_property_setter_as_a_caller() -> None:
    source = textwrap.dedent(
        """
        class A:
            @property
            def x(self):
                return self._x

            def _validate(self, value):
                pass

            @x.setter
            def x(self, value):
                self._validate(value)
        """
    )
    findings = check_call_tree_order(ast.parse(source), Path("f.py"))
    assert [f.symbol for f in findings] == ["A._validate"]


def test_check_call_tree_order__counts_a_helper_passed_by_reference() -> None:
    source = textwrap.dedent(
        """
        def _key(item):
            return item

        def root(items):
            return sorted(items, key=_key)
        """
    )
    findings = check_call_tree_order(ast.parse(source), Path("f.py"))
    assert [f.symbol for f in findings] == ["_key"]


def test_check_call_tree_order__ignores_a_decorator_defined_above_its_use() -> None:
    source = textwrap.dedent(
        """
        def deco(func):
            return func

        @deco
        def root():
            pass
        """
    )
    assert check_call_tree_order(ast.parse(source), Path("f.py")) == []


def test_check_call_tree_order__handles_a_call_chain_deeper_than_the_recursion_limit() -> None:
    depth = 1500
    source = (
        "\n".join(f"def f{i}():\n    f{i + 1}()\n" for i in range(depth))
        + f"\ndef f{depth}():\n    pass\n"
    )
    assert check_call_tree_order(ast.parse(source), Path("f.py")) == []


def test_check_call_tree_order__accepts_a_method_below_all_callers() -> None:
    source = textwrap.dedent(
        """
        class Batch:
            def unstage(self, ref):
                self._unstage_all({ref})

            def unstage_unchanged(self):
                Batch._unstage_all(set())

            def _unstage_all(self, refs):
                pass
        """
    )
    assert check_call_tree_order(ast.parse(source), Path("f.py")) == []


def test_main__exits_non_zero_and_prints_findings_when_a_file_has_violations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "sample.py"
    source.write_text("def _helper():\n    return 1\n\n\ndef root():\n    return _helper()\n")
    exit_code = main([str(source)])
    assert exit_code == 1
    assert f"{source}:1: BCT001" in capsys.readouterr().out


def test_main__accepts_a_baselined_finding(tmp_path: Path) -> None:
    source = tmp_path / "sample.py"
    source.write_text("def _helper():\n    return 1\n\n\ndef root():\n    return _helper()\n")
    baseline = tmp_path / "baseline.txt"
    assert main([str(source), "--baseline", str(baseline), "--update-baseline"]) == 0
    assert baseline.read_text() == f"{source}::_helper\n"
    assert main([str(source), "--baseline", str(baseline)]) == 0


def test_main__flags_a_new_violation_in_a_baselined_file(tmp_path: Path) -> None:
    source = tmp_path / "sample.py"
    source.write_text("def _helper():\n    return 1\n\n\ndef root():\n    return _helper()\n")
    baseline = tmp_path / "baseline.txt"
    main([str(source), "--baseline", str(baseline), "--update-baseline"])

    source.write_text(
        "def _other():\n    return 2\n\n\ndef root():\n    return _other() + _helper()\n\n\n"
        "def _helper():\n    return 1\n"
    )
    assert main([str(source), "--baseline", str(baseline)]) == 1


def test_main__writes_baseline_keys_relative_to_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text(
        "def _helper():\n    return 1\n\n\ndef root():\n    return _helper()\n"
    )
    monkeypatch.chdir(tmp_path)
    main(["pkg", "--baseline", "baseline.txt", "--update-baseline"])
    assert (tmp_path / "baseline.txt").read_text() == "pkg/mod.py::_helper\n"


def test_main__skips_a_finding_with_a_noqa_comment_for_its_code(tmp_path: Path) -> None:
    source = tmp_path / "sample.py"
    source.write_text(
        "def _helper():  # noqa: BCT001\n    return 1\n\n\ndef root():\n    return _helper()\n"
    )
    assert main([str(source)]) == 0


def test_main__rejects_update_baseline_without_a_baseline_file(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main([str(tmp_path), "--update-baseline"])


def test_main__exits_zero_when_no_files_have_violations(tmp_path: Path) -> None:
    source = tmp_path / "sample.py"
    source.write_text("def root():\n    return _helper()\n\n\ndef _helper():\n    return 1\n")
    assert main([str(source)]) == 0
