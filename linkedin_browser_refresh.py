#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = ROOT.parent.parent
DEFAULT_TASKS_PATH = ROOT / "sources" / "linkedin_search_tasks.json"
DEFAULT_SOURCES_DIR = ROOT / "sources"
DEFAULT_GROUPED_OUTPUT_PATH = ROOT / "sources" / "linkedin_jobs_browser_export_grouped.json"
DEFAULT_NORMALIZED_OUTPUT_PATH = ROOT / "data" / "linkedin_jobs.json"
DEFAULT_REPORT_OUTPUT_PATH = ROOT / "data" / "linkedin_refresh_report.json"
DEFAULT_BROWSER_TIMEOUT_MS = 45000
DEFAULT_SCROLL_ROUNDS = 10
DEFAULT_SCROLL_PAUSE_SECONDS = 1.5
DEFAULT_PAGE_STABILIZE_SECONDS = 4.0
DEFAULT_MAX_CARDS_PER_TASK = 40
DEFAULT_NAVIGATION_RETRIES = 3
DEFAULT_NAVIGATION_RETRY_PAUSE_SECONDS = 3.0
DEFAULT_COMMIT_MESSAGE = "Refresh LinkedIn browser exports"
DEFAULT_REMOTE_DEBUGGING_URL = "http://127.0.0.1:9222"


def load_env() -> None:
    env_candidates = (
        ROOT / ".env",
        WORKSPACE_ROOT / ".env",
        ROOT / ".env.example",
        WORKSPACE_ROOT / ".env.example",
    )
    for candidate in env_candidates:
        if candidate.exists():
            load_dotenv(candidate, override=False)

    if os.getenv("DISABLE_SYSTEM_PROXY", "1").strip().lower() in {"1", "true", "yes", "on"}:
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            os.environ.pop(key, None)

        no_proxy_entries = {
            entry.strip()
            for entry in (os.getenv("NO_PROXY", "") + "," + os.getenv("no_proxy", "")).split(",")
            if entry.strip()
        }
        no_proxy_entries.update({"127.0.0.1", "localhost"})
        no_proxy_value = ",".join(sorted(no_proxy_entries))
        os.environ["NO_PROXY"] = no_proxy_value
        os.environ["no_proxy"] = no_proxy_value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh LinkedIn browser exports locally using Playwright and the existing search task catalog.",
    )
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS_PATH, help="LinkedIn search task catalog path.")
    parser.add_argument("--sources-dir", type=Path, default=DEFAULT_SOURCES_DIR, help="Output directory for per-task browser export files.")
    parser.add_argument(
        "--task-id",
        action="append",
        default=[],
        help="Only refresh one or more specific task ids. Can be provided multiple times.",
    )
    parser.add_argument("--headless", action="store_true", help="Run the browser in headless mode.")
    parser.add_argument(
        "--pause-for-login",
        action="store_true",
        help="Pause on the first page until you confirm LinkedIn login is ready.",
    )
    parser.add_argument(
        "--scroll-rounds",
        type=int,
        default=DEFAULT_SCROLL_ROUNDS,
        help="Number of incremental scroll rounds per search page.",
    )
    parser.add_argument(
        "--scroll-pause-seconds",
        type=float,
        default=DEFAULT_SCROLL_PAUSE_SECONDS,
        help="Pause between scroll rounds.",
    )
    parser.add_argument(
        "--page-stabilize-seconds",
        type=float,
        default=DEFAULT_PAGE_STABILIZE_SECONDS,
        help="Initial wait time after opening a LinkedIn search page.",
    )
    parser.add_argument(
        "--max-cards-per-task",
        type=int,
        default=DEFAULT_MAX_CARDS_PER_TASK,
        help="Maximum number of cards to keep per search task.",
    )
    parser.add_argument(
        "--browser-timeout-ms",
        type=int,
        default=DEFAULT_BROWSER_TIMEOUT_MS,
        help="Playwright default timeout in milliseconds.",
    )
    parser.add_argument(
        "--navigation-retries",
        type=int,
        default=DEFAULT_NAVIGATION_RETRIES,
        help="How many times to retry LinkedIn page navigation before giving up.",
    )
    parser.add_argument(
        "--navigation-retry-pause-seconds",
        type=float,
        default=DEFAULT_NAVIGATION_RETRY_PAUSE_SECONDS,
        help="Pause between LinkedIn navigation retries.",
    )
    parser.add_argument(
        "--refresh-bundle",
        action="store_true",
        help="Run linkedin_ingest.py --mode refresh_bundle after exporting raw browser files.",
    )
    parser.add_argument(
        "--git-push",
        action="store_true",
        help="After refresh_bundle, automatically git add/commit/push updated LinkedIn source files.",
    )
    parser.add_argument(
        "--commit-message",
        default=DEFAULT_COMMIT_MESSAGE,
        help="Commit message used with --git-push.",
    )
    return parser.parse_args()


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def resolve_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path


