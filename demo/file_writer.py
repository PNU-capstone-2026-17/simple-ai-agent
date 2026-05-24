from pathlib import Path
from typing import Dict


def write_generated_files(output_dir: str, files: Dict[str, str]) -> None:
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)

    for relative_path, content in files.items():
        target = base / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")