"""Application state management."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from deeptrace.db import CaseDatabase

# Allow Azure Web App to override cases directory via environment variable
_cases_dir_env = os.environ.get("DEEPTRACE_CASES_DIR")
CASES_DIR = Path(_cases_dir_env) if _cases_dir_env else Path.home() / ".deeptrace" / "cases"


def slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


@dataclass
class AppState:
    cases_dir: Path = field(default_factory=lambda: CASES_DIR)
    active_case_slug: str | None = None
    db: CaseDatabase | None = None

    @property
    def active_case_dir(self) -> Path:
        if not self.active_case_slug:
            raise RuntimeError("No case is open.")
        return self.cases_dir / self.active_case_slug

    def ensure_cases_dir(self) -> None:
        self.cases_dir.mkdir(parents=True, exist_ok=True)

    def create_case(self, name: str) -> str:
        self.ensure_cases_dir()
        slug = slugify(name)
        case_dir = self.cases_dir / slug
        if case_dir.exists():
            raise FileExistsError(f"Case '{slug}' already exists.")
        case_dir.mkdir(parents=True)
        db = CaseDatabase(case_dir / "case.db")
        db.open()
        db.initialize_schema()
        db.close()
        return slug

    def open_case(self, slug: str) -> None:
        case_dir = self.cases_dir / slug
        if not case_dir.exists():
            raise FileNotFoundError(f"Case '{slug}' not found.")
        self.active_case_slug = slug
        self.db = CaseDatabase(case_dir / "case.db")
        self.db.open()
        self.db.maybe_migrate(case_dir)

    def close_case(self) -> None:
        if self.db:
            self.db.close()
        self.db = None
        self.active_case_slug = None

    def list_cases(self) -> list[str]:
        self.ensure_cases_dir()
        return sorted(
            d.name
            for d in self.cases_dir.iterdir()
            if d.is_dir() and (d / "case.db").exists()
        )
