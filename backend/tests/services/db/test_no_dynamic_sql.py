import re
from pathlib import Path

APP = Path(__file__).resolve().parents[3] / "app"
_DYNAMIC_SQL = re.compile(r"\btext\(\s*(?:[rR]?[fF]|[fF][rR])[\"']|\bexec_driver_sql\(|\.execute\(\s*[rR]?[fF][\"']")


def test_sql_text_is_static():
    offenders: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _DYNAMIC_SQL.search(line):
                offenders.append(f"{path.relative_to(APP).as_posix()}:{number}")
    assert offenders == [], "build SQL from SQLAlchemy expressions with bound parameters: " + ", ".join(offenders)


def test_the_guard_can_fail():
    assert _DYNAMIC_SQL.search('        await conn.execute(text(f"SELECT {name}"))')
    assert _DYNAMIC_SQL.search("    conn.exec_driver_sql(query)")
    assert _DYNAMIC_SQL.search('    await s.execute(f"DELETE FROM {table}")')
    assert not _DYNAMIC_SQL.search('                await conn.execute(text("SELECT 1"))')
