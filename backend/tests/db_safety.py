"""The one place that decides which database the destructive test fixture may touch (M4 S3c, D65; approved-database mode added in M4 QA).

The `db` fixture of `conftest.py` runs `Base.metadata.drop_all` and `create_all` before and after every test: against a database it drops
every application table (users, jobs, CVs, applications, the interview tables). So a PostgreSQL `TEST_DATABASE_URL` is accepted only when it
names a database that is meant to be wiped, and that is decided from the URL and from the variables the person running the tests typed, before
an engine exists and so before any connection:

- the dialect is PostgreSQL;
- there is exactly one host, and it is the loopback (`localhost`, or an IP address in 127.0.0.0/8 or `::1`): no remote host, no unix socket,
  no list of hosts;
- the query has nothing that can name another server (`host`, `hostaddr`, `service`, `options`, ...): only `connect_timeout`,
  `application_name` and `sslmode` pass;
- no libpq environment variable that could redirect the connection is set, not even empty (`REDIRECTING_ENV`): the URL names the host, but
  libpq lets `PGHOSTADDR` and friends override where it goes;
- and one of two things about the database:

  * **disposable**: its name ends in `_pgtest` (and is more than that suffix), and no approval variable is set. This is the original mode.
  * **approved**: any other name, with an explicit port, that is not `postgres`, `template0` or `template1`, and two variables that the person
    typed in the terminal, each one repeating the name exactly: `TEST_DATABASE_EXPECTED_NAME` (the database name) and
    `TEST_DATABASE_CONFIRM_DESTRUCTIVE` (`drop-all-tables-in:` followed by the name). A missing, blank or different value, or a confirmation
    for another database, is refused; so is an approval variable set next to a `_pgtest` URL when it does not match.

SQLite is accepted only in memory (`sqlite://`, `sqlite:///:memory:`), one connection shared by every session as it always was; a file-backed
SQLite URL is refused before an engine is built.

After the engine exists, `verify_identity` opens one connection, runs `SELECT current_database()` and requires the answer to be the approved
name, exactly, before the first statement of DDL: a proxy, a tunnel or a wrong port that lands on another database is caught there, and the
engine is disposed. Connection errors are not caught: they say where and why, never the password.

A refusal says which rule failed and never repeats the URL, the host, the database name, the password or an approval value: the message is
made of fixed words (it may name a variable, never its value), and the parse error of an unreadable URL (which quotes it) is not chained.
`TEST_DATABASE_URL` must be set by whoever runs the tests; nothing here derives it from `DATABASE_URL` or any other variable, and nothing here
reads `.env` (this module imports nothing of the application).

It is also a command, to run before any other tool that touches the same database (Alembic, the purge script):

    python backend/tests/db_safety.py [--no-connect] [--app]

It checks the same rules; unless `--no-connect`, it also verifies the identity; with `--app` it also requires `DATABASE_URL` to be exactly
`TEST_DATABASE_URL` and `CAREERSYNC_DOTENV` to be `0`, so the tool that follows reads this database and not `.env`. It prints fixed words
only, exits 0 when the checks pass, 2 when a rule refuses, 3 when the database could not be reached (the type of the error only). It changes
nothing in any database."""
import argparse
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from ipaddress import ip_address

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.pool import StaticPool

REQUIRED_SUFFIX = "_pgtest"
SAFE_QUERY = frozenset({"connect_timeout", "application_name", "sslmode"})
RESERVED_NAMES = frozenset({"postgres", "template0", "template1"})

URL_VAR = "TEST_DATABASE_URL"
EXPECTED_NAME_VAR = "TEST_DATABASE_EXPECTED_NAME"
CONFIRM_VAR = "TEST_DATABASE_CONFIRM_DESTRUCTIVE"
CONFIRM_PREFIX = "drop-all-tables-in:"

# libpq reads these when the URL does not say; the ones that can send the connection somewhere else, or to another database, or change
# the session it opens. Present is enough, even empty.
REDIRECTING_ENV = (
    "PGHOST",
    "PGHOSTADDR",
    "PGPORT",
    "PGDATABASE",
    "PGSERVICE",
    "PGSERVICEFILE",
    "PGOPTIONS",
    "PGTARGETSESSIONATTRS",
    "PGLOADBALANCEHOSTS",
)


