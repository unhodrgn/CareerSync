"""Migration 0012 executed on PostgreSQL, and the catalog of what it builds (M4 PostgreSQL QA, N1 and N2): PostgreSQL only.

Nothing else in the suite runs the migration on PostgreSQL: test_interview_migration.py runs it on SQLite and only renders the PostgreSQL
DDL as text. These tests take the database the `db` fixture built (the three tables made from the models), run the migration's own
`downgrade()` and `upgrade()` through Alembic's `Operations` on a real connection, and compare what PostgreSQL reports. No Alembic command is
run and `alembic_version` is not touched, so they work whatever the database's version table says.

N1 (up, down, up): the 0011 schema is what is left after `downgrade()` (the earlier tables untouched, the version table ignored), and what
`upgrade()` builds, the first time and again after a second down and up, is what the models build: columns, types, defaults, primary keys,
foreign keys, unique constraints, indexes and checks as PostgreSQL reports them, and an empty `compare_metadata` for the three tables.
N2 (catalog): on the schema built from the models and on the one the migration builds, the same facts: the JSON columns are `jsonb`, the
moments are `timestamptz`, the one-active-session index is a unique partial index on exactly three statuses, the five foreign keys all
cascade (and nothing links the quota to a session), the ten checks exist by name, and the keys and indexes are the reviewed ones.

They need `TEST_DATABASE_URL` on PostgreSQL (see db_safety.py: the fixture wipes the application tables) and are SKIPPED without it. They
ran and passed on PostgreSQL on 2026-11-22 (D77)."""
import importlib.util
import re
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.db.session import Base

from .test_interview_ingest_concurrency import PG

VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"
FILE = VERSIONS / "0012_practice_interviews.py"
NEW = ("interview_sessions", "interview_turns", "interview_quota")
PARTS = ("columns", "primary_key", "foreign_keys", "unique", "indexes", "checks")


def load():
    spec = importlib.util.spec_from_file_location("migration_0012_postgres", FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(engine, step: str) -> None:
    """The migration's own `upgrade()` or `downgrade()`, on a real connection, in one transaction."""
    module = load()
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            getattr(module, step)()


def earlier_tables() -> list[str]:
    return [t.name for t in Base.metadata.sorted_tables if t.name not in NEW]


def application_tables(engine) -> set[str]:
    """The tables of the application. `alembic_version` is Alembic's, not ours, and may or may not be there."""
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def snapshot(engine, names) -> dict:
    """What PostgreSQL reports about each table, in a form that does not depend on order. Both sides of every comparison come from PostgreSQL."""
    inspector = inspect(engine)
    out = {}
    for name in sorted(names):
        out[name] = {
            "columns": sorted(
                (c["name"], str(c["type"]), c["nullable"], None if c["default"] is None else str(c["default"])) for c in inspector.get_columns(name)
            ),
            "primary_key": inspector.get_pk_constraint(name)["constrained_columns"],
            "foreign_keys": sorted(
                (fk["name"], tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]), (fk.get("options") or {}).get("ondelete"))
                for fk in inspector.get_foreign_keys(name)
            ),
            "unique": sorted((u["name"], tuple(u["column_names"])) for u in inspector.get_unique_constraints(name)),
            "indexes": sorted(
                (
                    i["name"],
                    tuple(str(c) for c in i["column_names"]),
                    str(i.get("expressions")),
                    bool(i["unique"]),
                    sorted((k, str(v)) for k, v in (i.get("dialect_options") or {}).items()),
                )
                for i in inspector.get_indexes(name)
            ),
            "checks": sorted((c["name"], " ".join(c["sqltext"].split())) for c in inspector.get_check_constraints(name)),
        }
    return out


def same_schema(migrated: dict, modelled: dict, label: str) -> None:
    for name in NEW:
        for part in PARTS:
            assert migrated[name][part] == modelled[name][part], f"{label}: {name}.{part}"


