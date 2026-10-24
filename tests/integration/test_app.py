from webmusicfolder.main import load_or_create_secret


def test_healthz_is_public(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.text == "ok"


def test_secret_generated_once_and_reused(settings):
    first = load_or_create_secret(settings)
    path = settings.data_dir / "secret.key"
    assert path.stat().st_mode & 0o777 == 0o600
    assert load_or_create_secret(settings) == first


def test_env_secret_wins(settings):
    from dataclasses import replace

    s = replace(settings, secret="fixed")
    assert load_or_create_secret(s) == "fixed"
    assert not (s.data_dir / "secret.key").exists()


def test_run_exits_with_clear_message_without_password(monkeypatch, capsys):
    import pytest

    from webmusicfolder.main import run

    monkeypatch.delenv("WMF_PASSWORD", raising=False)
    with pytest.raises(SystemExit) as exc:
        run()
    assert exc.value.code == 2
    assert "WMF_PASSWORD" in capsys.readouterr().err


def test_downloads_page_has_submit_form(client):
    from tests.conftest import login

    login(client)
    html = client.get("/").text
    assert 'x-data="submitForm()"' in html
    assert 'name="csrf-token"' in html
    # app.js must load before Alpine so Alpine.data is registered in alpine:init.
    assert html.index("/static/js/app.js") < html.index("/static/vendor/alpine.min.js")
