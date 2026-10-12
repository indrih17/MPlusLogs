"""Keep publisher Git metadata outside the WoW installation."""
import os
from pathlib import Path


def build_tools_dir(source_root, environment=None):
    environment = os.environ if environment is None else environment
    override = environment.get("MPLUSLOGS_DEVELOPMENT_HOME")
    base = Path(override) if override else Path(environment.get("LOCALAPPDATA") or Path.home()/".cache")/"MPlusLogsDevelopment"
    destination = (base / "build-tools").resolve()
    source_root = Path(source_root).resolve()
    game_root = next((parent.parent for parent in source_root.parents if parent.name.casefold() == "_retail_"), None)
    if destination.is_relative_to(source_root) or (game_root and destination.is_relative_to(game_root)):
        raise ValueError("Publishing Git metadata must be outside the WoW installation")
    return destination
