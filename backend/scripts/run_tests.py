"""轻量测试 runner（无 pytest 依赖）：发现并运行 tests/ 下所有 test_* 函数。"""
from __future__ import annotations

import importlib
import sys
import traceback
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import tests  # noqa: E402  (确保 tests 包可导入)


def main() -> int:
    test_files = sorted(Path(BACKEND / "tests").glob("test_*.py"))
    passed = failed = 0
    failures: list[tuple[str, str]] = []
    for f in test_files:
        mod = importlib.import_module(f"tests.{f.stem}")
        fns = [(n, getattr(mod, n)) for n in dir(mod) if n.startswith("test_")
               and callable(getattr(mod, n))]
        for name, fn in fns:
            try:
                fn()
                passed += 1
                print(f"  PASS  {f.stem}.{name}")
            except Exception:
                failed += 1
                failures.append((f"{f.stem}.{name}", traceback.format_exc()))
                print(f"  FAIL  {f.stem}.{name}")
    print(f"\n{passed} passed, {failed} failed, {len(test_files)} files")
    for name, tb in failures:
        print(f"\n===== {name} =====\n{tb}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
