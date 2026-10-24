import asyncio
import os

import pytest

from webmusicfolder.queue_worker import WorkerBusyError
from webmusicfolder.runner_client import RunnerSpec
from webmusicfolder.ytdlp_update import UpdateBusyError, UpdateError


async def test_version_comes_from_the_runner(make_updater):
    updater = make_updater()
    assert await updater.version() == "2020.01.01"


async def test_update_reports_old_and_new_and_installs_into_the_package_dir(make_updater):
    updater = make_updater("ok:2099.05.06")
    result = await updater.update()
    assert (result.old, result.new, result.changed) == ("2020.01.01", "2099.05.06", True)
    assert (make_updater.package_dir / "version.txt").read_text() == "2099.05.06"
    assert not make_updater.package_dir.with_name("ytdlp_pkg.new").exists()
    assert not make_updater.package_dir.with_name("ytdlp_pkg.old").exists()
    # The cached version follows the update, and the next runner start sees the new package.
    assert await updater.version() == "2099.05.06"


async def test_second_update_replaces_the_first(make_updater):
    await make_updater("ok:2099.01.01").update()
    result = await make_updater("ok:2099.02.02").update()
    assert (result.old, result.new) == ("2099.01.01", "2099.02.02")


async def test_failed_pip_keeps_the_previous_package(make_updater):
    make_updater.package_dir.mkdir(parents=True)
    (make_updater.package_dir / "version.txt").write_text("2021.01.01")
    updater = make_updater("fail")
    with pytest.raises(UpdateError, match="Could not find a version"):
        await updater.update()
    assert (make_updater.package_dir / "version.txt").read_text() == "2021.01.01"
    assert not make_updater.package_dir.with_name("ytdlp_pkg.new").exists()
    assert await updater.version() == "2021.01.01"


async def test_package_that_does_not_import_is_not_swapped_in(make_updater):
    updater = make_updater("broken")
    with pytest.raises(UpdateError, match="failed to import"):
        await updater.update()
    assert not make_updater.package_dir.exists()
    assert await updater.version() == "2020.01.01"


async def test_pip_that_installs_nothing_is_an_error(make_updater):
    with pytest.raises(UpdateError, match="installed nothing"):
        await make_updater("nothing").update()


async def test_pip_timeout_is_reported_and_cleaned_up(make_updater):
    updater = make_updater("slow:30", timeout_s=0.3)
    with pytest.raises(UpdateError, match="timed out"):
        await updater.update()
    assert not make_updater.package_dir.exists()
    assert not updater.updating


async def test_only_one_update_runs_at_a_time(make_updater):
    updater = make_updater("slow:0.5")
    first = asyncio.create_task(updater.update())
    await asyncio.sleep(0.1)
    assert updater.updating
    with pytest.raises(UpdateBusyError):
        await updater.update()
    assert (await first).new == "9999"
    assert not updater.updating


async def test_crash_between_the_two_renames_is_recovered(make_updater):
    package = make_updater.package_dir
    old = package.with_name("ytdlp_pkg.old")
    old.mkdir(parents=True)
    (old / "version.txt").write_text("2021.01.01")
    package.with_name("ytdlp_pkg.new").mkdir()
    updater = make_updater()
    assert (package / "version.txt").read_text() == "2021.01.01"
    assert not old.exists() and not package.with_name("ytdlp_pkg.new").exists()
    assert await updater.version() == "2021.01.01"


def test_failed_swap_restores_the_working_package(make_updater, tmp_path):
    package = make_updater.package_dir
    package.mkdir(parents=True)
    (package / "version.txt").write_text("2021.01.01")
    updater = make_updater()
    with pytest.raises(UpdateError, match="Cannot install"):
        updater._swap(tmp_path / "missing_staging")
    assert (package / "version.txt").read_text() == "2021.01.01"


def test_runner_environment_puts_the_data_package_first(tmp_path, monkeypatch):
    package = tmp_path / "ytdlp_pkg"
    monkeypatch.setenv("PYTHONPATH", "/existing")
    assert RunnerSpec(extra_pythonpath=package).environment()["PYTHONPATH"] == "/existing"
    package.mkdir()
    env = RunnerSpec(extra_pythonpath=package).environment()
    assert env["PYTHONPATH"] == f"{package}{os.pathsep}/existing"
    monkeypatch.delenv("PYTHONPATH")
    assert RunnerSpec(extra_pythonpath=package).environment()["PYTHONPATH"] == str(package)


async def test_worker_is_held_during_maintenance_and_refuses_when_busy(settings, fake_runner):
    from webmusicfolder.main import create_app

    app = create_app(settings, runner=fake_runner())
    worker = app.state.worker
    async with worker.exclusive():
        assert worker.maintenance
        with pytest.raises(WorkerBusyError):
            async with worker.exclusive():
                pass
    assert not worker.maintenance
