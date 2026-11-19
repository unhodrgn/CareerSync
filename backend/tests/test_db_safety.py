"""The destructive test fixture touches only a disposable local PostgreSQL (M4 S3c, D65): `db_safety.py`.

`conftest.py`'s `db` fixture drops every application table before and after each test. Nothing here opens a database: the guard works on
the URL, and the tests below prove it by replacing `create_engine` with a function that fails if it is called."""
import ast
from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool

from . import db_safety
from .db_safety import UnsafeTestDatabase, check_disposable_postgres, make_test_engine

PASSWORD = "TOPSECRET-pw-9f3a"

SAFE = [
    f"postgresql+psycopg://postgres:{PASSWORD}@127.0.0.1:55432/careersync_pgtest",
    f"postgresql://postgres:{PASSWORD}@localhost/x_pgtest",
    f"postgresql+psycopg://postgres:{PASSWORD}@[::1]:5433/a_pgtest",
    f"postgresql+psycopg://postgres:{PASSWORD}@127.0.0.2/a_pgtest",
    f"postgresql+psycopg://postgres:{PASSWORD}@127.0.0.1/a_pgtest?connect_timeout=5&sslmode=disable&application_name=tests",
]

UNSAFE = {
    "a remote host name": f"postgresql+psycopg://postgres:{PASSWORD}@db.example.com/careersync_pgtest",
    "a private network address": f"postgresql+psycopg://postgres:{PASSWORD}@10.0.0.5/careersync_pgtest",
    "a host that only starts like the loopback": f"postgresql+psycopg://postgres:{PASSWORD}@127.0.0.1.evil.example.com/careersync_pgtest",
    "no host (a unix socket)": f"postgresql+psycopg://postgres:{PASSWORD}@/careersync_pgtest?host=/var/run/postgresql",
    "two hosts": f"postgresql+psycopg://postgres:{PASSWORD}@127.0.0.1,10.0.0.5/careersync_pgtest",
    "a database name that does not end in _pgtest": f"postgresql+psycopg://postgres:{PASSWORD}@127.0.0.1/careersync_db",
    "the old test name": f"postgresql+psycopg://postgres:{PASSWORD}@127.0.0.1/careersync_test",
    "a name that only contains the suffix": f"postgresql+psycopg://postgres:{PASSWORD}@127.0.0.1/x_pgtest_prod",
    "the suffix alone": f"postgresql+psycopg://postgres:{PASSWORD}@127.0.0.1/_pgtest",
    "no database name": f"postgresql+psycopg://postgres:{PASSWORD}@127.0.0.1",
    "another dialect": f"mysql+pymysql://root:{PASSWORD}@127.0.0.1/careersync_pgtest",
    "a host in the query": f"postgresql+psycopg://postgres:{PASSWORD}@127.0.0.1/a_pgtest?host=prod.example.com",
    "a host address in the query": f"postgresql+psycopg://postgres:{PASSWORD}@127.0.0.1/a_pgtest?hostaddr=10.0.0.5",
    "a service in the query": f"postgresql+psycopg://postgres:{PASSWORD}@127.0.0.1/a_pgtest?service=prod",
    "options in the query": f"postgresql+psycopg://postgres:{PASSWORD}@127.0.0.1/a_pgtest?options=-csearch_path%3Dprod",
    "something that is not a URL": f"not a url {PASSWORD}",
    "an empty string": "",
}


@pytest.fixture
def no_engine(monkeypatch):
    """`create_engine` fails if called: a refused URL must not get as far as an engine, let alone a connection."""
    calls = []

    def create_engine(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("an engine was created")

    monkeypatch.setattr(db_safety, "create_engine", create_engine)
    return calls


@pytest.mark.parametrize("url", SAFE)
def test_a_disposable_local_postgresql_is_accepted(url):
    check_disposable_postgres(url)


@pytest.mark.parametrize("url", UNSAFE.values(), ids=UNSAFE.keys())
def test_everything_else_is_refused_before_an_engine_exists(url, no_engine):
    with pytest.raises(UnsafeTestDatabase) as refused:
        make_test_engine(url)
    assert no_engine == []  # create_engine was never called


@pytest.mark.parametrize("url", UNSAFE.values(), ids=UNSAFE.keys())
def test_a_refusal_never_repeats_the_url_the_host_the_name_or_the_password(url, no_engine):
    with pytest.raises(UnsafeTestDatabase) as refused:
        check_disposable_postgres(url)
    error = refused.value
    shown = " ".join([str(error), repr(error), *map(str, error.args)])
    for part in (PASSWORD, "db.example.com", "10.0.0.5", "prod", "careersync", "postgres:", "evil", "@"):
        assert part not in shown, part
    assert error.__cause__ is None and error.__context__ is None  # nothing that quotes the URL is attached
    assert "no connection was made" in str(error)


def test_a_safe_url_gets_an_engine_and_still_no_connection(monkeypatch):
    made = []
    monkeypatch.setattr(db_safety, "create_engine", lambda url, **kwargs: made.append((url, kwargs)) or "engine")
    url = SAFE[0]
    assert make_test_engine(url) == "engine" and made == [(url, {})]  # created, not connected: the stub never connects either


def test_sqlite_behaves_as_before(no_engine, monkeypatch):
    """SQLite is not checked and keeps its options: one in-memory connection, shared by every thread and session."""
    seen = []
    monkeypatch.setattr(db_safety, "create_engine", lambda url, **kwargs: seen.append((url, kwargs)) or "engine")
    assert make_test_engine("sqlite://") == "engine"
    assert seen == [("sqlite://", {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool})]


def test_the_fixture_builds_its_engine_through_the_guard_and_nowhere_else():
    tree = ast.parse((Path(__file__).parent / "conftest.py").read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    names = {getattr(c.func, "id", getattr(c.func, "attr", "")) for c in calls}
    assert "make_test_engine" in names and "create_engine" not in names and "drop_all" in names
    other = [
        p.name
        for p in Path(__file__).parent.glob("*.py")
        if p.name not in {"db_safety.py", "test_db_safety.py"} and "drop_all" in p.read_text(encoding="utf-8") and p.name != "conftest.py"
    ]
    assert other == []  # no other file drops tables
