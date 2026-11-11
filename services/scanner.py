from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from repositories.catalog_repo import CatalogRepo, ScriptRecord

logger = logging.getLogger(__name__)

DEFAULT_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


@dataclass
class ScanSummary:
    total_found: int = 0
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)


class ScriptScanner:
    def __init__(
        self,
        scripts_dir: Path | str | None = None,
        repo: CatalogRepo | None = None,
    ) -> None:
        if scripts_dir is None:
            self.scripts_dir = DEFAULT_SCRIPTS_DIR
        else:
            self.scripts_dir = Path(scripts_dir)

        self.repo = repo if repo is not None else CatalogRepo()

    @staticmethod
    def derive_category(folder_name: str) -> str:
        """Derives human-readable category name from folder (e.g. 04_Printers_Devices -> Printers_Devices)."""
        clean = re.sub(r"^\d+_", "", folder_name)
        return clean.strip() or folder_name

    @staticmethod
    def compute_sha256(file_path: Path) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def parse_psstore_meta(content: str) -> tuple[dict[str, Any], str]:
        """
        Parses .PSSTORE_META JSON and .SYNOPSIS from PowerShell comment block (<# ... #>).
        Returns (meta_dict, synopsis_str).
        """
        synopsis = ""
        meta: dict[str, Any] = {}

        # Find help comment blocks <# ... #>
        comment_blocks = re.findall(r"<#\s*(.*?)\s*#>", content, re.DOTALL)
        if not comment_blocks:
            return meta, synopsis

        for block in comment_blocks:
            # Extract .SYNOPSIS if not already found
            if not synopsis:
                syn_match = re.search(
                    r"\.SYNOPSIS\s*\r?\n(.*?)(?=\r?\n\.[A-Z_]+|\Z)",
                    block,
                    re.IGNORECASE | re.DOTALL,
                )
                if syn_match:
                    synopsis = syn_match.group(1).strip()

            # Extract .PSSTORE_META
            meta_match = re.search(
                r"\.PSSTORE_META\s*\r?\n(.*?)(?=\r?\n\.[A-Z_]+|\Z)",
                block,
                re.IGNORECASE | re.DOTALL,
            )
            if meta_match:
                raw_json = meta_match.group(1).strip()
                # Find start of JSON object '{' and matching end '}'
                first_brace = raw_json.find("{")
                last_brace = raw_json.rfind("}")
                if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                    json_str = raw_json[first_brace : last_brace + 1]
                    try:
                        meta = json.loads(json_str)
                    except json.JSONDecodeError:
                        # Attempt common json fixups: trailing commas, single quotes
                        cleaned = re.sub(r",\s*([\]}])", r"\1", json_str)
                        cleaned = re.sub(r"'([^']*)'", r'"\1"', cleaned)
                        try:
                            meta = json.loads(cleaned)
                        except Exception as e:
                            logger.warning("Failed to parse .PSSTORE_META JSON: %s", e)

        return meta, synopsis

    def scan_file(self, file_path: Path) -> ScriptRecord:
        """Parses a single .ps1 file and returns a ScriptRecord."""
        relative_path = file_path.relative_to(self.scripts_dir).as_posix()
        folder_category = self.derive_category(file_path.parent.name)

        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = file_path.read_text(encoding="utf-8-sig", errors="replace")

        sha256 = self.compute_sha256(file_path)
        meta, synopsis = self.parse_psstore_meta(content)

        category = meta.get("category", folder_category)
        title = meta.get("title", file_path.stem)
        risk_level = meta.get("risk_level", "read_only")
        ps_edition = meta.get("ps_edition", "Desktop")
        requires_admin = bool(meta.get("requires_admin", False))
        timeout_seconds = int(meta.get("timeout_seconds", 30))
        output_mode = meta.get("output_mode", "json")
        params = meta.get("params", [])

        if not isinstance(params, list):
            params = []

        return ScriptRecord(
            relative_path=relative_path,
            category=category,
            filename=file_path.name,
            title=title,
            synopsis=synopsis,
            risk_level=risk_level,
            ps_edition=ps_edition,
            requires_admin=requires_admin,
            timeout_seconds=timeout_seconds,
            output_mode=output_mode,
            params=params,
            sha256=sha256,
        )

    def sync_catalog(self) -> ScanSummary:
        """
        Scans all .ps1 files in scripts_dir, compares hashes with the DB,
        and synchronizes scripts into SQLite.
        """
        summary = ScanSummary()

        if not self.scripts_dir.exists():
            self.scripts_dir.mkdir(parents=True, exist_ok=True)
            return summary

        found_paths: list[str] = []

        for ps1_file in self.scripts_dir.rglob("*.ps1"):
            summary.total_found += 1
            rel_path = ps1_file.relative_to(self.scripts_dir).as_posix()
            found_paths.append(rel_path)

            try:
                current_sha = self.compute_sha256(ps1_file)
                existing = self.repo.get_script_by_path(rel_path)

                if existing and existing.sha256 == current_sha:
                    summary.unchanged += 1
                    continue

                record = self.scan_file(ps1_file)
                self.repo.upsert_script(record)

                if existing:
                    summary.updated += 1
                else:
                    summary.added += 1

            except Exception as e:
                logger.exception("Error processing script %s", rel_path)
                summary.errors.append((rel_path, str(e)))

        # Clean up scripts that were removed from disk
        deleted_count = self.repo.delete_missing_scripts(found_paths)
        summary.deleted = deleted_count

        return summary
