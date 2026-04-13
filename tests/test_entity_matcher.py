"""Tests for entity matching."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from src.services.entity_matcher import match_entity, _load_entities, _build_lookup


SAMPLE_YAML = """
entities:
  - name: Wicked Sick
    role: owner
    priority_tier: 1
    active: true
    accounts:
      - craig@wickedsick.com
    domains:
      - wickedsick.com

  - name: FUTWIZ
    role: chairman
    priority_tier: 2
    active: true
    accounts:
      - craig@futwiz.com
    domains:
      - futwiz.com

  - name: Modiphius
    role: advisor
    priority_tier: 3
    active: true
    accounts: []
    domains:
      - modiphius.net
      - modiphius.com
"""


def _with_entities(fn):
    """Run a test function with a temporary entities.yaml loaded."""
    def wrapper():
        # Clear caches
        _load_entities.cache_clear()
        _build_lookup.cache_clear()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(SAMPLE_YAML)
            f.flush()
            with patch("src.services.entity_matcher.settings") as mock_settings:
                mock_settings.entities_yaml_path = f.name
                fn()

        # Clear caches after test
        _load_entities.cache_clear()
        _build_lookup.cache_clear()
    return wrapper


@_with_entities
def test_match_by_account_email():
    assert match_entity(account_email="craig@wickedsick.com") == "Wicked Sick"
    assert match_entity(account_email="craig@futwiz.com") == "FUTWIZ"


@_with_entities
def test_match_by_account_email_case_insensitive():
    assert match_entity(account_email="Craig@WickedSick.com") == "Wicked Sick"


@_with_entities
def test_match_by_sender_domain():
    assert match_entity(sender_email="sarah@modiphius.net") == "Modiphius"
    assert match_entity(sender_email="anyone@modiphius.com") == "Modiphius"
    assert match_entity(sender_email="dan@futwiz.com") == "FUTWIZ"


@_with_entities
def test_match_by_project_name():
    assert match_entity(project_name="Wicked Sick") == "Wicked Sick"
    assert match_entity(project_name="FUTWIZ") == "FUTWIZ"
    assert match_entity(project_name="futwiz board prep") == "FUTWIZ"


@_with_entities
def test_no_match():
    assert match_entity(sender_email="random@gmail.com") is None
    assert match_entity(project_name="Unknown Project") is None
    assert match_entity(account_email="someone@example.com") is None


@_with_entities
def test_priority_account_over_sender():
    # Account email takes precedence
    result = match_entity(
        account_email="craig@wickedsick.com",
        sender_email="sarah@modiphius.net",
    )
    assert result == "Wicked Sick"


def test_no_config_returns_none():
    """When entities_yaml_path is empty, all matching returns None."""
    _load_entities.cache_clear()
    _build_lookup.cache_clear()
    with patch("src.services.entity_matcher.settings") as mock_settings:
        mock_settings.entities_yaml_path = ""
        assert match_entity(sender_email="sarah@modiphius.net") is None
    _load_entities.cache_clear()
    _build_lookup.cache_clear()


def test_missing_file_returns_none():
    """When the file doesn't exist, matching returns None gracefully."""
    _load_entities.cache_clear()
    _build_lookup.cache_clear()
    with patch("src.services.entity_matcher.settings") as mock_settings:
        mock_settings.entities_yaml_path = "/nonexistent/entities.yaml"
        assert match_entity(sender_email="sarah@modiphius.net") is None
    _load_entities.cache_clear()
    _build_lookup.cache_clear()
