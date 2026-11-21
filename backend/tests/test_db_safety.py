"""The destructive test fixture touches only a database that is meant to be wiped (M4 S3c, D65; approved-database mode, M4 QA): `db_safety.py`.

`conftest.py`'s `db` fixture drops every application table before and after each test. Nothing here opens a database: the guard works on
the URL and on the variables the person typed, and the tests below prove it by replacing `create_engine` with a function that fails if it is
called, and `verify_identity` is shown a fake engine that records what it is asked.

Every test is hermetic: an autouse fixture clears the variables the guard reads, and the new tests pass their own `environ`, so a real
`TEST_DATABASE_*` or `PG*` variable in the terminal of whoever runs the suite (they will be set, on purpose, for the PostgreSQL QA) cannot make
a test pass or fail."""
import ast
import contextlib
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import StaticPool

from . import db_safety
from .db_safety import (
    CONFIRM_VAR,
    EXPECTED_NAME_VAR,
    REDIRECTING_ENV,
    Target,
    UnsafeTestDatabase,
    check_disposable_postgres,
    main,
    make_test_engine,
    resolve_target,
    verify_identity,
)

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

GUARDED = ("TEST_DATABASE_URL", EXPECTED_NAME_VAR, CONFIRM_VAR, "DATABASE_URL", "CAREERSYNC_DOTENV", *REDIRECTING_ENV)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """The guard reads os.environ when no `environ` is passed: clear what it reads, for every test in this file."""
    for name in GUARDED:
        monkeypatch.delenv(name, raising=False)


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


# ═══ M4 QA: the approved database, SQLite in memory only, the libpq environment, the identity check, the preflight command ═══

APPROVED_NAME = "careersync_db"
CONFIRM_TEXT = "drop-all-tables-in:"  # typed by a person; the tests pin the text on purpose


def approved_url(host="127.0.0.1:55432", name=APPROVED_NAME, query=""):
    return f"postgresql+psycopg://appuser:{PASSWORD}@{host}/{name}{query}"


def approval(name=APPROVED_NAME):
    return {EXPECTED_NAME_VAR: name, CONFIRM_VAR: CONFIRM_TEXT + name}


APPROVED_URL = approved_url()

APPROVAL_REFUSED = {
    "no approval variables at all": (APPROVED_URL, {}),
    "no expected name": (APPROVED_URL, {CONFIRM_VAR: CONFIRM_TEXT + APPROVED_NAME}),
    "no confirmation": (APPROVED_URL, {EXPECTED_NAME_VAR: APPROVED_NAME}),
    "a blank expected name": (APPROVED_URL, {**approval(), EXPECTED_NAME_VAR: ""}),
    "a blank confirmation": (APPROVED_URL, {**approval(), CONFIRM_VAR: ""}),
    "an expected name that is another database": (APPROVED_URL, approval("other_db")),
    "a stale confirmation for another database": (APPROVED_URL, {**approval(), CONFIRM_VAR: CONFIRM_TEXT + "other_db"}),
    "an expected name in another case": (APPROVED_URL, {**approval(), EXPECTED_NAME_VAR: "CareerSync_DB"}),
    "an expected name with a trailing space": (APPROVED_URL, {**approval(), EXPECTED_NAME_VAR: APPROVED_NAME + " "}),
    "a confirmation without its prefix": (APPROVED_URL, {**approval(), CONFIRM_VAR: APPROVED_NAME}),
    "a confirmation in another case": (APPROVED_URL, {**approval(), CONFIRM_VAR: CONFIRM_TEXT.upper() + APPROVED_NAME}),
    "a confirmation with a trailing space": (APPROVED_URL, {**approval(), CONFIRM_VAR: CONFIRM_TEXT + APPROVED_NAME + " "}),
    "a confirmation with a leading space": (APPROVED_URL, {**approval(), CONFIRM_VAR: " " + CONFIRM_TEXT + APPROVED_NAME}),
    "no port": (approved_url(host="127.0.0.1"), approval()),
    "a remote host name": (approved_url(host="db.example.com:5432"), approval()),
    "a private network address": (approved_url(host="10.0.0.5:5432"), approval()),
    "a host that only starts like the loopback": (approved_url(host="127.0.0.1.evil.example.com:5432"), approval()),
    "two hosts": (approved_url(host="127.0.0.1,10.0.0.5"), approval()),
    "no host (a unix socket)": (f"postgresql+psycopg://appuser:{PASSWORD}@/{APPROVED_NAME}?host=/var/run/postgresql", approval()),
    "a host in the query": (approved_url(query="?host=prod.example.com"), approval()),
    "a host address in the query": (approved_url(query="?hostaddr=10.0.0.5"), approval()),
    "a service in the query": (approved_url(query="?service=prod"), approval()),
    "options in the query": (approved_url(query="?options=-csearch_path%3Dprod"), approval()),
    "the reserved name postgres": (approved_url(name="postgres"), approval("postgres")),
    "the reserved name template0": (approved_url(name="template0"), approval("template0")),
    "the reserved name template1": (approved_url(name="template1"), approval("template1")),
    "a reserved name in upper case": (approved_url(name="POSTGRES"), approval("POSTGRES")),
    "no database name": (f"postgresql+psycopg://appuser:{PASSWORD}@127.0.0.1:55432", approval()),
    "another dialect": (f"mysql+pymysql://appuser:{PASSWORD}@127.0.0.1:3306/{APPROVED_NAME}", approval()),
    "something that is not a URL": (f"not a url {PASSWORD}", approval()),
    "an empty string": ("", approval()),
    "a _pgtest name with a stale confirmation": (approved_url(name="x_pgtest"), {**approval("x_pgtest"), CONFIRM_VAR: CONFIRM_TEXT + APPROVED_NAME}),
    "a _pgtest name with the expected name of another database": (approved_url(name="x_pgtest"), {**approval("x_pgtest"), EXPECTED_NAME_VAR: APPROVED_NAME}),
    "a _pgtest name with only an expected name": (approved_url(name="x_pgtest"), {EXPECTED_NAME_VAR: "x_pgtest"}),
}

