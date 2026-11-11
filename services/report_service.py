from __future__ import annotations

import html
import os
import platform
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QMimeData
from PySide6.QtGui import QGuiApplication

from services.runner import RunResult


class ReportService:
    """Generates rich-text HTML and Markdown audit reports for ticketing systems and exports."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def get_system_audit_info() -> dict[str, str]:
        """Collects environmental audit metadata for technician ticket evidence."""
        hostname = (
            os.environ.get("COMPUTERNAME")
            or platform.node()
            or "UNKNOWN-HOST"
        )
        user = os.environ.get("USERNAME") or "Unknown-Operator"
        os_name = f"{platform.system()} {platform.release()} (Build {platform.version()})"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return {
            "hostname": hostname,
            "operator": user,
            "os_name": os_name,
            "platform": platform.platform(),
            "timestamp": now_str,
        }

    def generate_html_report(
        self,
        script_title: str,
        result: RunResult,
        host_info: dict[str, str] | None = None,
        script_category: str = "",
        standalone: bool = True,
    ) -> str:
        """Builds a rich, self-contained HTML ticket report with audit headers and evidence table."""
        info = host_info or self.get_system_audit_info()
        title_text = script_title or result.script_title or "PowerShell Execution"
        category_text = script_category or result.script_category or "System"

        # Determine status badge styling
        status_key = result.status.lower()
        badge_configs = {
            "pass": {"bg": "#065f46", "fg": "#34d399", "border": "#10b981", "label": "PASS"},
            "warning": {"bg": "#78350f", "fg": "#fbbf24", "border": "#f59e0b", "label": "WARNING"},
            "fail": {"bg": "#7f1d1d", "fg": "#f87171", "border": "#ef4444", "label": "FAIL"},
            "error": {"bg": "#7f1d1d", "fg": "#f87171", "border": "#ef4444", "label": "ERROR"},
            "timeout": {"bg": "#581c87", "fg": "#c084fc", "border": "#a855f7", "label": "TIMEOUT"},
        }
        badge = badge_configs.get(
            status_key,
            {"bg": "#374151", "fg": "#9ca3af", "border": "#6b7280", "label": result.status.upper()},
        )

        escaped_title = html.escape(title_text)
        escaped_category = html.escape(category_text)
        escaped_summary = html.escape(result.summary or "Execution completed.")
        escaped_host = html.escape(info.get("hostname", "UNKNOWN"))
        escaped_os = html.escape(info.get("os_name", "Windows"))
        escaped_op = html.escape(info.get("operator", "Technician"))
        escaped_time = html.escape(info.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        # Build Data Table HTML
        table_html = self._build_html_table(result.data)

        # Build Errors HTML if present
        errors_html = ""
        if result.errors:
            error_items = "".join(f"<li>{html.escape(str(err))}</li>" for err in result.errors)
            errors_html = f"""
            <div style="margin-top: 14px; padding: 12px 14px; background-color: #fef2f2; border-left: 4px solid #ef4444; border-radius: 4px; color: #991b1b; font-family: Consolas, monospace; font-size: 12px;">
                <strong style="display: block; margin-bottom: 6px; font-family: 'Segoe UI', sans-serif;">ERRORS / WARNINGS:</strong>
                <ul style="margin: 0; padding-left: 20px;">
                    {error_items}
                </ul>
            </div>
            """

        body_content = f"""
        <div style="font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif; max-width: 960px; margin: 0 auto; color: #1e293b; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08);">
            <!-- Header with Title and Status Badge -->
            <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 2px solid #3b82f6; padding-bottom: 12px; margin-bottom: 16px;">
                <div>
                    <h2 style="margin: 0; font-size: 20px; color: #0f172a; font-weight: 700;">{escaped_title}</h2>
                    <span style="font-size: 12px; color: #64748b; font-weight: 500;">Category: {escaped_category} &bull; PowerShellStore Workstation</span>
                </div>
                <div>
                    <span style="display: inline-block; background-color: {badge['bg']}; color: {badge['fg']}; border: 1px solid {badge['border']}; padding: 4px 14px; border-radius: 6px; font-weight: 700; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px;">
                        {badge['label']}
                    </span>
                </div>
            </div>

            <!-- Audit Metadata Grid -->
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 16px; font-size: 12px; background-color: #f8fafc; border-radius: 6px; overflow: hidden; border: 1px solid #e2e8f0;">
                <tr>
                    <td style="padding: 8px 12px; font-weight: 600; color: #475569; width: 15%; border-bottom: 1px solid #e2e8f0;">Target Host:</td>
                    <td style="padding: 8px 12px; color: #0f172a; font-family: Consolas, monospace; width: 35%; border-bottom: 1px solid #e2e8f0;">{escaped_host}</td>
                    <td style="padding: 8px 12px; font-weight: 600; color: #475569; width: 15%; border-bottom: 1px solid #e2e8f0;">Execution Time:</td>
                    <td style="padding: 8px 12px; color: #0f172a; width: 35%; border-bottom: 1px solid #e2e8f0;">{escaped_time}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 12px; font-weight: 600; color: #475569;">OS Version:</td>
                    <td style="padding: 8px 12px; color: #0f172a;">{escaped_os}</td>
                    <td style="padding: 8px 12px; font-weight: 600; color: #475569;">Duration / Exit:</td>
                    <td style="padding: 8px 12px; color: #0f172a; font-family: Consolas, monospace;">{result.duration_ms} ms (Exit Code {result.exit_code})</td>
                </tr>
            </table>

            <!-- Summary Box -->
            <div style="background-color: #f1f5f9; border-left: 4px solid {badge['border']}; padding: 12px 14px; border-radius: 4px; margin-bottom: 18px;">
                <strong style="color: #334155; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 4px;">Outcome Summary:</strong>
                <span style="font-size: 13px; color: #0f172a; line-height: 1.4;">{escaped_summary}</span>
            </div>

            <!-- Structured Evidence Table -->
            <div style="margin-top: 14px;">
                <h4 style="margin: 0 0 8px 0; font-size: 13px; text-transform: uppercase; color: #475569; letter-spacing: 0.5px;">Structured Evidence / Collected Data</h4>
                {table_html}
            </div>

            {errors_html}

            <!-- Footer -->
            <div style="margin-top: 20px; pt-3; border-top: 1px solid #e2e8f0; font-size: 11px; color: #94a3b8; display: flex; justify-content: space-between;">
                <span>Verified by PowerShellStore IT Workstation</span>
                <span>Operator: {escaped_op}</span>
            </div>
        </div>
        """

        if not standalone:
            return body_content.strip()

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Execution Report - {escaped_title}</title>
    <style>
        body {{
            background-color: #0f172a;
            padding: 30px 15px;
            margin: 0;
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
        }}
    </style>
</head>
<body>
    {body_content}
</body>
</html>"""

    def _build_html_table(self, data: list[Any]) -> str:
        """Renders an array of flat objects or items into a clean, responsive HTML table."""
        if not data:
            return '<div style="padding: 12px; background-color: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 4px; color: #64748b; font-size: 12px; font-style: italic;">No tabular evidence records returned by script.</div>'

        # Case 1: List of dictionaries (flat objects from PSCustomObject)
        if isinstance(data[0], dict):
            columns = list(data[0].keys())
            header_ths = "".join(
                f'<th style="background-color: #e2e8f0; color: #334155; padding: 8px 10px; font-size: 11px; text-align: left; font-weight: 600; border: 1px solid #cbd5e1;">{html.escape(str(col))}</th>'
                for col in columns
            )
            rows_trs = []
            for idx, row_dict in enumerate(data):
                bg_color = "#ffffff" if idx % 2 == 0 else "#f8fafc"
                tds = "".join(
                    f'<td style="padding: 7px 10px; font-size: 12px; color: #1e293b; border: 1px solid #e2e8f0; font-family: Consolas, monospace;">{html.escape(str(row_dict.get(col, "")))}</td>'
                    for col in columns
                )
                rows_trs.append(f'<tr style="background-color: {bg_color};">{tds}</tr>')

            return f"""
            <div style="overflow-x: auto; max-width: 100%; border: 1px solid #cbd5e1; border-radius: 6px;">
                <table style="width: 100%; border-collapse: collapse; text-align: left;">
                    <thead>
                        <tr>{header_ths}</tr>
                    </thead>
                    <tbody>
                        {"".join(rows_trs)}
                    </tbody>
                </table>
            </div>
            """

        # Case 2: List of primitive values (strings / ints)
        rows_trs = []
        for idx, val in enumerate(data):
            bg_color = "#ffffff" if idx % 2 == 0 else "#f8fafc"
            td = f'<td style="padding: 7px 10px; font-size: 12px; color: #1e293b; border: 1px solid #e2e8f0; font-family: Consolas, monospace;">{html.escape(str(val))}</td>'
            rows_trs.append(f'<tr style="background-color: {bg_color};">{td}</tr>')

        return f"""
        <div style="overflow-x: auto; max-width: 100%; border: 1px solid #cbd5e1; border-radius: 6px;">
            <table style="width: 100%; border-collapse: collapse; text-align: left;">
                <thead>
                    <tr><th style="background-color: #e2e8f0; color: #334155; padding: 8px 10px; font-size: 11px; text-align: left; font-weight: 600; border: 1px solid #cbd5e1;">Value</th></tr>
                </thead>
                <tbody>
                    {"".join(rows_trs)}
                </tbody>
            </table>
        </div>
        """

    def generate_markdown_report(
        self,
        script_title: str,
        result: RunResult,
        host_info: dict[str, str] | None = None,
        script_category: str = "",
    ) -> str:
        """Builds a structured Markdown report formatted for ticket comments or documentation."""
        info = host_info or self.get_system_audit_info()
        title_text = script_title or result.script_title or "PowerShell Execution"
        category_text = script_category or result.script_category or "System"

        lines = [
            f"### [PowerShellStore Audit] {title_text}",
            f"**Status:** `{result.status.upper()}` | **Category:** `{category_text}`",
            f"- **Target Host:** `{info.get('hostname', 'UNKNOWN')}`",
            f"- **Executed At:** {info.get('timestamp', '')}",
            f"- **OS:** {info.get('os_name', 'Windows')}",
            f"- **Operator:** {info.get('operator', 'Technician')}",
            f"- **Duration:** {result.duration_ms} ms | **Exit Code:** {result.exit_code}",
            f"- **Outcome Summary:** {result.summary or 'Execution completed.'}",
            "",
            "#### Structured Evidence:",
        ]

        if not result.data:
            lines.append("_No tabular evidence records returned by script._")
        elif isinstance(result.data[0], dict):
            columns = list(result.data[0].keys())
            # Header
            lines.append("| " + " | ".join(columns) + " |")
            lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
            # Rows
            for row_dict in result.data:
                row_vals = [
                    str(row_dict.get(c, "")).replace("|", "\\|").replace("\n", " ")
                    for c in columns
                ]
                lines.append("| " + " | ".join(row_vals) + " |")
        else:
            lines.append("| Output Value |")
            lines.append("| --- |")
            for val in result.data:
                escaped = str(val).replace("|", "\\|").replace("\n", " ")
                lines.append(f"| {escaped} |")

        if result.errors:
            lines.append("")
            lines.append("#### Errors & Warnings:")
            for err in result.errors:
                lines.append(f"- `{err}`")

        lines.append("")
        lines.append("---")
        lines.append("_Generated by PowerShellStore Workstation_")

        return "\n".join(lines)

    def create_mime_data(
        self,
        script_title: str,
        result: RunResult,
        host_info: dict[str, str] | None = None,
        script_category: str = "",
    ) -> QMimeData:
        """Constructs a QMimeData bundle containing both Rich Text (HTML) and Markdown (Plain Text)."""
        html_content = self.generate_html_report(
            script_title=script_title,
            result=result,
            host_info=host_info,
            script_category=script_category,
            standalone=False,
        )
        md_content = self.generate_markdown_report(
            script_title=script_title,
            result=result,
            host_info=host_info,
            script_category=script_category,
        )

        mime_data = QMimeData()
        mime_data.setHtml(html_content)
        mime_data.setText(md_content)
        return mime_data

    def copy_ticket_report_to_clipboard(
        self,
        script_title: str,
        result: RunResult,
        host_info: dict[str, str] | None = None,
        script_category: str = "",
    ) -> bool:
        """Copies both Rich Text (HTML) and Plain Text (Markdown) to the Windows Clipboard."""
        clipboard = QGuiApplication.clipboard()
        if not clipboard:
            return False

        mime_data = self.create_mime_data(
            script_title=script_title,
            result=result,
            host_info=host_info,
            script_category=script_category,
        )
        clipboard.setMimeData(mime_data)
        return True

    def save_html_report(
        self,
        file_path: Path | str,
        script_title: str,
        result: RunResult,
        host_info: dict[str, str] | None = None,
        script_category: str = "",
    ) -> Path:
        """Saves a standalone HTML execution report to disk."""
        target_path = Path(file_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        full_html = self.generate_html_report(
            script_title=script_title,
            result=result,
            host_info=host_info,
            script_category=script_category,
            standalone=True,
        )
        target_path.write_text(full_html, encoding="utf-8")
        return target_path
