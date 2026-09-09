"""Comprehensive tests for computer_use.file skills."""

from __future__ import annotations

from pathlib import Path

import pytest

from effero.skills.computer_use.file_ops import delete_file, list_dir, read_file, write_file


@pytest.mark.asyncio
async def test_file_read_write_lifecycle(tmp_path: Path) -> None:
    """Verify write, read, and append operations on files."""
    test_file = tmp_path / "sub" / "test.txt"
    content = "Hello, Effero embodied agent runtime!"

    # Write file
    write_res = await write_file(str(test_file), content)
    assert write_res["status"] == "success"
    assert test_file.exists()

    # Read file
    read_res = await read_file(str(test_file))
    assert read_res["status"] == "success"
    assert read_res["content"] == content


@pytest.mark.asyncio
async def test_file_read_nonexistent(tmp_path: Path) -> None:
    """Verify read error on non-existent file."""
    res = await read_file(str(tmp_path / "does_not_exist.txt"))
    assert res["status"] == "error"
    assert "No such file" in res["error"] or "does_not_exist" in res["error"]


@pytest.mark.asyncio
async def test_file_read_max_bytes_limit(tmp_path: Path) -> None:
    """Verify safety limit on maximum read bytes."""
    test_file = tmp_path / "large.txt"
    test_file.write_text("A" * 500, encoding="utf-8")

    res = await read_file(str(test_file), max_bytes=100)
    assert res["status"] == "error"
    assert "exceeds safety limit" in res["error"]


@pytest.mark.asyncio
async def test_file_list_dir(tmp_path: Path) -> None:
    """Verify list_dir returns items in directory."""
    (tmp_path / "file1.txt").write_text("1")
    (tmp_path / "file2.txt").write_text("2")
    (tmp_path / "folder").mkdir()

    res = await list_dir(str(tmp_path))
    assert res["status"] == "success"
    assert set(res["items"]) >= {"file1.txt", "file2.txt", "folder"}


@pytest.mark.asyncio
async def test_file_delete_single_file(tmp_path: Path) -> None:
    """Verify deleting a single file."""
    test_file = tmp_path / "to_delete.txt"
    test_file.write_text("delete me")

    del_res = await delete_file(str(test_file))
    assert del_res["status"] == "success"
    assert not test_file.exists()


@pytest.mark.asyncio
async def test_file_delete_nonexistent(tmp_path: Path) -> None:
    """Verify delete on non-existent path returns error."""
    del_res = await delete_file(str(tmp_path / "missing.txt"))
    assert del_res["status"] == "error"
    assert "does not exist" in del_res["error"]


@pytest.mark.asyncio
async def test_file_delete_directory_safety(tmp_path: Path) -> None:
    """Verify deleting directory fails without recursive=True, and succeeds with it."""
    dir_to_delete = tmp_path / "nested_dir"
    dir_to_delete.mkdir()
    (dir_to_delete / "child.txt").write_text("child")

    # Non-recursive should fail for safety
    safe_res = await delete_file(str(dir_to_delete), recursive=False)
    assert safe_res["status"] == "error"
    assert "recursive=True" in safe_res["error"]
    assert dir_to_delete.exists()

    # Recursive should succeed
    rec_res = await delete_file(str(dir_to_delete), recursive=True)
    assert rec_res["status"] == "success"
    assert not dir_to_delete.exists()
