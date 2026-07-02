from genoscribe.app import parse_user_input


def test_parse_sessions_commands():
    assert parse_user_input("sessions") == ("sessions", "")

    cmd, args = parse_user_input("session save foo --desc \"bar\"")
    assert cmd == "session_save"
    assert args == "foo --desc \"bar\""

    cmd, args = parse_user_input("session load demo")
    assert cmd == "session_load"
    assert args == "demo"

    cmd, args = parse_user_input("session delete old_run")
    assert cmd == "session_delete"
    assert args == "old_run"

    cmd, args = parse_user_input("inbox sync")
    assert cmd == "inbox"
    assert args == "sync"

    cmd, args = parse_user_input("details 3")
    assert cmd == "details"
    assert args == "3"

    cmd, args = parse_user_input("report metrics varipred")
    assert cmd == "report"
    assert args == "metrics varipred"

    cmd, args = parse_user_input("recent ask 2 how many samples")
    assert cmd == "recent"
    assert args == "ask 2 how many samples"

    cmd, args = parse_user_input("watch downloads on")
    assert cmd == "watch_downloads"
    assert args == "on"

    cmd, args = parse_user_input("mode variant")
    assert cmd == "mode"
    assert args == "variant"

    cmd, args = parse_user_input("/mode assembly")
    assert cmd == "mode"
    assert args == "assembly"

    cmd, args = parse_user_input("switch to mode paper")
    assert cmd == "mode"
    assert args == "paper"
