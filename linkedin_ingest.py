#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import feedparser
import requests

from job_tracker import (
    EXPERIMENTAL_LINKEDIN_SOURCES,
    canonicalize_url,
    load_env,
    parse_datetime_string,
    parse_entry_datetime,
    strip_html,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_PATH = ROOT / "data" / "linkedin_jobs.json"
DEFAULT_INPUT_PATH = ROOT / "sources" / "linkedin_jobs_seed.example.json"
DEFAULT_TEXT_INPUT_PATH = ROOT / "sources" / "linkedin_jobs_manual_text.sample.txt"
DEFAULT_GROUPED_OUTPUT_PATH = ROOT / "sources" / "linkedin_jobs_browser_export_grouped.json"
DEFAULT_TASKS_PATH = ROOT / "sources" / "linkedin_search_tasks.json"
DEFAULT_REPORT_PATH = ROOT / "data" / "linkedin_refresh_report.json"
DEFAULT_SOURCES_DIR = ROOT / "sources"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_FRESHNESS_DAYS = 7


@dataclass(slots=True)
class LinkedInJob:
    title: str
    company: str
    location: str
    summary: str
    link: str
    published_at: datetime | None
    source: str
    source_type: str
    source_task_id: str
    source_task_name: str
    source_query: str
    source_region: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a normalized LinkedIn middle-layer JSON file.",
    )
    parser.add_argument(
        "--mode",
        choices=("manual_json", "manual_text", "legacy_rss", "refresh_bundle"),
        default="manual_json",
        help="Input mode. manual_json is the default stable path; manual_text is the low-friction semi-manual path; legacy_rss is a temporary compatibility path; refresh_bundle aggregates per-task browser exports into grouped + normalized LinkedIn outputs.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="Raw input path for manual_json or manual_text mode.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Normalized output JSON path.",
    )
    parser.add_argument(
        "--grouped-output",
        type=Path,
        default=DEFAULT_GROUPED_OUTPUT_PATH,
        help="Grouped browser-export bundle output path for refresh_bundle mode.",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Freshness report output path for refresh_bundle mode.",
    )
    parser.add_argument(
        "--tasks",
        type=Path,
        default=DEFAULT_TASKS_PATH,
        help="LinkedIn search task catalog path for refresh_bundle mode.",
    )
    parser.add_argument(
        "--sources-dir",
        type=Path,
        default=DEFAULT_SOURCES_DIR,
        help="Directory containing per-task LinkedIn browser export files.",
    )
    parser.add_argument(
        "--freshness-days",
        type=int,
        default=DEFAULT_FRESHNESS_DAYS,
        help="Freshness window in days used by refresh_bundle reporting.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the normalized payload instead of writing it to disk.",
    )
    return parser.parse_args()


