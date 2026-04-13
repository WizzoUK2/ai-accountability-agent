"""Entity matcher for the Accountability Agent.

Loads entities.yaml (shared with the twin vault) and provides
entity matching for emails, tasks, and calendar events based on
account email, sender domain, or project/client name.
"""

import logging
from pathlib import Path
from functools import lru_cache

import yaml

from config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_entities() -> list[dict]:
    """Load entities from YAML file."""
    path = settings.entities_yaml_path
    if not path:
        logger.info("No entities_yaml_path configured — entity matching disabled")
        return []
    yaml_path = Path(path)
    if not yaml_path.exists():
        logger.warning("entities.yaml not found at %s", yaml_path)
        return []
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    entities = data.get("entities", [])
    logger.info("Loaded %d entities from %s", len(entities), yaml_path)
    return entities


@lru_cache(maxsize=1)
def _build_lookup() -> dict[str, str]:
    """Build a lookup dict mapping domains and accounts to entity names."""
    entities = _load_entities()
    lookup = {}
    for e in entities:
        name = e.get("name", "")
        if not name:
            continue
        for domain in e.get("domains", []):
            lookup[domain.lower()] = name
        for account in e.get("accounts", []):
            lookup[account.lower()] = name
    return lookup


def match_entity(
    account_email: str | None = None,
    sender_email: str | None = None,
    project_name: str | None = None,
) -> str | None:
    """Match to an entity name by account, sender domain, or project name.

    Returns the entity name string or None.
    """
    lookup = _build_lookup()
    if not lookup and not _load_entities():
        return None

    # Match by account email (e.g. which Google account this came from)
    if account_email:
        account_lower = account_email.lower()
        if account_lower in lookup:
            return lookup[account_lower]
        if "@" in account_lower:
            domain = account_lower.split("@", 1)[1]
            if domain in lookup:
                return lookup[domain]

    # Match by sender email domain (e.g. inbound email from sarah@modiphius.net)
    if sender_email:
        sender_lower = sender_email.lower()
        if "@" in sender_lower:
            domain = sender_lower.split("@", 1)[1]
            if domain in lookup:
                return lookup[domain]

    # Fuzzy match by project/client name
    if project_name:
        project_lower = project_name.lower().strip()
        for e in _load_entities():
            entity_name = e.get("name", "").lower()
            if entity_name and (entity_name in project_lower or project_lower in entity_name):
                return e.get("name")

    return None
