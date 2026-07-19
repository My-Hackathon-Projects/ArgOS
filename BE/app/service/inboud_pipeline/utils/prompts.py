"""Inbound pipeline prompts — loaded from prompts.yaml (README §8)."""

from pathlib import Path

from app.service.prompt_loader import load_prompts

_PROMPTS = load_prompts(Path(__file__).resolve().parents[1] / "prompts.yaml")

EXTRACT_CLAIMS_PROMPT = _PROMPTS["extract_claims"]
PRE_SCREEN_PROMPT = _PROMPTS["pre_screen"]