class UnsafeTestDatabase(RuntimeError):
    """TEST_DATABASE_URL is not a database that may be wiped. The message never contains the URL or an approval value."""


def _refuse(rule: str) -> UnsafeTestDatabase:
    return UnsafeTestDatabase(f"TEST_DATABASE_URL refused, no connection was made: {rule}")


def _is_loopback(host: str | None) -> bool:
    if not host or "," in host:
        return False
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:  # a name, or a unix-socket path
        return False


def _parse(url: str):
    try:
        parsed = make_url(url)
    except (ArgumentError, TypeError, ValueError):
        parsed = None
    if parsed is None:  # (raised here, outside the `except`, so the parse error that quotes the URL is not attached)
        raise _refuse("it is not a database URL")
    return parsed


def _check_endpoint(parsed) -> None:
    if parsed.get_backend_name() != "postgresql":
        raise _refuse("the dialect must be PostgreSQL")
    if not _is_loopback(parsed.host):
        raise _refuse("the host must be one loopback address (localhost, 127.x.x.x or ::1)")


def _check_query(parsed) -> None:
    if set(parsed.query) - SAFE_QUERY:
        raise _refuse("the URL has a parameter that could name another server")


def check_disposable_postgres(url: str) -> None:
    """Return when `url` names a disposable local PostgreSQL (a `_pgtest` name), else raise `UnsafeTestDatabase`. Parses the URL; connects to nothing."""
    parsed = _parse(url)
    _check_endpoint(parsed)
    name = parsed.database or ""
    if not name.endswith(REQUIRED_SUFFIX) or len(name) <= len(REQUIRED_SUFFIX):
        raise _refuse(f"the database name must end with {REQUIRED_SUFFIX}")
    _check_query(parsed)


def check_approved_postgres(url: str, environ: Mapping[str, str] | None = None) -> None:
    """Return when `url` names a local PostgreSQL database that the person running the tests approved for destruction by typing its name
    twice (`TEST_DATABASE_EXPECTED_NAME`, `TEST_DATABASE_CONFIRM_DESTRUCTIVE`), else raise `UnsafeTestDatabase`. Connects to nothing."""
    environ = os.environ if environ is None else environ
    parsed = _parse(url)
    _check_endpoint(parsed)
    if parsed.port is None:
        raise _refuse("the URL must name a port")
    name = parsed.database or ""
    if not name:
        raise _refuse("the URL must name a database")
    if name.lower() in RESERVED_NAMES:
        raise _refuse("the database name is a reserved PostgreSQL name")
    _check_query(parsed)
    if environ.get(EXPECTED_NAME_VAR, "") != name:
        raise _refuse(f"{EXPECTED_NAME_VAR} must be set to the database name of the URL, exactly")
    if environ.get(CONFIRM_VAR, "") != CONFIRM_PREFIX + name:
        raise _refuse(f"{CONFIRM_VAR} must be set to the fixed confirmation text for that database, exactly")


def check_libpq_environment(environ: Mapping[str, str] | None = None) -> None:
    """Refuse while a libpq variable that can redirect the connection is set, even to an empty value. Only the name is ever shown."""
    environ = os.environ if environ is None else environ
    for name in REDIRECTING_ENV:
        if name in environ:
            raise _refuse(f"{name} is set and could redirect the connection")


def _check_in_memory_sqlite(parsed) -> None:
    if parsed.query or parsed.database not in (None, "", ":memory:"):
        raise _refuse("SQLite is accepted only in memory")


@dataclass(frozen=True)
class Target:
    kind: str  # "memory" (SQLite in memory), "disposable" (a `_pgtest` name) or "approved" (typed in the terminal)
    database: str | None  # the name `current_database()` must answer; None for SQLite


