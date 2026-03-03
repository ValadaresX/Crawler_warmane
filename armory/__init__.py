"""Armory — Warmane character analysis library."""

from pathlib import Path

from .analyzer import analyze_character

__version__: str = (Path(__file__).resolve().parents[1] / "VERSION").read_text().strip()

__all__ = ["analyze_character", "__version__"]
