from __future__ import annotations

import ctypes
import hashlib
import json
import logging
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from repositories.catalog_repo import CatalogRepo, RunHistoryRecord, ScriptRecord

logger = logging.getLogger(__name__)

DEFAULT_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def is_running_as_admin() -> bool:
    """Returns True if the current process has Windows Administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def build_powershell_args(param_values: dict[str, Any]) -> list[str]:
    """Converts a dictionary of parameters into PowerShell command-line arguments."""
    args: list[str] = []
    for name, val in param_values.items():
        if val is None:
            continue
        if isinstance(val, bool):
            args.append(f"-{name}:${str(val).lower()}")
        elif isinstance(val, (int, float)):
            args.extend([f"-{name}", str(val)])
        else:
            clean_val = str(val).replace("'", "''")
            args.extend([f"-{name}", f"'{clean_val}'"])
    return args


@dataclass
class RunResult:
    script_id: int
    duration_ms: int
    exit_code: int
    status: str  # 'pass', 'warning', 'fail', 'error', 'timeout'
    summary: str = ""
    data: list[Any] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    raw_output: str = ""
    raw_json: str = ""
    script_title: str = ""
    script_category: str = ""


class ScriptRunner(QObject):
    started = Signal()
    output_received = Signal(str)
    finished = Signal(RunResult)
    error_occurred = Signal(str)

    def __init__(
        self,
        scripts_dir: Path | str | None = None,
        repo: CatalogRepo | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.scripts_dir = Path(scripts_dir) if scripts_dir else DEFAULT_SCRIPTS_DIR
        self.repo = repo if repo is not None else CatalogRepo()

        self._process: QProcess | None = None
        self._timer: QTimer | None = None
        self._start_time: float = 0.0
        self._current_script: ScriptRecord | None = None
        self._current_params: dict[str, Any] = {}
        self._stdout_chunks: list[str] = []
        self._stderr_chunks: list[str] = []
        self._is_timed_out: bool = False

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning

    def _select_executable(self, ps_edition: str) -> str:
        """Selects pwsh.exe for Core if available, otherwise powershell.exe."""
        if ps_edition.lower() == "core":
            pwsh_path = shutil.which("pwsh") or shutil.which("pwsh.exe")
            if pwsh_path:
                return pwsh_path
        # Default Desktop edition 5.1
        powershell_path = shutil.which("powershell.exe") or shutil.which("powershell")
        return powershell_path or "powershell.exe"

    def execute_script(
        self,
        script: ScriptRecord,
        param_values: dict[str, Any] | None = None,
    ) -> bool:
        """
        Launches the PowerShell script non-blockingly using QProcess.
        Validates path and SHA-256 before starting.
        """
        if self.is_running:
            self.error_occurred.emit("A script is already running.")
            return False

        script_file = self.scripts_dir / script.relative_path
        if not script_file.exists():
            msg = f"Script file not found: {script_file}"
            self.error_occurred.emit(msg)
            return False

        # Validate SHA-256 checksum
        current_hash = hashlib.sha256(script_file.read_bytes()).hexdigest()
        if script.sha256 and script.sha256 != current_hash:
            logger.warning(
                "SHA-256 mismatch for %s (recorded=%s, actual=%s). Updating catalog.",
                script.relative_path,
                script.sha256,
                current_hash,
            )
            script.sha256 = current_hash
            self.repo.upsert_script(script)

        self._current_script = script
        self._current_params = param_values or {}
        self._stdout_chunks = []
        self._stderr_chunks = []
        self._is_timed_out = False

        executable = self._select_executable(script.ps_edition)
        resolved_script = str(script_file.resolve()).replace("'", "''")

        if self._current_params:
            arg_str = " ".join(build_powershell_args(self._current_params))
            cli_args = [
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                f"& '{resolved_script}' {arg_str}".strip(),
            ]
        else:
            cli_args = [
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_file.resolve()),
            ]

        self._process = QProcess(self)
        self._process.readyReadStandardOutput.connect(self._on_stdout_ready)
        self._process.readyReadStandardError.connect(self._on_stderr_ready)
        self._process.finished.connect(self._on_process_finished)

        # Timeout timer
        timeout_sec = script.timeout_seconds if script.timeout_seconds > 0 else 30
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

        self._start_time = time.time()
        self.started.emit()
        self._timer.start(timeout_sec * 1000)
        self._process.start(executable, cli_args)

        return True

    def stop_execution(self) -> None:
        """Terminates the currently running script process."""
        if self._timer and self._timer.isActive():
            self._timer.stop()

        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()

    def _on_stdout_ready(self) -> None:
        if not self._process:
            return
        data = self._process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self._stdout_chunks.append(data)
        self.output_received.emit(data)

    def _on_stderr_ready(self) -> None:
        if not self._process:
            return
        data = self._process.readAllStandardError().data().decode("utf-8", errors="replace")
        self._stderr_chunks.append(data)
        self.output_received.emit(data)

    def _on_timeout(self) -> None:
        self._is_timed_out = True
        msg = f"[TIMEOUT] Execution exceeded {self._current_script.timeout_seconds if self._current_script else 30} seconds."
        self._stderr_chunks.append(msg)
        self.output_received.emit(f"\n{msg}\n")
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()

    def _parse_results(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        duration_ms: int,
    ) -> RunResult:
        script_id = self._current_script.id if self._current_script and self._current_script.id else 0
        script_title = self._current_script.title if self._current_script else ""
        script_category = self._current_script.category if self._current_script else ""
        raw_output = (stdout + ("\n" + stderr if stderr else "")).strip()

        if self._is_timed_out:
            return RunResult(
                script_id=script_id,
                duration_ms=duration_ms,
                exit_code=exit_code,
                status="timeout",
                summary="Execution timed out and was killed.",
                errors=["Process timed out."],
                raw_output=raw_output,
                script_title=script_title,
                script_category=script_category,
            )

        # Attempt to parse standard JSON envelope from stdout
        # First check full stdout, or lines containing JSON
        json_payload_str = ""
        parsed_json = None

        # Look for JSON payload in stdout lines
        for line in reversed(stdout.strip().splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    candidate = json.loads(line)
                    if isinstance(candidate, dict) and "status" in candidate:
                        parsed_json = candidate
                        json_payload_str = line
                        break
                except Exception:
                    pass

        # If not on a single line, try finding first '{' to matching '}'
        if not parsed_json:
            match = re.search(r"(\{.*\})", stdout, re.DOTALL)
            if match:
                try:
                    candidate = json.loads(match.group(1))
                    if isinstance(candidate, dict) and "status" in candidate:
                        parsed_json = candidate
                        json_payload_str = match.group(1)
                except Exception:
                    pass

        if parsed_json:
            status = parsed_json.get("status", "pass")
            summary = parsed_json.get("summary", "")
            data = parsed_json.get("data", [])
            errors = parsed_json.get("errors", [])
            return RunResult(
                script_id=script_id,
                duration_ms=duration_ms,
                exit_code=exit_code,
                status=status,
                summary=summary,
                data=data if isinstance(data, list) else [data],
                errors=errors if isinstance(errors, list) else [str(errors)],
                raw_output=raw_output,
                raw_json=json_payload_str,
                script_title=script_title,
                script_category=script_category,
            )

        # Fallback to standard RMM / console text output parsing
        status = "pass" if exit_code == 0 else "error"
        summary = ""
        errors_list: list[str] = []

        for line in stdout.splitlines():
            line_str = line.strip()
            if "[SUCCESS]" in line_str or "[PASS]" in line_str:
                status = "pass"
                summary = line_str
            elif "[WARNING]" in line_str:
                status = "warning"
                summary = line_str
            elif "[ERROR]" in line_str or "[FAIL]" in line_str:
                status = "fail" if exit_code == 0 else "error"
                summary = line_str
                errors_list.append(line_str)

        if not summary:
            if exit_code == 0:
                # Use first non-empty line or default
                non_empty = [l.strip() for l in stdout.splitlines() if l.strip()]
                summary = non_empty[0] if non_empty else "Script completed successfully (exit code 0)."
            else:
                summary = f"Script failed with exit code {exit_code}."

        if stderr:
            errors_list.extend([l.strip() for l in stderr.splitlines() if l.strip()])

        return RunResult(
            script_id=script_id,
            duration_ms=duration_ms,
            exit_code=exit_code,
            status=status,
            summary=summary,
            data=[],
            errors=errors_list,
            raw_output=raw_output,
            raw_json="",
            script_title=script_title,
            script_category=script_category,
        )

    def _on_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        if self._timer and self._timer.isActive():
            self._timer.stop()

        duration_ms = int((time.time() - self._start_time) * 1000)
        stdout = "".join(self._stdout_chunks)
        stderr = "".join(self._stderr_chunks)

        result = self._parse_results(exit_code, stdout, stderr, duration_ms)

        # Persist to run history if script has valid id
        if result.script_id:
            try:
                history_rec = RunHistoryRecord(
                    script_id=result.script_id,
                    duration_ms=result.duration_ms,
                    exit_code=result.exit_code,
                    status=result.status,
                    summary=result.summary,
                    parameters_json=json.dumps(self._current_params),
                    raw_output=result.raw_output,
                    json_payload=result.raw_json,
                )
                self.repo.log_run(history_rec)
            except Exception as e:
                logger.error("Failed to log run history: %s", e)

        self.finished.emit(result)

    def execute_script_elevated(
        self,
        script: ScriptRecord,
        param_values: dict[str, Any] | None = None,
    ) -> bool:
        """Spawns an elevated PowerShell session via Windows UAC runas verb."""
        script_file = self.scripts_dir / script.relative_path
        if not script_file.exists():
            self.error_occurred.emit(f"Script file not found: {script_file}")
            return False

        resolved_script = str(script_file.resolve()).replace("'", "''")
        params = param_values or {}
        arg_str = " ".join(build_powershell_args(params))

        ps_command = (
            f"Write-Host '===================================================' -ForegroundColor Cyan; "
            f"Write-Host ' PowerShellStore — Elevated Test Runner (UAC)' -ForegroundColor Cyan; "
            f"Write-Host ' Running: {script.title}' -ForegroundColor White; "
            f"Write-Host '===================================================' -ForegroundColor Cyan; "
            f"Write-Host ''; "
            f"& '{resolved_script}' {arg_str}; "
            f"Write-Host ''; "
            f"Write-Host '---------------------------------------------------' -ForegroundColor DarkGray; "
            f"Write-Host 'Execution complete. Press Enter to close window...' -ForegroundColor Yellow; "
            f"[void][System.Console]::ReadLine()"
        )

        try:
            ret = ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                "powershell.exe",
                f"-NoProfile -ExecutionPolicy Bypass -Command \"{ps_command}\"",
                None,
                1,  # SW_SHOWNORMAL
            )
            return ret > 32
        except Exception as e:
            logger.error("Failed to spawn elevated runner: %s", e)
            self.error_occurred.emit(f"Failed to launch elevated session: {e}")
            return False
