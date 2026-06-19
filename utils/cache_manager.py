import json
import os
from typing import Any


def ensure_data_folder_exists() -> None:
    os.makedirs("docs", exist_ok=True)


def save_json(file_path: str, data: Any) -> None:
    ensure_data_folder_exists()

    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def load_json(file_path: str) -> Any:
    if not os.path.exists(file_path):
        return None

    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def cache_exists(file_path: str) -> bool:
    return os.path.exists(file_path)
