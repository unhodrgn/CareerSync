"""The one place that decides which database the destructive test fixture may touch (M4 S3c, D65).

The `db` fixture of `conftest.py` runs `Base.metadata.drop_all` and `create_all` before and after every test: against a database it drops
every application table (users, jobs, CVs, applications, the interview tables). So a PostgreSQL `TEST_DATABASE_URL` is accepted only when it
names a disposable local database, and that is decided from the URL alone, before an engine exists and so before any connection:

- the dialect is PostgreSQL;
- there is exactly one host, and it is the loopback (`localhost`, or an IP address in 127.0.0.0/8 or `::1`): no remote host, no unix socket,
  no list of hosts;
- the database name ends in `_pgtest` (and is more than that suffix);
- the query has nothing that can name another server (`host`, `hostaddr`, `service`, `options`, ...): only `connect_timeout`,
  `application_name` and `sslmode` pass.

A refusal says which rule failed and never repeats the URL, the host, the database name or the password: the message is made of fixed
words, and the parse error of an unreadable URL (which quotes it) is not chained. SQLite keeps what it had, an in-memory database shared
by every session. `TEST_DATABASE_URL` must be set by whoever runs the tests; nothing here derives it from `DATABASE_URL` or any other
variable, and nothing here reads `.env`."""
from ipaddress import ip_address

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.pool import StaticPool

REQUIRED_SUFFIX = "_pgtest"
SAFE_QUERY = frozenset({"connect_timeout", "application_name", "sslmode"})


class UnsafeTestDatabase(RuntimeError):
    """TEST_DATABASE_URL is not a disposable local PostgreSQL. The message never contains the URL."""


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


def check_disposable_postgres(url: str) -> None:
    """Return when `url` names a disposable local PostgreSQL, else raise `UnsafeTestDatabase`. Parses the URL; connects to nothing."""
    try:
        parsed = make_url(url)
    except (ArgumentError, TypeError, ValueError):
        parsed = None
    if parsed is None:  # (raised here, outside the `except`, so the parse error that quotes the URL is not attached)
        raise _refuse("it is not a database URL")
    if parsed.get_backend_name() != "postgresql":
        raise _refuse("the dialect must be PostgreSQL")
    if not _is_loopback(parsed.host):
        raise _refuse("the host must be one loopback address (localhost, 127.x.x.x or ::1)")
    name = parsed.database or ""
    if not name.endswith(REQUIRED_SUFFIX) or len(name) <= len(REQUIRED_SUFFIX):
        raise _refuse(f"the database name must end with {REQUIRED_SUFFIX}")
    if set(parsed.query) - SAFE_QUERY:
        raise _refuse("the URL has a parameter that could name another server")


def make_test_engine(url: str):
    """The engine of the `db` fixture. SQLite: one in-memory connection shared by every session, as it always was. Anything else must
    pass `check_disposable_postgres` first."""
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    check_disposable_postgres(url)
    return create_engine(url)