def get_repo_path() -> Path:
    return resolve_path(os.getenv("JOB_TRACKER_REPO_PATH", str(ROOT)).strip())


def get_user_data_dir() -> Path:
    return resolve_path(required_env("LINKEDIN_BROWSER_USER_DATA_DIR"))


def get_remote_debugging_url() -> str:
    return os.getenv("LINKEDIN_REMOTE_DEBUGGING_URL", DEFAULT_REMOTE_DEBUGGING_URL).strip()


def ensure_debug_endpoint_ready(remote_debugging_url: str, timeout_seconds: float = 5.0) -> None:
    version_url = remote_debugging_url.rstrip("/") + "/json/version"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(version_url, headers={"User-Agent": "job-tracker-linkedin-refresh"})
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(
            "Could not reach Chrome remote debugging endpoint. "
            f"Checked: {version_url}. Confirm Chrome was started with "
            "`--remote-debugging-port=9222` and that no local proxy is intercepting localhost."
        ) from exc

    web_socket_url = str(payload.get("webSocketDebuggerUrl") or "").strip()
    browser_name = str(payload.get("Browser") or "").strip()
    if not web_socket_url:
        raise RuntimeError(
            "Chrome remote debugging endpoint responded, but did not expose `webSocketDebuggerUrl`. "
            f"Checked: {version_url}"
        )

    print(
        f"Connected to Chrome debug endpoint: {browser_name or 'unknown browser'}",
        file=sys.stderr,
    )


def load_tasks(tasks_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(tasks_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"Unsupported task file shape: {tasks_path}")
    return [item for item in payload if isinstance(item, dict)]


def filter_tasks(tasks: list[dict[str, Any]], selected_ids: list[str]) -> list[dict[str, Any]]:
    if not selected_ids:
        return tasks
    selected = set(selected_ids)
    return [
        item
        for item in tasks
        if str(item.get("id") or item.get("task_id") or "").strip() in selected
    ]


def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def attach_or_launch_browser(playwright: Any, args: argparse.Namespace) -> tuple[Any, Any]:
    browser_executable = os.getenv("LINKEDIN_BROWSER_EXECUTABLE", "").strip() or None
    attach_to_existing = os.getenv("LINKEDIN_ATTACH_TO_EXISTING_BROWSER", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if attach_to_existing:
        remote_debugging_url = get_remote_debugging_url()
        ensure_debug_endpoint_ready(remote_debugging_url)
        browser = playwright.chromium.connect_over_cdp(remote_debugging_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        return browser, context

    user_data_dir = get_user_data_dir()
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(user_data_dir),
        headless=args.headless,
        executable_path=browser_executable,
    )
    return None, context


def extract_cards(page: Any, max_cards: int) -> list[dict[str, Any]]:
    js = """
    (maxCards) => {
      const cardSelectors = [
        'li.jobs-search-results__list-item',
        'li.scaffold-layout__list-item',
        'div.job-card-container',
        'div.base-card'
      ];

      function queryFirst(root, selectors) {
        for (const selector of selectors) {
          const node = root.querySelector(selector);
          if (node) return node;
        }
        return null;
      }

      function nodeText(node) {
        return (node?.textContent || '').replace(/\\s+/g, ' ').trim();
      }

      function nodeHref(node) {
        return (node?.href || '').trim();
      }

      function collectCardNodes() {
        const nodes = [];
        for (const selector of cardSelectors) {
          for (const node of document.querySelectorAll(selector)) {
            if (!nodes.includes(node)) nodes.push(node);
          }
        }
        return nodes;
      }

      const results = [];
      for (const card of collectCardNodes()) {
        const titleNode = queryFirst(card, [
          'a.job-card-list__title--link',
          'a.job-card-container__link',
          'a.job-card-list__title',
          'a.base-card__full-link',
          'h3 a',
          'a'
        ]);
        const companyNode = queryFirst(card, [
          '.artdeco-entity-lockup__subtitle',
          '.job-card-container__company-name',
          '.base-search-card__subtitle',
          'h4'
        ]);
        const locationNode = queryFirst(card, [
          '.job-card-container__metadata-wrapper li',
          '.job-card-container__metadata-item',
          '.artdeco-entity-lockup__caption',
          '.base-search-card__metadata'
        ]);
        const summaryNode = queryFirst(card, [
          '.job-card-list__snippet',
          '.job-card-container__description',
          '.base-search-card__snippet',
          '.job-card-container__footer-wrapper'
        ]);
        const timeNode = queryFirst(card, [
          'time',
          '.job-card-container__footer-item',
          '.job-search-card__listdate'
        ]);

        const title = nodeText(titleNode);
        const company = nodeText(companyNode);
        const location = nodeText(locationNode);
        const summary = nodeText(summaryNode);
        const link = nodeHref(titleNode);
        const publishedAt = (timeNode?.getAttribute('datetime') || nodeText(timeNode) || '').trim();

        if (!title || !link) continue;
        results.push({
          title,
          company,
          location,
          summary,
          link,
          published_at: publishedAt,
          source: 'LinkedIn Browser Search',
          source_type: 'linkedin_manual'
        });
        if (results.length >= maxCards) break;
      }
      return results;
    }
    """
    return page.evaluate(js, max_cards)


def scroll_results(page: Any, scroll_rounds: int, pause_seconds: float) -> None:
    for _ in range(scroll_rounds):
        page.mouse.wheel(0, 3000)
        time.sleep(pause_seconds)


def open_task_page(page: Any, url: str, retries: int, pause_seconds: float) -> None:
    last_error: Exception | None = None
    for attempt in range(1, max(retries, 1) + 1):
        try:
            page.goto(url, wait_until="domcontentloaded")
            return
        except Exception as exc:
            last_error = exc
            if attempt >= max(retries, 1):
                break
            print(
                f"Navigation failed (attempt {attempt}/{max(retries, 1)}). Retrying in {pause_seconds:.1f}s: {url}",
                file=sys.stderr,
            )
            time.sleep(pause_seconds)

    if last_error is not None:
        raise last_error


def write_task_export(
    sources_dir: Path,
    task: dict[str, Any],
    cards: list[dict[str, Any]],
) -> Path:
    task_id = str(task.get("id") or task.get("task_id") or "").strip()
    export_path = sources_dir / f"{task_id}.browser_export.json"
    payload = {
        "task_id": task_id,
        "task_name": str(task.get("name") or task.get("task_name") or task_id).strip(),
        "query": str(task.get("query") or "").strip(),
        "region": str(task.get("region") or "").strip(),
        "source": "LinkedIn Browser Search",
        "source_type": "linkedin_manual",
        "url": str(task.get("url") or "").strip(),
        "jobs": cards,
    }
    export_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return export_path


def run_refresh_bundle() -> None:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "linkedin_ingest.py"),
            "--mode",
            "refresh_bundle",
        ],
        cwd=str(ROOT),
        check=True,
    )


