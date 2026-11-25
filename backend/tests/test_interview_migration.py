"""Migration 0012 (M4 S1): it follows 0011, creates exactly the three practice-interview tables and changes nothing else,
its tables equal the models (reflection, Alembic's own comparison, and the DDL rendered for PostgreSQL), it downgrades in
reverse dependency order, and the migrated tables enforce the same rules as the models.

The tests build the tables with `create_all` and the migration runs with Alembic's `Operations` (the rest of the suite does
not use migrations, issue 18). They run on SQLite, and the PostgreSQL DDL is only rendered as text: nothing here executes
the migration on PostgreSQL.
"""
import importlib.util
import io
import re
from datetime import date
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateIndex, CreateTable

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.db.session import Base
from app.models import InterviewQuota, InterviewSession

from .interview_fixtures import build_ids, make_session

# The tables of earlier migrations have expression-based indexes that SQLite cannot reflect: SQLAlchemy and Alembic warn, and say nothing about ours
pytestmark = pytest.mark.filterwarnings("ignore:Skipped unsupported reflection", "ignore:autogenerate skipping metadata-specified")

VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"
FILE = VERSIONS / "0012_practice_interviews.py"
NEW = ("interview_sessions", "interview_turns", "interview_quota")


def load():
    spec = importlib.util.spec_from_file_location("migration_0012", FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def new_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _foreign_keys_on(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def earlier_tables():
    return [t for t in Base.metadata.sorted_tables if t.name not in NEW]


@pytest.fixture
def before():
    """A database with every table of migrations 0001-0011 (built from the models) and none of the new ones."""
    engine = new_engine()
    Base.metadata.create_all(engine, tables=earlier_tables())
    yield engine
    engine.dispose()


def run(engine, step: str) -> None:
    module = load()
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            getattr(module, step)()


def snapshot(engine, names) -> dict:
    """Everything the database reports about each table, in a form that does not depend on order."""
    inspector = inspect(engine)
    out = {}
    for name in sorted(names):
        out[name] = {
            "columns": sorted(
                (c["name"], str(c["type"]), c["nullable"], None if c["default"] is None else str(c["default"]), c.get("autoincrement"))
                for c in inspector.get_columns(name)
            ),
            "primary_key": inspector.get_pk_constraint(name)["constrained_columns"],
            "foreign_keys": sorted(
                (tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]), (fk.get("options") or {}).get("ondelete"))
                for fk in inspector.get_foreign_keys(name)
            ),
            "unique": sorted((u["name"], tuple(u["column_names"])) for u in inspector.get_unique_constraints(name)),
            "indexes": sorted(
                (i["name"], tuple(i["column_names"]), bool(i["unique"]), sorted((k, str(v)) for k, v in (i.get("dialect_options") or {}).items()))
                for i in inspector.get_indexes(name)
            ),
            "checks": sorted((c["name"], " ".join(c["sqltext"].split())) for c in inspector.get_check_constraints(name)),
        }
    return out


@pytest.fixture
def model_side():
    engine = new_engine()
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


# ── The revision ──


def test_the_revision_follows_0011():
    module = load()
    assert (module.revision, module.down_revision) == ("0012", "0011")
    assert (VERSIONS / "0011_cv_reviews.py").exists()
    heads = [p.name for p in VERSIONS.glob("*.py") if re.search(r'down_revision = "0012"', p.read_text(encoding="utf-8"))]
    assert heads == ["0013_job_requirement_analyses.py"], "0013 follows the interview migration"


def test_upgrade_creates_exactly_the_three_tables_and_changes_nothing_else(before):
    pre = snapshot(before, [t.name for t in earlier_tables()])
    assert not set(NEW) & set(inspect(before).get_table_names())
    run(before, "upgrade")
    assert set(NEW) <= set(inspect(before).get_table_names())
    assert set(inspect(before).get_table_names()) == {t.name for t in earlier_tables()} | set(NEW)
    assert snapshot(before, [t.name for t in earlier_tables()]) == pre  # not one existing table was touched


def test_the_migrated_tables_equal_the_models(before, model_side):
    run(before, "upgrade")
    migrated, modelled = snapshot(before, NEW), snapshot(model_side, NEW)
    for name in NEW:
        for part in ("columns", "primary_key", "foreign_keys", "unique", "indexes", "checks"):
            assert migrated[name][part] == modelled[name][part], f"{name}.{part}"


