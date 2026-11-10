"""Tests for config defaults and .gitignore handling."""

import pytest

from azdo_daily import config


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / ".config")
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / ".config" / "settings.json")
    return tmp_path


def test_default_cfg_has_repo_and_target_branch():
    assert config.DEFAULT_CFG["repo"] == ""
    assert config.DEFAULT_CFG["target_branch"] == "main"


def test_gitignore_created_in_git_repo(project):
    (project / ".git").mkdir()
    config.save_cfg({})
    assert ".config/" in (project / ".gitignore").read_text()


def test_gitignore_appended_when_exists(project):
    (project / ".git").mkdir()
    (project / ".gitignore").write_text("node_modules/\n")
    config.save_cfg({})
    lines = (project / ".gitignore").read_text().splitlines()
    assert "node_modules/" in lines
    assert ".config/" in lines


def test_gitignore_not_created_outside_git_repo(project):
    config.save_cfg({})
    assert not (project / ".gitignore").exists()