# ── N1: up, down, up ──


@PG
def test_postgres_the_migration_goes_down_to_the_previous_schema_and_up_again_to_the_models_schema(db):
    engine = db.get_bind()
    models = snapshot(engine, NEW)  # the fixture built these from the models
    earlier = snapshot(engine, earlier_tables())
    assert set(models) == set(NEW) and all(models[name]["columns"] for name in NEW)
    for cycle in ("down and up", "down and up again"):
        run(engine, "downgrade")
        assert application_tables(engine) == set(earlier_tables()), f"{cycle}: after the downgrade only the earlier tables are left"
        assert snapshot(engine, earlier_tables()) == earlier, f"{cycle}: the downgrade touched an earlier table"
        run(engine, "upgrade")
        assert application_tables(engine) == set(earlier_tables()) | set(NEW), cycle
        assert snapshot(engine, earlier_tables()) == earlier, f"{cycle}: the upgrade touched an earlier table"
        same_schema(snapshot(engine, NEW), models, cycle)


@PG
def test_postgres_alembic_finds_no_drift_between_the_migrated_tables_and_the_models(db):
    engine = db.get_bind()
    run(engine, "downgrade")
    run(engine, "upgrade")
    with engine.connect() as connection:
        # Types are compared here; the defaults are compared exactly by the snapshot of the test above
        diffs = compare_metadata(MigrationContext.configure(connection, opts={"compare_type": True}), Base.metadata)

    def flat(items):
        for item in items:
            yield from flat(item) if isinstance(item, list) else [item]

    ours = [d for d in flat(diffs) if any(name in repr(d) for name in NEW)]
    assert ours == [], ours  # (the tables of earlier migrations are not this test's business: only a difference in these three fails it)


# ── N2: the catalog, on the schema of the models and on the one the migration builds ──


@pytest.fixture(params=["models", "migration"])
def built(db, request):
    """The engine of a database whose three interview tables were made by the models (as the fixture left them) or by the migration."""
    engine = db.get_bind()
    if request.param == "migration":
        run(engine, "downgrade")
        run(engine, "upgrade")
    return engine


JSON_COLUMNS = {"interview_sessions": ("plan", "limits", "coverage", "feedback"), "interview_turns": ("analysis", "masked_kinds")}
NOT_NULL_JSON = {("interview_sessions", "limits")}
MOMENTS = {
    "interview_sessions": (
        "consent_at", "created_at", "started_at", "ended_at", "active_until", "expires_at", "feedback_at", "feedback_lease_until",
    ),
    "interview_turns": ("created_at",),
}  # fmt: skip
SMALL_INTEGERS = {"interview_sessions": ("feedback_attempts",), "interview_turns": ("item_index",), "interview_quota": ("used", "quota_limit")}


def columns_of(engine, table):
    return {c["name"]: c for c in inspect(engine).get_columns(table)}


@PG
def test_postgres_the_json_columns_are_jsonb_the_moments_have_a_time_zone_and_the_counters_are_small(built):
    for table, names in JSON_COLUMNS.items():
        columns = columns_of(built, table)
        for name in names:
            assert isinstance(columns[name]["type"], postgresql.JSONB), (table, name, columns[name]["type"])
            assert columns[name]["nullable"] is ((table, name) not in NOT_NULL_JSON), (table, name)
    for table, names in MOMENTS.items():
        columns = columns_of(built, table)
        for name in names:
            kind = columns[name]["type"]
            assert isinstance(kind, postgresql.TIMESTAMP) and kind.timezone, (table, name, kind)
    for table, names in SMALL_INTEGERS.items():
        columns = columns_of(built, table)
        for name in names:
            assert isinstance(columns[name]["type"], sa.SmallInteger), (table, name, columns[name]["type"])
    assert isinstance(columns_of(built, "interview_quota")["kst_day"]["type"], sa.Date)