SQLITE_MEMORY = ["sqlite://", "sqlite:///:memory:", "sqlite+pysqlite://", "sqlite+pysqlite:///:memory:", "sqlite:///"]
SQLITE_REFUSED = {
    "a relative file": "sqlite:///dev.db",
    "a file in the working directory": "sqlite:///./dev.db",
    "an absolute path": "sqlite:////tmp/dev.db",
    "a drive path": "sqlite:///C:/work/dev.db",
    "a file with the pysqlite driver": "sqlite+pysqlite:///dev.db",
    "memory with a query": "sqlite:///:memory:?mode=ro",
    "a shared in-memory file URI": "sqlite:///file::memory:?cache=shared&uri=true",
    "a named in-memory database": "sqlite:///file:memdb1?mode=memory&cache=shared&uri=true",
    "the dialect in upper case": "SQLITE://",
}


def test_the_names_a_person_types_and_the_runbook_uses_are_pinned():
    assert (db_safety.URL_VAR, EXPECTED_NAME_VAR, CONFIRM_VAR, db_safety.CONFIRM_PREFIX) == (
        "TEST_DATABASE_URL",
        "TEST_DATABASE_EXPECTED_NAME",
        "TEST_DATABASE_CONFIRM_DESTRUCTIVE",
        CONFIRM_TEXT,
    )
    assert db_safety.RESERVED_NAMES == {"postgres", "template0", "template1"}
    assert set(REDIRECTING_ENV) == {
        "PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS", "PGTARGETSESSIONATTRS", "PGLOADBALANCEHOSTS",
    }  # fmt: skip


# ── An approved existing database ──


def test_an_approved_database_is_accepted_and_gets_an_engine_with_no_connection(monkeypatch):
    assert resolve_target(APPROVED_URL, approval()) == Target("approved", APPROVED_NAME)
    made = []
    monkeypatch.setattr(db_safety, "create_engine", lambda url, **kwargs: made.append((url, kwargs)) or "engine")
    assert make_test_engine(APPROVED_URL, approval()) == "engine" and made == [(APPROVED_URL, {})]


def test_an_approval_that_matches_a_pgtest_name_is_also_accepted():
    url = approved_url(name="x_pgtest")
    assert resolve_target(url, approval("x_pgtest")) == Target("approved", "x_pgtest")


@pytest.mark.parametrize("url, environ", APPROVAL_REFUSED.values(), ids=APPROVAL_REFUSED.keys())
def test_an_approved_database_needs_every_condition_and_is_refused_before_an_engine_exists(url, environ, no_engine):
    with pytest.raises(UnsafeTestDatabase):
        make_test_engine(url, environ)
    with pytest.raises(UnsafeTestDatabase):
        resolve_target(url, environ)
    assert no_engine == []


