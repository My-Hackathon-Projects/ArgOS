"""Load pipeline prompts from a YAML config file.

Expected layout:

    preamble: |
      Shared text prepended to every prompt.
    prompts:
      node_name: |
        Prompt body for that node.
"""

from pathlib import Path

import yaml


def load_prompts(path: Path) -> dict[str, str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "prompts" not in data:
        raise ValueError(f"{path}: expected a mapping with a 'prompts' key")

    preamble = (data.get("preamble") or "").strip()
    prompts: dict[str, str] = {}
    for name, body in data["prompts"].items():
        body = str(body).strip()
        prompts[name] = f"{preamble}\n\n{body}" if preamble else body
    return prompts
