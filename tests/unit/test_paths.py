import pytest

from webmusicfolder import paths
from webmusicfolder.paths import PathError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Song", "Song"),
        ("a/b\\c", "a b c"),
        ('AC/DC: "Hells" <Bells>?', "AC DC Hells Bells"),
        ("  spaced   out  ", "spaced out"),
        ("..", "untitled"),
        ("", "untitled"),
        ("...hidden", "hidden"),
        ("trailing.", "trailing"),
        ("CON", "_CON"),
        ("nul.txt", "_nul.txt"),
        ("tab\tand\nnewline", "tab and newline"),
        ("Café ☕ 日本語", "Café ☕ 日本語"),
    ],
)
def test_sanitize_name(raw, expected):
    assert paths.sanitize_name(raw) == expected


def test_sanitize_long_title_fits_byte_limit_without_splitting_chars():
    result = paths.sanitize_name("é" * 500)
    assert len(result.encode()) <= paths.MAX_NAME_BYTES
    assert set(result) == {"é"}


@pytest.mark.parametrize("raw", ["../x", "a/b", "a\\b", ".hidden", "..", "x" * 81, "a\x00b", "a."])
def test_validate_subfolder_rejects(raw):
    with pytest.raises(PathError):
        paths.validate_subfolder(raw)


@pytest.mark.parametrize(
    ("raw", "expected"), [("", ""), ("  ", ""), ("geek", "geek"), (" a b ", "a b")]
)
def test_validate_subfolder_accepts(raw, expected):
    assert paths.validate_subfolder(raw) == expected


def test_resolve_inside_ok(tmp_path):
    assert paths.resolve_inside(tmp_path, "geek", "a.mp3") == tmp_path.resolve() / "geek" / "a.mp3"
    assert paths.resolve_inside(tmp_path) == tmp_path.resolve()


def test_resolve_inside_rejects_traversal(tmp_path):
    with pytest.raises(PathError):
        paths.resolve_inside(tmp_path, "..", "x")


def test_resolve_inside_rejects_sibling_with_common_prefix(tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    (tmp_path / "music2").mkdir()
    with pytest.raises(PathError):
        paths.resolve_inside(music, "..", "music2", "x")


def test_resolve_inside_rejects_symlink_escape(tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (music / "link").symlink_to(outside)
    with pytest.raises(PathError):
        paths.resolve_inside(music, "link", "a.mp3")


def test_list_subfolders_skips_hidden_files_and_symlinks(tmp_path):
    for name in ("Zeta", "alpha", ".hidden"):
        (tmp_path / name).mkdir()
    (tmp_path / "file.mp3").write_bytes(b"")
    (tmp_path / "link").symlink_to(tmp_path / "alpha")
    assert paths.list_subfolders(tmp_path) == ["alpha", "Zeta"]


def test_list_subfolders_missing_dir(tmp_path):
    assert paths.list_subfolders(tmp_path / "nope") == []


def test_choose_filename_free_and_collision(tmp_path):
    assert paths.choose_filename(tmp_path, "Intro", "aaaaaaaaaaa") == "Intro.mp3"
    (tmp_path / "Intro.mp3").write_bytes(b"")
    assert paths.choose_filename(tmp_path, "Intro", "bbbbbbbbbbb") == "Intro [bbbbbbbbbbb].mp3"
    assert paths.choose_filename(tmp_path, "Intro", "aaaaaaaaaaa", owned=True) == "Intro.mp3"


def test_choose_filename_long_title_with_id_stays_within_limit(tmp_path):
    title = "x" * 400
    first = paths.choose_filename(tmp_path, title, "aaaaaaaaaaa")
    (tmp_path / first).write_bytes(b"")
    second = paths.choose_filename(tmp_path, title, "bbbbbbbbbbb")
    assert second != first
    assert len(second.encode()) <= 255
    assert second.endswith(" [bbbbbbbbbbb].mp3")