def test_alembic_finds_no_drift_in_the_new_tables(before):
    run(before, "upgrade")
    with before.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True, "compare_server_default": True})
        diffs = compare_metadata(context, Base.metadata)

    def flat(items):
        for item in items:
            yield from flat(item) if isinstance(item, list) else [item]

    ours = [d for d in flat(diffs) if any(name in repr(d) for name in NEW)]
    assert ours == []


# ── The index on the quota day ──

DAY_INDEX = ("ix_interview_quota_kst_day", ("kst_day",), False)


def test_the_quota_day_index_exists_after_the_migration_and_matches_the_model(before, model_side):
    run(before, "upgrade")
    modelled = {(i.name, tuple(c.name for c in i.columns), i.unique) for i in Base.metadata.tables["interview_quota"].indexes}
    assert modelled == {DAY_INDEX}
    for engine in (before, model_side):  # the migrated database and the one built from the models report the same
        reflected = {(i["name"], tuple(i["column_names"]), bool(i["unique"])) for i in inspect(engine).get_indexes("interview_quota")}
        assert reflected == {DAY_INDEX}


def test_the_quota_day_index_serves_the_deletion_of_past_days(before):
    """The primary key starts with the seeker, so only this index can answer `kst_day < today` without reading every row."""
    run(before, "upgrade")
    with before.connect() as connection:
        plan = " ".join(str(row) for row in connection.execute(text("EXPLAIN QUERY PLAN DELETE FROM interview_quota WHERE kst_day < '2026-11-16'")))
    assert "ix_interview_quota_kst_day" in plan, plan


def test_downgrade_removes_the_quota_day_index_with_its_table(before):
    run(before, "upgrade")
    run(before, "downgrade")
    assert "interview_quota" not in inspect(before).get_table_names()
    with before.connect() as connection:
        left = connection.execute(text("SELECT name FROM sqlite_master WHERE name = 'ix_interview_quota_kst_day'")).all()
    assert left == []


# ── The migrated tables enforce the rules of the models ──


