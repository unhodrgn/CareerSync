import pytest

from interview_agent.text_cli import main, parse_command


@pytest.mark.parametrize(
    "line, expected",
    [
        ("자바로 API를 만들었습니다", ("answer", "자바로 API를 만들었습니다")),
        ("", ("answer", "")),
        ("/silence 25", ("silence", 25.0)),
        ("/silence", ("silence", 20.0)),
        ("/silence abc", ("silence", 20.0)),
        ("/silence -3", ("silence", 0.0)),
        ("/quit", ("quit", "")),
        (" /exit ", ("quit", "")),
    ],
)
def test_commands(line, expected):
    assert parse_command(line) == expected


def test_a_missing_secret_exits_with_2_and_names_the_setting(monkeypatch, capsys):
    monkeypatch.delenv("INTERVIEW_AGENT_SECRET", raising=False)
    assert main(["--session-id", "1"]) == 2
    assert "INTERVIEW_AGENT_SECRET" in capsys.readouterr().err


def test_job_mode_needs_an_email():
    with pytest.raises(SystemExit):
        main(["--job-id", "3"])


def test_create_only_goes_with_a_job_and_not_with_an_existing_session():
    with pytest.raises(SystemExit):
        main(["--session-id", "1", "--create-only"])