def git_push_changes(commit_message: str) -> None:
    repo_path = get_repo_path()
    subprocess.run(["git", "add", "sources", "data/linkedin_jobs.json", "data/linkedin_refresh_report.json"], cwd=repo_path, check=True)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_path)
    if diff.returncode == 0:
        print("No LinkedIn source changes to commit.", file=sys.stderr)
        return
    subprocess.run(["git", "commit", "-m", commit_message], cwd=repo_path, check=True)
    subprocess.run(["git", "push"], cwd=repo_path, check=True)


def main() -> int:
    load_env()
    args = parse_args()

    tasks = filter_tasks(load_tasks(args.tasks), args.task_id)
    if not tasks:
        raise RuntimeError("No LinkedIn search tasks selected.")

    ensure_output_dir(args.sources_dir)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Run `pip install playwright` and `playwright install chromium` first."
        ) from exc

    written_files: list[str] = []
    failed_tasks: list[dict[str, str]] = []

    with sync_playwright() as playwright:
        browser, context = attach_or_launch_browser(playwright, args)

        for index, task in enumerate(tasks, start=1):
            task_id = str(task.get("id") or task.get("task_id") or "").strip()
            task_name = str(task.get("name") or task.get("task_name") or task_id).strip()
            url = str(task.get("url") or "").strip()
            if not url:
                print(f"Skipping task with empty url: {task_id}", file=sys.stderr)
                continue

            page = context.new_page()
            page.set_default_timeout(args.browser_timeout_ms)
            try:
                print(f"[{index}/{len(tasks)}] Opening {task_name}", file=sys.stderr)
                open_task_page(page, url, args.navigation_retries, args.navigation_retry_pause_seconds)
                time.sleep(args.page_stabilize_seconds)

                if index == 1 and args.pause_for_login:
                    input("Confirm LinkedIn is logged in and results are visible, then press Enter to continue...")

                scroll_results(page, args.scroll_rounds, args.scroll_pause_seconds)
                cards = extract_cards(page, args.max_cards_per_task)
                export_path = write_task_export(args.sources_dir, task, cards)
                written_files.append(str(export_path))
                print(f"Saved {len(cards)} cards -> {export_path.name}", file=sys.stderr)
            except Exception as exc:
                failed_tasks.append(
                    {
                        "task_id": task_id,
                        "task_name": task_name,
                        "url": url,
                        "error": str(exc),
                    }
                )
                print(f"Task failed, skipping {task_name}: {exc}", file=sys.stderr)
            finally:
                page.close()

        context.close()
        if browser is not None:
            browser.close()

    if args.refresh_bundle:
        run_refresh_bundle()

    if args.git_push:
        git_push_changes(args.commit_message)

    print(
        json.dumps(
            {
                "tasks_processed": len(tasks),
                "written_files": written_files,
                "failed_tasks": failed_tasks,
                "refresh_bundle": args.refresh_bundle,
                "git_push": args.git_push,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