@pytest.fixture
def migrated_db(before):
    run(before, "upgrade")
    session = sessionmaker(bind=before, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()


def test_the_migrated_tables_enforce_the_same_rules(migrated_db):
    ids = build_ids(migrated_db)
    migrated_db.add(make_session(ids, status="live"))
    migrated_db.commit()
    for bad in (make_session(ids, status="created"), make_session(ids, status="expired"), make_session(ids, status="aborted", feedback_attempts=-1)):
        migrated_db.add(bad)
        with pytest.raises(IntegrityError):
            migrated_db.commit()
        migrated_db.rollback()
    quota = InterviewQuota.__table__
    row = {"seeker_id": ids.seeker_id, "kst_day": date(2026, 11, 16), "kind": "session", "used": 0, "quota_limit": 3}
    migrated_db.execute(quota.insert().values(**row))
    migrated_db.commit()
    with pytest.raises(IntegrityError):
        migrated_db.execute(quota.update().values(used=4))
    migrated_db.rollback()
    assert migrated_db.scalar(select(InterviewSession.status)) == "live"


# ── Downgrade ──


def test_downgrade_removes_the_three_tables_and_restores_the_earlier_schema(before):
    names = [t.name for t in earlier_tables()]
    pre = snapshot(before, names)
    run(before, "upgrade")
    run(before, "downgrade")
    assert set(inspect(before).get_table_names()) == set(names)
    assert snapshot(before, names) == pre
    run(before, "upgrade")  # and it can go up again
    assert set(NEW) <= set(inspect(before).get_table_names())


def test_tables_are_created_and_dropped_in_dependency_order(before, monkeypatch):
    calls: list[tuple[str, str]] = []
    for method in ("create_table", "drop_table", "create_index", "drop_index"):
        original = getattr(Operations, method)

        def recorder(self, name, *args, _m=method, _o=original, **kwargs):
            calls.append((_m, name))
            return _o(self, name, *args, **kwargs)

        monkeypatch.setattr(Operations, method, recorder)
    run(before, "upgrade")
    run(before, "downgrade")
    # The quota day index is created after its table and dropped explicitly before it, like the other migrations do
    day = "ix_interview_quota_kst_day"
    assert calls.index(("create_table", "interview_quota")) < calls.index(("create_index", day))
    assert calls.index(("drop_index", day)) < calls.index(("drop_table", "interview_quota"))
    created = [n for m, n in calls if m == "create_table"]
    dropped = [n for m, n in calls if m == "drop_table"]
    assert set(created) == set(dropped) == set(NEW)
    assert created.index("interview_sessions") < created.index("interview_turns")  # the turns reference the sessions
    assert dropped.index("interview_turns") < dropped.index("interview_sessions")


# ── PostgreSQL: the DDL rendered as text (not executed) ──


def render(step: str) -> str:
    out = io.StringIO()
    module = load()
    with Operations.context(MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": out})):
        getattr(module, step)()
    return out.getvalue()


def statements(sql: str) -> list[str]:
    parts = [" ".join(s.split()) for s in re.split(r";\s*\n", sql)]
    return [s for s in parts if s and s.upper() not in ("BEGIN", "COMMIT", "BEGIN;", "COMMIT;") and not s.startswith("--")]


def normalize_create_table(statement: str) -> tuple[str, list[str]]:
    name = re.match(r"CREATE TABLE (\w+) \(", statement).group(1)
    body = statement[statement.index("(") + 1 : statement.rindex(")")]
    # split on the commas that are not inside parentheses
    depth, item, items = 0, "", []
    for ch in body:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            items.append(item.strip())
            item = ""
        else:
            item += ch
    items.append(item.strip())
    return name, sorted(items)


def test_the_postgresql_ddl_of_the_migration_equals_the_ddl_of_the_models():
    dialect = postgresql.dialect()
    migration = statements(render("upgrade"))
    mig_tables = dict(normalize_create_table(s) for s in migration if s.startswith("CREATE TABLE"))
    mig_indexes = {s.rstrip(";") for s in migration if s.startswith(("CREATE INDEX", "CREATE UNIQUE INDEX"))}
    assert set(mig_tables) == set(NEW)
    assert len(migration) == len(mig_tables) + len(mig_indexes)  # nothing but these statements: no ALTER TABLE, no other table

    model_tables, model_indexes = {}, set()
    for name in NEW:
        table = Base.metadata.tables[name]
        key, items = normalize_create_table(" ".join(str(CreateTable(table).compile(dialect=dialect)).split()))
        model_tables[key] = items
        for index in table.indexes:
            model_indexes.add(" ".join(str(CreateIndex(index).compile(dialect=dialect)).split()).rstrip(";"))
    assert mig_tables == model_tables
    assert mig_indexes == model_indexes


def test_the_postgresql_ddl_uses_postgresql_types_and_the_partial_index():
    sql = " ".join(render("upgrade").split())
    assert "JSONB" in sql and "TIMESTAMP WITH TIME ZONE" in sql and "SERIAL" in sql
    assert (
        "CREATE UNIQUE INDEX uq_interview_sessions_active ON interview_sessions (seeker_id) WHERE status IN ('planning', 'created', 'live')" in sql
    )
    assert "CONSTRAINT ck_interview_quota_used CHECK (used >= 0 AND used <= quota_limit)" in sql
    assert "PRIMARY KEY (seeker_id, kst_day, kind)" in sql
    assert sql.count("ON DELETE CASCADE") == 5  # sessions: user, job, cv profile; turns: session; quota: user
    assert "REFERENCES interview_sessions" in sql and "interview_quota" in sql
    assert "CREATE INDEX ix_interview_quota_kst_day ON interview_quota (kst_day)" in sql
    quota = next(s for s in statements(render("upgrade")) if s.startswith("CREATE TABLE interview_quota"))
    assert "interview_sessions" not in quota  # no foreign key to a session


def test_the_postgresql_downgrade_drops_in_reverse_dependency_order():
    sql = " ".join(render("downgrade").split())
    drops = re.findall(r"DROP TABLE (\w+)", sql)
    assert drops.index("interview_turns") < drops.index("interview_sessions")
    assert set(drops) == set(NEW)
    assert "ALTER TABLE" not in sql


def test_the_migration_adds_no_room_avatar_audio_or_video_column_and_alters_no_table():
    sql = render("upgrade").lower()
    for word in ("room", "avatar", "audio", "video", "bytea", "cv_text", "masked_cv", "cv_quote", "weight"):
        assert word not in sql, word
    assert "alter table" not in sql
