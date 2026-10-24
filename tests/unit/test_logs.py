from pathlib import Path

from webmusicfolder.logs import LOG_FILE_NAME, LogBuffer


def test_ring_buffer_keeps_only_the_last_lines():
    buf = LogBuffer(capacity=5)
    for i in range(12):
        buf.add(f"line {i}")
    lines = buf.lines()
    assert [e["line"] for e in lines] == [f"line {i}" for i in range(7, 12)]
    assert [e["seq"] for e in lines] == [8, 9, 10, 11, 12]


def test_default_capacity_is_one_thousand():
    buf = LogBuffer()
    for i in range(1500):
        buf.add(f"l{i}")
    assert len(buf.lines()) == 1000


def test_filter_by_item_and_blank_lines_ignored():
    buf = LogBuffer()
    buf.add("a", item_id="1")
    buf.add("b", item_id="2")
    buf.add("   ")
    assert [e["line"] for e in buf.lines("1")] == ["a"]
    assert len(buf.lines()) == 2


def test_sink_receives_each_entry():
    seen = []
    buf = LogBuffer(sink=lambda kind, data: seen.append((kind, data)))
    buf.add("hello", item_id="x", title="T")
    assert seen[0][0] == "log"
    assert seen[0][1]["line"] == "hello" and seen[0][1]["title"] == "T"


def test_long_lines_are_truncated():
    buf = LogBuffer()
    buf.add("x" * 10_000)
    assert len(buf.lines()[0]["line"]) == 2000


def test_file_rotation_never_exceeds_the_cap(tmp_path: Path):
    max_bytes = 4096
    buf = LogBuffer(tmp_path, max_bytes=max_bytes, backups=2)
    for i in range(2000):
        buf.add(f"line number {i} " + "y" * 60, item_id="abc")
    buf.close()
    files = sorted(tmp_path.glob(f"{LOG_FILE_NAME}*"))
    assert [f.name for f in files] == [LOG_FILE_NAME, f"{LOG_FILE_NAME}.1", f"{LOG_FILE_NAME}.2"]
    assert all(f.stat().st_size <= max_bytes for f in files)
    # The newest line is in the live file.
    assert "line number 1999" in files[0].read_text()


def test_write_failure_does_not_raise(tmp_path: Path):
    buf = LogBuffer(tmp_path)
    assert buf._handler is not None
    buf._handler.stream.close()
    buf._handler.stream = None
    buf._handler.emit = lambda record: (_ for _ in ()).throw(OSError("disk full"))  # type: ignore[method-assign]
    buf.add("still buffered")
    assert buf.lines()[0]["line"] == "still buffered"


def test_redactor_hides_literal_secrets_and_the_cookie_path():
    from webmusicfolder.logs import Redactor

    redact = Redactor(["hunter2-pass", "/data/cookies.txt", "ab"])
    assert redact("login with hunter2-pass failed") == "login with [redacted] failed"
    assert redact("Cookies file /data/cookies.txt is bad") == "Cookies file [redacted] is bad"
    # Too short to be safe to replace everywhere.
    assert redact("about abc") == "about abc"


def test_redactor_hides_headers_and_key_values():
    from webmusicfolder.logs import Redactor

    redact = Redactor()
    assert redact("Cookie: SID=abc; HSID=def") == "Cookie: [redacted]"
    assert redact("Set-Cookie: __Secure-1PSID=zzz; Path=/") == "Set-Cookie: [redacted]"
    assert redact("Authorization: Bearer abc.def") == "Authorization: [redacted]"
    assert redact("https://x/y?token=abc123&v=1") == "https://x/y?token=[redacted]&v=1"
    assert redact("password=hunter2") == "password=[redacted]"
    assert redact("[youtube] Extracting URL: https://youtu.be/aaaaaaaaaaa") == (
        "[youtube] Extracting URL: https://youtu.be/aaaaaaaaaaa"
    )


def test_redactor_hides_netscape_cookie_rows():
    from webmusicfolder.logs import Redactor

    row = ".youtube.com\tTRUE\t/\tTRUE\t1893456000\tSID\tverysecretvalue"
    assert "verysecretvalue" not in Redactor()(row)


def test_buffer_file_and_sink_never_contain_secrets(tmp_path: Path):
    from webmusicfolder.logs import Redactor

    seen = []
    buf = LogBuffer(
        tmp_path,
        sink=lambda kind, data: seen.append(data["line"]),
        redact=Redactor(["my-password-123", "/data/cookies.txt"]),
    )
    buf.add("ERROR: bad cookies file /data/cookies.txt")
    buf.add("password=my-password-123 Cookie: SID=abc")
    buf.close()
    everything = " ".join(seen) + " ".join(e["line"] for e in buf.lines())
    everything += (tmp_path / LOG_FILE_NAME).read_text()
    for secret in ("my-password-123", "/data/cookies.txt", "SID=abc"):
        assert secret not in everything