@pytest.mark.parametrize("url", SAFE)
def test_every_disposable_url_of_before_is_still_disposable_without_approval(url):
    assert resolve_target(url, {}) == Target("disposable", make_url(url).database)


@pytest.mark.parametrize("url", UNSAFE.values(), ids=UNSAFE.keys())
def test_every_refused_url_of_before_is_still_refused_without_approval(url, no_engine):
    with pytest.raises(UnsafeTestDatabase):
        make_test_engine(url, {})
    assert no_engine == []


def test_the_application_database_url_is_never_the_source_of_the_target():
    with pytest.raises(UnsafeTestDatabase):
        resolve_target(APPROVED_URL, {"DATABASE_URL": APPROVED_URL})  # nothing typed: DATABASE_URL does not approve anything
    code, out, err = run_main(["--no-connect"], {"DATABASE_URL": APPROVED_URL, **approval()})
    assert code == 2 and out == ""  # TEST_DATABASE_URL is missing: DATABASE_URL is not a substitute


def test_the_environment_of_the_process_is_what_is_read_when_none_is_given(monkeypatch):
    monkeypatch.setenv(EXPECTED_NAME_VAR, APPROVED_NAME)
    monkeypatch.setenv(CONFIRM_VAR, CONFIRM_TEXT + APPROVED_NAME)
    assert resolve_target(APPROVED_URL) == Target("approved", APPROVED_NAME)
    monkeypatch.setenv("PGHOSTADDR", "10.0.0.5")
    with pytest.raises(UnsafeTestDatabase):
        resolve_target(APPROVED_URL)


# ── W1: SQLite only in memory ──


@pytest.mark.parametrize("url", SQLITE_MEMORY)
def test_sqlite_in_memory_is_accepted_with_its_options(url, monkeypatch):
    assert resolve_target(url, {}) == Target("memory", None)
    seen = []
    monkeypatch.setattr(db_safety, "create_engine", lambda u, **kwargs: seen.append((u, kwargs)) or "engine")
    assert make_test_engine(url, {}) == "engine"
    assert seen == [(url, {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool})]


@pytest.mark.parametrize("url", SQLITE_REFUSED.values(), ids=SQLITE_REFUSED.keys())
def test_a_file_backed_sqlite_database_is_refused_before_an_engine_exists(url, no_engine):
    with pytest.raises(UnsafeTestDatabase) as refused:
        make_test_engine(url, {})
    assert no_engine == []
    shown = str(refused.value)
    assert "dev.db" not in shown and "memdb1" not in shown and "C:" not in shown


# ── W3: libpq variables that can redirect the connection ──


@pytest.mark.parametrize("name", REDIRECTING_ENV)
@pytest.mark.parametrize("value", ["SECRET-VALUE", ""], ids=["a value", "an empty value"])
@pytest.mark.parametrize("mode", ["disposable", "approved"])
def test_a_redirecting_libpq_variable_refuses_both_modes_and_only_its_name_is_shown(name, value, mode, no_engine):
    url, environ = (SAFE[0], {}) if mode == "disposable" else (APPROVED_URL, approval())
    with pytest.raises(UnsafeTestDatabase) as refused:
        make_test_engine(url, {**environ, name: value})
    shown = " ".join([str(refused.value), repr(refused.value)])
    assert name in shown and "SECRET-VALUE" not in shown and PASSWORD not in shown
    assert no_engine == []


def test_sqlite_in_memory_does_not_care_about_libpq_variables():
    assert resolve_target("sqlite://", dict.fromkeys(REDIRECTING_ENV, "x")) == Target("memory", None)


def test_the_libpq_variables_that_cannot_redirect_are_not_refused():
    assert resolve_target(SAFE[0], {"PGUSER": "u", "PGPASSWORD": "p", "PGSSLMODE": "disable", "PGCONNECT_TIMEOUT": "5"}).kind == "disposable"


# ── Refusals say nothing about the target ──

