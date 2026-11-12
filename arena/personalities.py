"""The personalities of config/personalities: who a model seat may play."""

import json
from pathlib import Path

import yaml
from jsonschema import ValidationError, validate
from pydantic import BaseModel

from arena.config import CONFIG_PATH

PERSONALITIES_DIR = CONFIG_PATH.parent / "personalities"


class Personality(BaseModel):
    id: str
    name: str
    description: str
    speech_style: str = ""


def load_personalities(directory: Path = PERSONALITIES_DIR) -> list[Personality]:
    """Every personality file, checked against its schema, in file-name order."""
    schema = json.loads((directory / "personality.schema.json").read_text(encoding="utf-8"))
    personalities = []
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            validate(data, schema)
        except ValidationError as error:
            raise ValueError(f"{path.name}: {error.message}") from None
        if data["id"] != path.stem:
            raise ValueError(f"{path.name}: id {data['id']!r} must match the file name")
        personalities.append(
            Personality(
                id=data["id"],
                name=data["name"],
                description=data["description"].strip(),
                speech_style=data["speech_style"].strip(),
            )
        )
    return personalities
