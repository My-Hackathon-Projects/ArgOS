"""Validation (processing) pipeline prompts — loaded from prompts.yaml (README §8)."""

from pathlib import Path

from app.service.prompt_loader import load_prompts

_PROMPTS = load_prompts(Path(__file__).resolve().parents[1] / "prompts.yaml")

FOUNDER_AXIS_PROMPT = _PROMPTS["founder_axis"]
MARKET_AXIS_PROMPT = _PROMPTS["market_axis"]
IDEA_VS_MARKET_AXIS_PROMPT = _PROMPTS["idea_vs_market_axis"]
VALIDATOR_PROMPT = _PROMPTS["validator"]
MEMO_WRITER_PROMPT = _PROMPTS["memo_writer"]
