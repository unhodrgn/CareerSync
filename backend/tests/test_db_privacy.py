"""The database engine does not put bound values into errors or logs (M4 S3c, D65).

The values of an interview are masked transcripts, plans and feedback, and the CV features bind masked CV text: an unhandled database
error is logged with its SQL, and SQLAlchemy adds the bound parameters to that text unless the engine hides them. The engine of the app
is built from `ENGINE_OPTIONS`; the error test builds a SQLite engine from the same options (the app's engine points at PostgreSQL and
is never connected here) and an engine without them, to show the test would see a leak.

What the option does not cover is a value that the database server itself writes into an error (PostgreSQL names the failing row of a
check or not-null violation); nothing here claims it does."""
import ast
import logging
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, String, Table, MetaData, create_engine, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from app.db import session as session_module

ROOT = Path(__file__).resolve().parents[2]
MARKER = "SECRET-MARKER-답변-내용"


def _engine(**options):
    return create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, **options)


def _collide(engine) -> IntegrityError:
    """Two rows with the same unique value: the second insert fails, with the marker as its bound parameter."""
    table = Table("notes", MetaData(), Column("id", Integer, primary_key=True), Column("body", String, unique=True))
    table.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(table).values(body=MARKER))
    with pytest.raises(IntegrityError) as error:
        with engine.begin() as conn:
            conn.execute(insert(table).values(body=MARKER))
    return error.value


def test_the_apps_engine_hides_parameters():
    assert session_module.engine.hide_parameters is True
    assert session_module.ENGINE_OPTIONS["hide_parameters"] is True


def test_an_error_and_the_sql_log_carry_no_bound_value(caplog):
    caplog.set_level(logging.INFO, logger="sqlalchemy.engine")
    error = _collide(_engine(**session_module.ENGINE_OPTIONS))
    # The message is what a traceback and a log line print. (`error.params` still holds the values as an attribute; nothing logs it.)
    assert MARKER not in str(error) and MARKER not in repr(error)
    assert MARKER not in caplog.text
    assert "INSERT INTO notes" in caplog.text and "hidden" in caplog.text  # the statement is logged, its values are not


def test_the_same_check_sees_the_leak_when_the_engine_does_not_hide_parameters(caplog):
    """The control: without the option the marker is in the error text and the log, so the test above can fail."""
    caplog.set_level(logging.INFO, logger="sqlalchemy.engine")
    error = _collide(_engine())
    assert MARKER in str(error)
    assert MARKER in caplog.text


def test_the_app_builds_its_one_engine_from_those_options():
    """Only `app/db/session.py` creates an engine in app code, and it passes `ENGINE_OPTIONS`; a second engine would not hide parameters."""
    found = []
    for root in ("backend/app", "scripts", "ai"):
        for path in sorted((ROOT / root).rglob("*.py")):
            if "tests" in path.relative_to(ROOT).parts or "__pycache__" in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) in {"create_engine", "engine_from_config"}:
                    options = [k.value.id for k in node.keywords if k.arg is None and isinstance(k.value, ast.Name)]
                    found.append((path.relative_to(ROOT).as_posix(), options))
    assert found == [("backend/app/db/session.py", ["ENGINE_OPTIONS"])]
