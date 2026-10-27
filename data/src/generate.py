import json
from pathlib import Path


def generate_enums():
    path = Path("schemas.json")
    if not path.exists():
        raise FileNotFoundError("Schema file not found: " + str(path))
    config = json.loads(path.read_text())

    categories = "\n    ".join(
        f"{value} = '{value}'" for value in config["DeviceCategories"]
    )

    enum_code = f"""# Auto-generated file. Do not edit manually.
from enum import StrEnum

class DeviceCategories(StrEnum):
    {categories}

"""

    Path("./src/generated/").mkdir(exist_ok=True)
    Path("src/generated/generated_enums.py").write_text(enum_code)