def resolve_target(url: str, environ: Mapping[str, str] | None = None) -> Target:
    """Everything that can be decided from the URL and the environment, without a connection. Raises `UnsafeTestDatabase`."""
    environ = os.environ if environ is None else environ
    parsed = _parse(url)
    if parsed.get_backend_name() == "sqlite":
        _check_in_memory_sqlite(parsed)
        return Target("memory", None)
    name = parsed.database or ""
    approving = EXPECTED_NAME_VAR in environ or CONFIRM_VAR in environ
    if not approving and name.endswith(REQUIRED_SUFFIX) and len(name) > len(REQUIRED_SUFFIX):
        check_disposable_postgres(url)
        check_libpq_environment(environ)
        return Target("disposable", name)
    check_approved_postgres(url, environ)
    check_libpq_environment(environ)
    return Target("approved", name)


def make_test_engine(url: str, environ: Mapping[str, str] | None = None):
    """The engine of the `db` fixture. SQLite (in memory only): one connection shared by every session, as it always was. Anything else
    must pass `resolve_target` first. No connection is made here: `verify_identity` is the first one."""
    target = resolve_target(url, environ)
    if target.kind == "memory":
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return create_engine(url)


def verify_identity(engine, url: str, environ: Mapping[str, str] | None = None) -> None:
    """Before the first DDL: the server must answer `SELECT current_database()` with the approved name, exactly. Nothing else is run.

    The rules are checked again first (no connection if they refuse), and so is that the engine was built from this very URL. On a different
    answer the engine is disposed and `UnsafeTestDatabase` is raised, in fixed words. SQLite in memory has no identity to check. A connection
    error is not caught."""
    target = resolve_target(url, environ)
    if target.kind == "memory":
        return
    wanted, built = make_url(url), engine.url
    key = ("drivername", "host", "port", "database", "username")
    if tuple(getattr(built, name) for name in key) != tuple(getattr(wanted, name) for name in key):
        raise _refuse("the engine was not built from the approved URL")
    with engine.connect() as connection:
        actual = connection.execute(text("SELECT current_database()")).scalar()
    if actual != target.database:
        engine.dispose()
        raise UnsafeTestDatabase(
            "TEST_DATABASE_URL refused after connecting: the server answered with a database other than the approved one, so nothing was changed"
        )


# ── The command: a preflight for every other tool that uses the same database ──


def check_app_environment(url: str, environ: Mapping[str, str]) -> None:
    """For a tool that reads `DATABASE_URL` (Alembic, `scripts/purge_interviews.py`): it must read this database, and not `.env`."""
    if environ.get("DATABASE_URL") != url:
        raise _refuse("DATABASE_URL must be set to TEST_DATABASE_URL, exactly")
    if environ.get("CAREERSYNC_DOTENV") != "0":
        raise _refuse("CAREERSYNC_DOTENV must be 0")


def main(
    argv: list[str] | None = None,
    environ: Mapping[str, str] | None = None,
    *,
    engine_factory: Callable = make_test_engine,
    stdout=None,
    stderr=None,
) -> int:
    """The preflight. Fixed words only; changes nothing in any database."""
    parser = argparse.ArgumentParser(prog="db_safety.py", description="Preflight for a command that is about to use the test database.")
    parser.add_argument("--no-connect", action="store_true", help="check the URL and the environment only; do not connect")
    parser.add_argument("--app", action="store_true", help="also require DATABASE_URL to equal TEST_DATABASE_URL and CAREERSYNC_DOTENV to be 0")
    args = parser.parse_args(argv)
    environ = os.environ if environ is None else environ
    out, err = stdout or sys.stdout, stderr or sys.stderr
    try:
        url = environ.get(URL_VAR, "")
        if not url.strip():
            raise _refuse(f"{URL_VAR} is not set")
        if args.app:
            check_app_environment(url, environ)
        if resolve_target(url, environ).kind == "memory":
            raise _refuse("the preflight is for a PostgreSQL database")
        if not args.no_connect:
            engine = engine_factory(url, environ)
            try:
                verify_identity(engine, url, environ)
            finally:
                engine.dispose()
    except UnsafeTestDatabase as refused:
        print(str(refused), file=err)
        return 2
    except Exception as error:  # noqa: BLE001  (the database could not be reached: the type only, a message can name hosts and users)
        print(f"preflight failed: the database could not be checked ({type(error).__name__})", file=err)
        return 3
    print(
        "preflight ok: the rules passed, nothing was connected"
        if args.no_connect
        else "preflight ok: the rules passed and the server answered with the approved database",
        file=out,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