# (the names of the variables may be shown: only values, names of databases, hosts and the password may not)
LEAK_PARTS = (PASSWORD, "db.example.com", "10.0.0.5", "prod", "careersync_db", "careersync_pgtest", "other_db", "x_pgtest", "appuser", "evil", "dev.db", "SECRET", "drop-all", "@", "postgres:")
LEAKING = {
    **{f"approval: {name}": (url, environ) for name, (url, environ) in APPROVAL_REFUSED.items()},
    **{f"sqlite: {name}": (url, {}) for name, url in SQLITE_REFUSED.items()},
    **{f"libpq: {name}": (APPROVED_URL, {**approval(), name: "SECRET-VALUE"}) for name in REDIRECTING_ENV},
}


@pytest.mark.parametrize("url, environ", LEAKING.values(), ids=LEAKING.keys())
def test_no_refusal_repeats_a_url_a_name_a_password_or_an_approval_value(url, environ):
    with pytest.raises(UnsafeTestDatabase) as refused:
        resolve_target(url, environ)
    error = refused.value
    shown = " ".join([str(error), repr(error), *map(str, error.args)]).lower()
    for part in LEAK_PARTS:
        assert part.lower() not in shown, part
    assert error.__cause__ is None and error.__context__ is None
    assert "no connection was made" in str(error)


# ── W2: the server must answer with the approved name before anything is dropped ──


class FakeConnection:
    def __init__(self, owner):
        self.owner = owner

    def execute(self, statement):
        self.owner.statements.append(str(statement))
        return self

    def scalar(self):
        return self.owner.answer


class FakeEngine:
    """An engine that never connects: it records the statements it is asked to run, and answers `answer` to any of them."""

    def __init__(self, url, answer=None, error=None):
        self.url, self.answer, self.error = make_url(url), answer, error
        self.statements, self.connects, self.disposed = [], 0, 0

    @contextlib.contextmanager
    def connect(self):
        self.connects += 1
        if self.error is not None:
            raise self.error
        yield FakeConnection(self)

    def dispose(self):
        self.disposed += 1


@pytest.mark.parametrize(
    "url, environ, answer",
    [(APPROVED_URL, approval(), APPROVED_NAME), (SAFE[0], {}, "careersync_pgtest"), (approved_url(name="x_pgtest"), approval("x_pgtest"), "x_pgtest")],
    ids=["approved", "disposable", "approved-pgtest"],
)
def test_the_approved_name_passes_the_identity_check_and_only_one_statement_runs(url, environ, answer):
    engine = FakeEngine(url, answer)
    assert verify_identity(engine, url, environ) is None
    assert engine.statements == ["SELECT current_database()"] and engine.disposed == 0


@pytest.mark.parametrize("answer", ["other_db", "CAREERSYNC_DB", "careersync_db ", " careersync_db", "", None, "careersync_pgtest", "postgres"])
def test_any_other_answer_disposes_the_engine_and_fails_closed_in_fixed_words(answer):
    engine = FakeEngine(APPROVED_URL, answer)
    with pytest.raises(UnsafeTestDatabase) as refused:
        verify_identity(engine, APPROVED_URL, approval())
    assert engine.statements == ["SELECT current_database()"] and engine.disposed == 1
    error = refused.value
    shown = " ".join([str(error), repr(error)]).lower()
    for part in LEAK_PARTS + (str(answer).lower() or "x",):
        if part.strip():
            assert part.lower() not in shown, part
    assert "after connecting" in str(error) and "nothing was changed" in str(error) and "no connection was made" not in str(error)
    assert error.__cause__ is None


def test_a_disposable_url_is_checked_against_its_own_name_too():
    engine = FakeEngine(SAFE[0], "someone_elses_pgtest")
    with pytest.raises(UnsafeTestDatabase):
        verify_identity(engine, SAFE[0], {})
    assert engine.disposed == 1


def test_a_connection_error_is_not_swallowed_and_not_rewritten():
    error = OperationalError("SELECT 1", {}, Exception("connection refused"))
    engine = FakeEngine(APPROVED_URL, error=error)
    with pytest.raises(OperationalError) as raised:
        verify_identity(engine, APPROVED_URL, approval())
    assert raised.value is error and engine.statements == []