@PG
def test_postgres_the_active_session_index_is_a_unique_partial_index_on_exactly_three_statuses(built):
    indexes = {i["name"]: i for i in inspect(built).get_indexes("interview_sessions")}
    active = indexes["uq_interview_sessions_active"]
    assert active["unique"] and active["column_names"] == ["seeker_id"]
    predicate = active["dialect_options"]["postgresql_where"]
    assert set(re.findall(r"'([a-z]+)'", predicate)) == {"planning", "created", "live"}, predicate


@PG
def test_postgres_the_tables_have_the_reviewed_keys_and_named_indexes(built):
    inspector = inspect(built)
    assert inspector.get_pk_constraint("interview_sessions")["constrained_columns"] == ["id"]
    assert inspector.get_pk_constraint("interview_turns")["constrained_columns"] == ["id"]
    assert inspector.get_pk_constraint("interview_quota")["constrained_columns"] == ["seeker_id", "kst_day", "kind"]
    unique = {u["name"]: u["column_names"] for u in inspector.get_unique_constraints("interview_turns")}
    assert unique == {"uq_interview_turns_session_seq": ["session_id", "seq"]}
    names = {table: {i["name"] for i in inspector.get_indexes(table)} for table in NEW}
    assert names["interview_sessions"] == {
        "ix_interview_sessions_job_id",
        "ix_interview_sessions_cv_profile_id",
        "ix_interview_sessions_expires_at",
        "ix_interview_sessions_seeker_created",
        "uq_interview_sessions_active",
    }
    assert names["interview_quota"] == {"ix_interview_quota_kst_day"}
    assert names["interview_turns"] <= {"uq_interview_turns_session_seq"}  # the index of the unique constraint, if the inspector lists it
    seeker_created = next(i for i in inspector.get_indexes("interview_sessions") if i["name"] == "ix_interview_sessions_seeker_created")
    assert seeker_created["column_names"] == ["seeker_id", "created_at"] and not seeker_created["unique"]
    day = inspector.get_indexes("interview_quota")[0]
    assert day["column_names"] == ["kst_day"] and not day["unique"]


EXPECTED_FOREIGN_KEYS = {
    ("interview_sessions", "seeker_id", "users"),
    ("interview_sessions", "job_id", "job_postings"),
    ("interview_sessions", "cv_profile_id", "cv_profiles"),
    ("interview_turns", "session_id", "interview_sessions"),
    ("interview_quota", "seeker_id", "users"),
}


@PG
def test_postgres_there_are_five_foreign_keys_each_one_cascades_and_the_quota_has_none_to_a_session(built):
    inspector = inspect(built)
    found = set()
    for table in NEW:
        for fk in inspector.get_foreign_keys(table):
            assert len(fk["constrained_columns"]) == 1, (table, fk["name"])
            assert (fk.get("options") or {}).get("ondelete") == "CASCADE", (table, fk["name"])
            found.add((table, fk["constrained_columns"][0], fk["referred_table"]))
    assert found == EXPECTED_FOREIGN_KEYS  # a sixth, such as quota -> session, would give a reservation back with a deleted session


EXPECTED_CHECKS = {
    "interview_sessions": {"ck_interview_sessions_status", "ck_interview_sessions_feedback_attempts", "ck_interview_sessions_feedback_method"},
    "interview_turns": {"ck_interview_turns_seq", "ck_interview_turns_role", "ck_interview_turns_item_index", "ck_interview_turns_text_len"},
    "interview_quota": {"ck_interview_quota_kind", "ck_interview_quota_limit", "ck_interview_quota_used"},
}


@PG
def test_postgres_the_ten_check_constraints_exist_by_name(built):
    inspector = inspect(built)
    found = {table: {c["name"] for c in inspector.get_check_constraints(table)} for table in NEW}
    assert found == EXPECTED_CHECKS
    assert sum(len(names) for names in found.values()) == 10
