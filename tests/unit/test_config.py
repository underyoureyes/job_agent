"""
tests/unit/test_config.py
=========================
Unit tests for config.py — Config dataclass, env loading, and validation.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch


from config import Config


# ── Instantiation ──────────────────────────────────────────────────────────────

class TestConfigDefaults:

    def test_default_candidate_name_fallback(self, tmp_path):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CANDIDATE_NAME", None)
            cfg = Config()
            cfg.output_dir = tmp_path / "output"
            cfg.logs_dir = tmp_path / "logs"
            cfg.output_dir.mkdir()
            cfg.logs_dir.mkdir()
            assert cfg.candidate_name == "YOUR_NAME"

    def test_env_candidate_name_loaded(self, tmp_path):
        with patch.dict(os.environ, {"CANDIDATE_NAME": "Alice Test"}):
            cfg = Config()
            cfg.output_dir = tmp_path / "output"
            cfg.logs_dir = tmp_path / "logs"
            cfg.output_dir.mkdir()
            cfg.logs_dir.mkdir()
            assert cfg.candidate_name == "Alice Test"

    def test_default_search_keywords_non_empty(self, tmp_path):
        cfg = Config()
        cfg.output_dir = tmp_path / "output"
        cfg.logs_dir = tmp_path / "logs"
        cfg.output_dir.mkdir()
        cfg.logs_dir.mkdir()
        assert len(cfg.search_keywords) > 0
        assert all(isinstance(k, str) for k in cfg.search_keywords)

    def test_seniority_filter_titles_non_empty(self, tmp_path):
        cfg = Config()
        cfg.output_dir = tmp_path / "output"
        cfg.logs_dir = tmp_path / "logs"
        cfg.output_dir.mkdir()
        cfg.logs_dir.mkdir()
        assert len(cfg.seniority_filter_titles) > 0

    def test_seniority_filter_experience_non_empty(self, tmp_path):
        cfg = Config()
        cfg.output_dir = tmp_path / "output"
        cfg.logs_dir = tmp_path / "logs"
        cfg.output_dir.mkdir()
        cfg.logs_dir.mkdir()
        assert len(cfg.seniority_filter_experience) > 0

    def test_irrelevant_filter_titles_non_empty(self, tmp_path):
        cfg = Config()
        cfg.output_dir = tmp_path / "output"
        cfg.logs_dir = tmp_path / "logs"
        cfg.output_dir.mkdir()
        cfg.logs_dir.mkdir()
        assert len(cfg.irrelevant_filter_titles) > 0

    def test_output_dir_created_on_init(self, tmp_path):
        cfg = Config()
        cfg.output_dir = tmp_path / "output_new"
        cfg.logs_dir = tmp_path / "logs_new"
        cfg.__post_init__()
        assert cfg.output_dir.exists()
        assert cfg.logs_dir.exists()

    def test_min_match_score_default(self, tmp_path):
        cfg = Config()
        cfg.output_dir = tmp_path / "output"
        cfg.logs_dir = tmp_path / "logs"
        cfg.output_dir.mkdir()
        cfg.logs_dir.mkdir()
        assert cfg.min_match_score == 65

    def test_exclude_locations_non_empty(self, tmp_path):
        cfg = Config()
        cfg.output_dir = tmp_path / "output"
        cfg.logs_dir = tmp_path / "logs"
        cfg.output_dir.mkdir()
        cfg.logs_dir.mkdir()
        assert len(cfg.exclude_locations) > 0


# ── Validation ─────────────────────────────────────────────────────────────────

class TestConfigValidate:

    @pytest.fixture
    def cfg(self, tmp_path):
        c = Config(
            candidate_name="Test User",
            anthropic_api_key="sk-ant-real-key",
            reed_api_key="real-reed-key",
            adzuna_app_id="real-adzuna-id",
        )
        c.output_dir = tmp_path / "output"
        c.logs_dir = tmp_path / "logs"
        c.base_cv_path = tmp_path / "base_cv.md"
        c.output_dir.mkdir()
        c.logs_dir.mkdir()
        c.base_cv_path.write_text("# Test CV")
        return c

    def test_validate_no_warnings_when_all_set(self, cfg):
        warnings = cfg.validate()
        assert warnings == []

    def test_validate_warns_missing_anthropic_key(self, cfg):
        cfg.anthropic_api_key = ""
        warnings = cfg.validate()
        assert any("ANTHROPIC_API_KEY" in w for w in warnings)

    def test_validate_warns_missing_reed_key(self, cfg):
        cfg.reed_api_key = ""
        warnings = cfg.validate()
        assert any("REED_API_KEY" in w for w in warnings)

    def test_validate_warns_missing_adzuna_id(self, cfg):
        cfg.adzuna_app_id = ""
        warnings = cfg.validate()
        assert any("ADZUNA" in w for w in warnings)

    def test_validate_warns_default_candidate_name(self, cfg):
        cfg.candidate_name = "YOUR_NAME"
        warnings = cfg.validate()
        assert any("CANDIDATE_NAME" in w for w in warnings)

    def test_validate_warns_missing_base_cv(self, cfg):
        cfg.base_cv_path = cfg.base_cv_path.parent / "nonexistent.md"
        warnings = cfg.validate()
        assert any("base_cv" in w for w in warnings)

    def test_validate_returns_list(self, cfg):
        assert isinstance(cfg.validate(), list)

    def test_validate_multiple_warnings(self, cfg):
        cfg.anthropic_api_key = ""
        cfg.reed_api_key = ""
        cfg.candidate_name = "YOUR_NAME"
        warnings = cfg.validate()
        assert len(warnings) >= 3