@pytest.mark.parametrize(
    "other",
    [
        approved_url(name="other_db"),
        approved_url(host="127.0.0.1:55433"),
        approved_url(host="127.0.0.2:55432"),
        approved_url(host="localhost:55432"),
        APPROVED_URL.replace("appuser", "someone"),
        APPROVED_URL.replace("+psycopg", ""),
    ],
    ids=["database", "port", "host", "host-name", "user", "driver"],
)
def test_an_engine_built_from_another_url_is_refused_before_it_connects(other):
    engine = FakeEngine(other, APPROVED_NAME)
    with pytest.raises(UnsafeTestDatabase) as refused:
        verify_identity(engine, APPROVED_URL, approval())
    assert engine.connects == 0 and "no connection was made" in str(refused.value)


def test_the_rules_are_checked_again_before_any_connection():
    engine = FakeEngine(APPROVED_URL, APPROVED_NAME)
    with pytest.raises(UnsafeTestDatabase):
        verify_identity(engine, APPROVED_URL, {})  # the approval is gone: no connection
    with pytest.raises(UnsafeTestDatabase):
        verify_identity(engine, APPROVED_URL, {**approval(), "PGHOSTADDR": "10.0.0.5"})
    assert engine.connects == 0


def test_sqlite_in_memory_has_no_identity_to_check_and_never_connects():
    engine = FakeEngine("sqlite://", error=AssertionError("connected"))
    assert verify_identity(engine, "sqlite://", {}) is None and engine.connects == 0


def test_the_identity_check_comes_before_the_first_drop_in_the_fixture_and_uses_the_same_url():
    tree = ast.parse((Path(__file__).parent / "conftest.py").read_text(encoding="utf-8"))
    fixture = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "db")
    calls: dict[str, list[ast.Call]] = {}
    for call in (c for c in ast.walk(fixture) if isinstance(c, ast.Call)):
        calls.setdefault(getattr(call.func, "id", getattr(call.func, "attr", "")), []).append(call)
    make, verify, drops = calls["make_test_engine"][0], calls["verify_identity"][0], calls["drop_all"]
    assert make.lineno < verify.lineno < min(d.lineno for d in drops)
    assert [a.id for a in make.args] == ["url"] and [a.id for a in verify.args][1:] == ["url"]  # one URL, read once, for both