def get_timeout_seconds() -> float:
    return float(os.getenv("LINKEDIN_INGEST_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)).strip())


def coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if isinstance(value, str):
        return parse_datetime_string(value)
    return None


def normalize_manual_job(raw: dict[str, Any]) -> LinkedInJob | None:
    title = strip_html(str(raw.get("title") or raw.get("position") or "")).strip()
    company = strip_html(str(raw.get("company") or raw.get("company_name") or "")).strip()
    location = strip_html(str(raw.get("location") or raw.get("city") or "")).strip()
    summary = strip_html(
        str(
            raw.get("summary")
            or raw.get("description")
            or raw.get("snippet")
            or raw.get("content")
            or ""
        )
    ).strip()
    link = canonicalize_url(str(raw.get("link") or raw.get("url") or ""))
    published_at = coerce_datetime(
        raw.get("published_at")
        or raw.get("published")
        or raw.get("posted_at")
        or raw.get("date")
    )
    source = str(raw.get("source") or "LinkedIn Manual").strip() or "LinkedIn Manual"
    source_type = str(raw.get("source_type") or "linkedin_manual").strip() or "linkedin_manual"
    source_task_id = str(raw.get("source_task_id") or raw.get("task_id") or "").strip()
    source_task_name = str(raw.get("source_task_name") or raw.get("task_name") or "").strip()
    source_query = str(raw.get("source_query") or raw.get("query") or "").strip()
    source_region = str(raw.get("source_region") or raw.get("region") or "").strip()

    if not title or not link:
        return None

    return LinkedInJob(
        title=title,
        company=company,
        location=location,
        summary=summary,
        link=link,
        published_at=published_at,
        source=source,
        source_type=source_type,
        source_task_id=source_task_id,
        source_task_name=source_task_name,
        source_query=source_query,
        source_region=source_region,
    )


def extract_manual_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        raise RuntimeError("Unsupported JSON payload shape for manual LinkedIn import.")

    if isinstance(payload.get("jobs"), list):
        return [item for item in payload["jobs"] if isinstance(item, dict)]

    exports = payload.get("exports")
    if not isinstance(exports, list):
        raise RuntimeError("Unsupported JSON payload shape in manual LinkedIn import.")

    items: list[dict[str, Any]] = []
    for export in exports:
        if not isinstance(export, dict):
            continue

        export_source = str(export.get("source") or "LinkedIn Browser Search").strip() or "LinkedIn Browser Search"
        export_source_type = (
            str(export.get("source_type") or "linkedin_manual").strip() or "linkedin_manual"
        )
        export_task_id = str(export.get("task_id") or "").strip()
        export_task_name = str(export.get("task_name") or "").strip()
        export_query = str(export.get("query") or "").strip()
        export_region = str(export.get("region") or "").strip()

        for job in export.get("jobs", []):
            if not isinstance(job, dict):
                continue

            merged = dict(job)
            merged.setdefault("source", export_source)
            merged.setdefault("source_type", export_source_type)
            if export_task_id:
                merged.setdefault("task_id", export_task_id)
            if export_task_name:
                merged.setdefault("task_name", export_task_name)
            if export_query:
                merged.setdefault("query", export_query)
            if export_region:
                merged.setdefault("region", export_region)
            items.append(merged)

    return items


def load_manual_json(input_path: Path) -> list[LinkedInJob]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    raw_items = extract_manual_items(payload)

    jobs: list[LinkedInJob] = []
    for item in raw_items:
        normalized = normalize_manual_job(item)
        if normalized is not None:
            jobs.append(normalized)
    return jobs


def load_task_catalog(tasks_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(tasks_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"Unsupported task catalog shape: {tasks_path}")
    return [item for item in payload if isinstance(item, dict)]


def split_text_records(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n")
    return [chunk.strip() for chunk in re.split(r"\n\s*\n(?=title:)", normalized, flags=re.IGNORECASE) if chunk.strip()]


def parse_text_record(block: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    summary_lines: list[str] = []
    in_summary = False

    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if in_summary and ":" not in line:
            summary_lines.append(line)
            continue

        key, sep, value = line.partition(":")
        if not sep:
            if in_summary:
                summary_lines.append(line)
            continue

        normalized_key = key.strip().lower()
        normalized_value = value.strip()

        if normalized_key == "summary":
            in_summary = True
            if normalized_value:
                summary_lines.append(normalized_value)
            continue

        in_summary = False
        parsed[normalized_key] = normalized_value

    if summary_lines:
        parsed["summary"] = " ".join(summary_lines).strip()
    return parsed


def load_manual_text(input_path: Path) -> list[LinkedInJob]:
    text = input_path.read_text(encoding="utf-8")
    blocks = split_text_records(text)

    jobs: list[LinkedInJob] = []
    for block in blocks:
        parsed = parse_text_record(block)
        normalized = normalize_manual_job(
            {
                "title": parsed.get("title", ""),
                "company": parsed.get("company", ""),
                "location": parsed.get("location", ""),
                "summary": parsed.get("summary", ""),
                "link": parsed.get("link", ""),
                "published_at": parsed.get("published_at") or parsed.get("published") or parsed.get("date"),
                "source": parsed.get("source", "LinkedIn Manual Text"),
                "source_type": parsed.get("source_type", "linkedin_manual"),
            }
        )
        if normalized is not None:
            jobs.append(normalized)
    return jobs


def load_legacy_rss() -> list[LinkedInJob]:
    session = requests.Session()
    session.trust_env = False

    jobs: list[LinkedInJob] = []
    for source in EXPERIMENTAL_LINKEDIN_SOURCES:
        try:
            response = session.get(
                source["url"],
                timeout=get_timeout_seconds(),
                headers={"User-Agent": "LinkedInIngest/1.0"},
                allow_redirects=True,
            )
            response.raise_for_status()
        except Exception as exc:
            print(f"Warning: failed to fetch {source['name']}: {exc}", file=sys.stderr)
            continue

        parsed = feedparser.parse(response.content)
        for entry in parsed.entries:
            link = canonicalize_url(str(entry.get("link") or entry.get("guid") or ""))
            title = strip_html(str(entry.get("title") or "")).strip()
            summary = strip_html(
                str(entry.get("summary") or entry.get("contentSnippet") or entry.get("description") or "")
            ).strip()
            published_at = parse_entry_datetime(entry)

            if not title or not link:
                continue

            jobs.append(
                LinkedInJob(
                    title=title,
                    company="",
                    location="",
                    summary=summary,
                    link=link,
                    published_at=published_at,
                    source=source["name"],
                    source_type="linkedin_rss_legacy",
                )
            )

    return jobs


def aggregate_browser_exports(tasks_path: Path, sources_dir: Path) -> dict[str, Any]:
    tasks = load_task_catalog(tasks_path)
    task_by_id = {
        str(task.get("id") or task.get("task_id") or "").strip(): task
        for task in tasks
        if str(task.get("id") or task.get("task_id") or "").strip()
    }

    exports: list[dict[str, Any]] = []
    report_tasks: list[dict[str, Any]] = []

    for task in tasks:
        task_id = str(task.get("id") or task.get("task_id") or "").strip()
        if not task_id:
            continue

        export_path = sources_dir / f"{task_id}.browser_export.json"
        raw_jobs_count = 0
        freshest_date: str | None = None
        oldest_date: str | None = None
        status = "missing"

        if export_path.exists():
            export_payload = json.loads(export_path.read_text(encoding="utf-8"))
            if not isinstance(export_payload, dict):
                raise RuntimeError(f"Unsupported browser export shape: {export_path}")

            jobs = export_payload.get("jobs", [])
            if not isinstance(jobs, list):
                raise RuntimeError(f"Unsupported jobs payload in: {export_path}")

            normalized_jobs: list[dict[str, Any]] = []
            published_dates: list[datetime] = []
            for raw_job in jobs:
                if not isinstance(raw_job, dict):
                    continue
                normalized_jobs.append(dict(raw_job))
                published_at = coerce_datetime(
                    raw_job.get("published_at")
                    or raw_job.get("published")
                    or raw_job.get("posted_at")
                    or raw_job.get("date")
                )
                if published_at:
                    published_dates.append(published_at)

            raw_jobs_count = len(normalized_jobs)
            if raw_jobs_count > 0:
                status = "ready"
            else:
                status = "empty"

            if published_dates:
                freshest_date = max(published_dates).date().isoformat()
                oldest_date = min(published_dates).date().isoformat()

            exports.append(
                {
                    "task_id": task_id,
                    "task_name": str(
                        export_payload.get("task_name")
                        or task.get("name")
                        or task.get("task_name")
                        or task_id
                    ).strip(),
                    "query": str(export_payload.get("query") or task.get("query") or "").strip(),
                    "region": str(export_payload.get("region") or task.get("region") or "").strip(),
                    "source": str(export_payload.get("source") or "LinkedIn Browser Search").strip()
                    or "LinkedIn Browser Search",
                    "source_type": str(export_payload.get("source_type") or "linkedin_manual").strip()
                    or "linkedin_manual",
                    "url": str(export_payload.get("url") or task.get("url") or "").strip(),
                    "jobs": normalized_jobs,
                }
            )

        report_tasks.append(
            {
                "task_id": task_id,
                "task_name": str(task.get("name") or task.get("task_name") or task_id).strip(),
                "query": str(task.get("query") or "").strip(),
                "expected_role_bucket": str(task.get("expected_role_bucket") or "").strip(),
                "status": status,
                "export_file": str(export_path),
                "jobs_count": raw_jobs_count,
                "freshest_published_at": freshest_date,
                "oldest_published_at": oldest_date,
            }
        )

    missing_tasks = [item["task_id"] for item in report_tasks if item["status"] == "missing"]
    empty_tasks = [item["task_id"] for item in report_tasks if item["status"] == "empty"]

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "generated_from_tasks": str(tasks_path),
        "generated_from_sources_dir": str(sources_dir),
        "exports": exports,
        "task_report": report_tasks,
        "summary": {
            "task_count": len(tasks),
            "exported_task_count": len(exports),
            "missing_tasks": missing_tasks,
            "empty_tasks": empty_tasks,
        },
        "task_by_id": task_by_id,
    }


def build_refresh_report(grouped_payload: dict[str, Any], freshness_days: int) -> dict[str, Any]:
    freshness_cutoff = (datetime.now(UTC) - timedelta(days=freshness_days)).date()
    stale_tasks: list[str] = []
    fresh_tasks: list[str] = []

    for item in grouped_payload.get("task_report", []):
        freshest_raw = item.get("freshest_published_at")
        if not freshest_raw:
            continue
        freshest_date = datetime.fromisoformat(freshest_raw).date()
        if freshest_date < freshness_cutoff:
            stale_tasks.append(item["task_id"])
        else:
            fresh_tasks.append(item["task_id"])

    normalized_jobs = dedupe_jobs(
        load_manual_json_payload(grouped_payload)
    )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "freshness_days": freshness_days,
        "freshness_cutoff": freshness_cutoff.isoformat(),
        "summary": {
            **grouped_payload.get("summary", {}),
            "normalized_jobs": len(normalized_jobs),
            "fresh_task_count": len(fresh_tasks),
            "stale_task_count": len(stale_tasks),
            "fresh_tasks": fresh_tasks,
            "stale_tasks": stale_tasks,
        },
        "tasks": grouped_payload.get("task_report", []),
    }


def load_manual_json_payload(payload: Any) -> list[LinkedInJob]:
    raw_items = extract_manual_items(payload)
    jobs: list[LinkedInJob] = []
    for item in raw_items:
        normalized = normalize_manual_job(item)
        if normalized is not None:
            jobs.append(normalized)
    return jobs


def dedupe_jobs(jobs: list[LinkedInJob]) -> list[LinkedInJob]:
    deduped: dict[str, LinkedInJob] = {}
    for job in jobs:
        deduped.setdefault(job.link, job)
    return list(deduped.values())


def jobs_to_json(jobs: list[LinkedInJob]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for job in jobs:
        payload.append(
            {
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "summary": job.summary,
                "link": job.link,
                "published_at": job.published_at.isoformat() if job.published_at else None,
                "source": job.source,
                "source_type": job.source_type,
                "source_task_id": job.source_task_id,
                "source_task_name": job.source_task_name,
                "source_query": job.source_query,
                "source_region": job.source_region,
            }
        )
    return payload


def main() -> None:
    load_env()
    args = parse_args()

    if args.mode == "manual_json":
        if not args.input.exists():
            raise RuntimeError(f"Missing input file for manual_json mode: {args.input}")
        jobs = load_manual_json(args.input)
    elif args.mode == "manual_text":
        if args.input == DEFAULT_INPUT_PATH:
            args.input = DEFAULT_TEXT_INPUT_PATH
        if not args.input.exists():
            raise RuntimeError(f"Missing input file for manual_text mode: {args.input}")
        jobs = load_manual_text(args.input)
    elif args.mode == "refresh_bundle":
        if not args.tasks.exists():
            raise RuntimeError(f"Missing task catalog for refresh_bundle mode: {args.tasks}")
        if not args.sources_dir.exists():
            raise RuntimeError(f"Missing sources directory for refresh_bundle mode: {args.sources_dir}")

        grouped_payload = aggregate_browser_exports(args.tasks, args.sources_dir)
        jobs = dedupe_jobs(load_manual_json_payload(grouped_payload))
        normalized_payload = jobs_to_json(jobs)
        refresh_report = build_refresh_report(grouped_payload, freshness_days=args.freshness_days)

        if args.dry_run:
            print(
                json.dumps(
                    {
                        "mode": args.mode,
                        "grouped_output": str(args.grouped_output),
                        "output": str(args.output),
                        "report_output": str(args.report_output),
                        "summary": refresh_report["summary"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return

        args.grouped_output.parent.mkdir(parents=True, exist_ok=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.report_output.parent.mkdir(parents=True, exist_ok=True)

        grouped_to_write = dict(grouped_payload)
        grouped_to_write.pop("task_by_id", None)
        args.grouped_output.write_text(json.dumps(grouped_to_write, ensure_ascii=False, indent=2), encoding="utf-8")
        args.output.write_text(json.dumps(normalized_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        args.report_output.write_text(json.dumps(refresh_report, ensure_ascii=False, indent=2), encoding="utf-8")

        print(
            json.dumps(
                {
                    "mode": args.mode,
                    "grouped_output": str(args.grouped_output),
                    "jobs": len(normalized_payload),
                    "output": str(args.output),
                    "report_output": str(args.report_output),
                    "summary": refresh_report["summary"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    else:
        jobs = load_legacy_rss()

    jobs = dedupe_jobs(jobs)
    payload = jobs_to_json(jobs)

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "mode": args.mode,
                "jobs": len(payload),
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
