"""安装包仓库：路径不能逃出目录，错误信息不能带本机绝对路径。"""

from __future__ import annotations

from pathlib import Path

import pytest

from application.releases.desktop import DesktopReleaseService
from domain.desktop_release import ReleaseUnavailable
from infrastructure.releases.filesystem import FilesystemReleaseRepository


def test_missing_file_hides_absolute_path(tmp_path: Path) -> None:
    repo = FilesystemReleaseRepository(tmp_path, "Nexora-Setup.exe", max_bytes=1024)
    with pytest.raises(ReleaseUnavailable) as caught:
        repo.load_windows_installer()
    assert "尚未发布" in caught.value.message
    assert str(tmp_path) not in caught.value.message
    assert caught.value.internal


def test_rejects_traversal_filename(tmp_path: Path) -> None:
    repo = FilesystemReleaseRepository(tmp_path, "../secret.exe", max_bytes=1024)
    with pytest.raises(ReleaseUnavailable) as caught:
        repo.load_windows_installer()
    assert "配置无效" in caught.value.message
    assert str(tmp_path) not in caught.value.message


def test_serves_real_file(tmp_path: Path) -> None:
    target = tmp_path / "Nexora-Setup.exe"
    target.write_bytes(b"MZ-fake-installer")
    repo = FilesystemReleaseRepository(tmp_path, "Nexora-Setup.exe", max_bytes=1024)
    package = repo.load_windows_installer()
    assert package.filename == "Nexora-Setup.exe"
    assert package.size_bytes == len(b"MZ-fake-installer")
    assert package.path.resolve() == target.resolve()


def test_rejects_empty_and_oversize(tmp_path: Path) -> None:
    empty = tmp_path / "Nexora-Setup.exe"
    empty.write_bytes(b"")
    repo = FilesystemReleaseRepository(tmp_path, "Nexora-Setup.exe", max_bytes=4)
    with pytest.raises(ReleaseUnavailable):
        repo.load_windows_installer()

    empty.write_bytes(b"12345")
    with pytest.raises(ReleaseUnavailable) as caught:
        repo.load_windows_installer()
    assert "不可用" in caught.value.message
    assert "12345" not in caught.value.message


def test_symlink_outside_release_dir_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "secret.exe"
    outside.write_bytes(b"MZ")
    folder = tmp_path / "releases"
    folder.mkdir()
    link = folder / "Nexora-Setup.exe"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("当前环境不能创建符号链接")
    repo = FilesystemReleaseRepository(folder, "Nexora-Setup.exe", max_bytes=1024)
    with pytest.raises(ReleaseUnavailable):
        repo.load_windows_installer()


def test_disabled_service_does_not_require_file(tmp_path: Path) -> None:
    repo = FilesystemReleaseRepository(tmp_path, "Nexora-Setup.exe", max_bytes=1024)
    service = DesktopReleaseService(repo, enabled=False)
    meta = service.metadata()
    assert meta.available is False
    assert meta.detail == "未开放下载"
    with pytest.raises(ReleaseUnavailable):
        service.require_package()