def test_the_guard_imports_nothing_of_the_application_and_no_dotenv():
    tree = ast.parse(Path(db_safety.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"app", "ai", "dotenv", "yaml"}


# ── W5: the preflight command ──


def run_main(argv, environ, engine=None, *, may_connect=False):
    def factory(url, env):
        assert may_connect, "the preflight connected"
        return engine

    out, err = io.StringIO(), io.StringIO()
    code = main(argv, environ, engine_factory=factory, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


OK_NO_CONNECT = "preflight ok: the rules passed, nothing was connected\n"
OK_CONNECTED = "preflight ok: the rules passed and the server answered with the approved database\n"
CLI_ENV = {"TEST_DATABASE_URL": APPROVED_URL, **approval()}


def test_no_connect_checks_the_rules_and_connects_to_nothing():
    assert run_main(["--no-connect"], CLI_ENV) == (0, OK_NO_CONNECT, "")


def test_the_normal_mode_verifies_the_identity_and_disposes_the_engine():
    engine = FakeEngine(APPROVED_URL, APPROVED_NAME)
    assert run_main([], CLI_ENV, engine, may_connect=True) == (0, OK_CONNECTED, "")
    assert engine.statements == ["SELECT current_database()"] and engine.disposed == 1


def test_the_engine_factory_gets_the_url_and_the_environment():
    seen = []
    engine = FakeEngine(APPROVED_URL, APPROVED_NAME)
    main([], CLI_ENV, engine_factory=lambda url, env: seen.append((url, env)) or engine, stdout=io.StringIO(), stderr=io.StringIO())
    assert seen == [(APPROVED_URL, CLI_ENV)]


@pytest.mark.parametrize("value", [None, "", "   "], ids=["unset", "empty", "blank"])
def test_the_command_refuses_a_missing_url(value):
    environ = {**approval(), **({} if value is None else {"TEST_DATABASE_URL": value})}
    code, out, err = run_main([], environ)
    assert (code, out) == (2, "") and err == "TEST_DATABASE_URL refused, no connection was made: TEST_DATABASE_URL is not set\n"


@pytest.mark.parametrize("url, environ", APPROVAL_REFUSED.values(), ids=APPROVAL_REFUSED.keys())
def test_the_command_exits_2_on_every_refusal_and_says_nothing_about_the_target(url, environ):
    code, out, err = run_main([], {"TEST_DATABASE_URL": url, **environ})
    shown = (out + err).lower()
    assert code == 2 and out == "" and err.startswith("TEST_DATABASE_URL refused")
    for part in LEAK_PARTS:
        assert part.lower() not in shown, part


def test_the_command_is_for_postgresql_and_refuses_sqlite():
    code, out, err = run_main([], {"TEST_DATABASE_URL": "sqlite://"})
    assert code == 2 and out == "" and "PostgreSQL database" in err


@pytest.mark.parametrize(
    "app_environ, ok",
    [
        ({"DATABASE_URL": APPROVED_URL, "CAREERSYNC_DOTENV": "0"}, True),
        ({"CAREERSYNC_DOTENV": "0"}, False),
        ({"DATABASE_URL": APPROVED_URL}, False),
        ({"DATABASE_URL": APPROVED_URL, "CAREERSYNC_DOTENV": "1"}, False),
        ({"DATABASE_URL": APPROVED_URL, "CAREERSYNC_DOTENV": ""}, False),
        ({"DATABASE_URL": approved_url(name="other_db"), "CAREERSYNC_DOTENV": "0"}, False),
        ({"DATABASE_URL": APPROVED_URL + " ", "CAREERSYNC_DOTENV": "0"}, False),
        ({"DATABASE_URL": "", "CAREERSYNC_DOTENV": "0"}, False),
    ],
    ids=["ok", "no DATABASE_URL", "no CAREERSYNC_DOTENV", "dotenv on", "dotenv empty", "another database", "trailing space", "blank DATABASE_URL"],
)
def test_the_app_flag_needs_the_same_database_url_and_no_dotenv(app_environ, ok):
    code, out, err = run_main(["--no-connect", "--app"], {**CLI_ENV, **app_environ})
    if ok:
        assert (code, out, err) == (0, OK_NO_CONNECT, "")
    else:
        shown = (out + err).lower()
        assert code == 2 and out == "" and err.startswith("TEST_DATABASE_URL refused")
        for part in LEAK_PARTS:
            assert part.lower() not in shown, part


def test_without_the_app_flag_the_application_variables_are_not_looked_at():
    assert run_main(["--no-connect"], {**CLI_ENV, "DATABASE_URL": "anything", "CAREERSYNC_DOTENV": "1"}) == (0, OK_NO_CONNECT, "")


def test_a_wrong_database_exits_2_and_the_engine_is_disposed():
    engine = FakeEngine(APPROVED_URL, "other_db")
    code, out, err = run_main([], CLI_ENV, engine, may_connect=True)
    assert (code, out) == (2, "") and "after connecting" in err and engine.disposed >= 1
    for part in LEAK_PARTS:
        assert part.lower() not in err.lower(), part


def test_a_connection_error_exits_3_and_only_its_type_is_shown():
    secret = f"password authentication failed for user appuser at host db.example.com {PASSWORD}"
    engine = FakeEngine(APPROVED_URL, error=OperationalError("SELECT 1", {}, Exception(secret)))
    code, out, err = run_main([], CLI_ENV, engine, may_connect=True)
    assert (code, out) == (3, "") and err == "preflight failed: the database could not be checked (OperationalError)\n"
    assert engine.disposed == 1


def test_the_command_runs_as_a_script_with_the_same_exit_codes_and_words():
    script = Path(db_safety.__file__)
    base = dict(os.environ)

    def run(*args, **environ):
        done = subprocess.run([sys.executable, str(script), *args], env={**base, **environ}, capture_output=True, text=True, timeout=60)
        return done.returncode, done.stdout, done.stderr

    assert run("--no-connect", **CLI_ENV) == (0, OK_NO_CONNECT, "")
    code, out, err = run("--no-connect")
    assert (code, out) == (2, "") and err == "TEST_DATABASE_URL refused, no connection was made: TEST_DATABASE_URL is not set\n"
    code, out, err = run("--no-connect", TEST_DATABASE_URL=APPROVED_URL)  # the approval was not typed
    assert code == 2 and out == "" and PASSWORD not in err and APPROVED_NAME not in err
    code, out, err = run("--no-connect", "--app", **CLI_ENV)  # DATABASE_URL is not the same one
    assert code == 2 and PASSWORD not in err and APPROVED_NAME not in err
    assert run("--help")[0] == 0
