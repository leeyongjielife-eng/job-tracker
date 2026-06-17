#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import feedparser
import requests
from dateutil import parser as date_parser
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = ROOT.parent.parent
DEFAULT_LOOKBACK_DAYS = 60
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_GLM_MODEL = "glm-4.5-flash"
DEFAULT_WEEKLY_CRON_UTC = "0 0 * * 1"
DEFAULT_ENGINEERING_ROLE_CAP = 5
DEFAULT_ENGINEERING_SHARE_CAP = 0.3
DEFAULT_ENGINEERING_PER_COMPANY_CAP = 2
DEFAULT_NON_ENGINEERING_PER_COMPANY_CAP = 3
DEFAULT_REGION_SCOPE = "asia_focus"
DEFAULT_GLM_MAX_JOBS = 12
DEFAULT_LLM_SUMMARY_MAX_CHARS = 2200
DEFAULT_GLM_REQUEST_INTERVAL_SECONDS = 3.0
DEFAULT_GLM_RETRY_BACKOFF_SECONDS = 5.0
DEFAULT_GLM_RATE_LIMIT_COOLDOWN_SECONDS = 30.0
DEFAULT_SOURCE_CATALOG_PATH = ROOT / "sources" / "company_sources.json"
DEFAULT_LINKEDIN_MIDDLE_LAYER_PATH = ROOT / "data" / "linkedin_jobs.json"
DEFAULT_REVIEW_PACKET_PATH = ROOT / "data" / "linkedin_curated_review_packets.json"
DEFAULT_LAGOU_TIMEOUT_SECONDS = 35.0
DEFAULT_LAGOU_MAX_RETRIES = 3
DEFAULT_LAGOU_RETRY_BACKOFF_SECONDS = 3.0


def default_lookback_days() -> int:
    raw = os.getenv("JOB_TRACKER_LOOKBACK_DAYS", "").strip()
    if raw:
        return int(raw)
    return DEFAULT_LOOKBACK_DAYS

EXPERIMENTAL_LINKEDIN_SOURCES: list[dict[str, Any]] = [
    {
        "name": "LinkedIn AI PM",
        "type": "rss",
        "url": "https://rss.app/feeds/fZB5650QaIpLjukV.xml",
        "priority": 88,
        "category": "linkedin",
    },
    {
        "name": "LinkedIn AI Operations",
        "type": "rss",
        "url": "https://rss.app/feeds/lAXlAekAHx0uFpbr.xml",
        "priority": 86,
        "category": "linkedin",
    },
    {
        "name": "LinkedIn AI Project Manager",
        "type": "rss",
        "url": "https://rss.app/feeds/gBCjoPUN9cGt17d9.xml",
        "priority": 86,
        "category": "linkedin",
    },
    {
        "name": "LinkedIn 人工智能产品",
        "type": "rss",
        "url": "https://rss.app/feeds/JW0oZ1hTiZd58T99.xml",
        "priority": 89,
        "category": "linkedin",
    },
]

BUILTIN_FALLBACK_SOURCES: list[dict[str, Any]] = [
    {
        "name": "Scale AI Greenhouse",
        "type": "greenhouse",
        "board_token": "scaleai",
        "company": "Scale AI",
        "priority": 100,
        "category": "greenhouse",
    },
    {
        "name": "Glean Greenhouse",
        "type": "greenhouse",
        "board_token": "gleanwork",
        "company": "Glean",
        "priority": 100,
        "category": "greenhouse",
    },
    {
        "name": "Turing Greenhouse",
        "type": "greenhouse",
        "board_token": "turing",
        "company": "Turing",
        "priority": 100,
        "category": "greenhouse",
    },
    {
        "name": "PhysicsX Greenhouse",
        "type": "greenhouse",
        "board_token": "physicsx",
        "company": "PhysicsX",
        "priority": 100,
        "category": "greenhouse",
    },
    {
        "name": "Rubrik Greenhouse",
        "type": "greenhouse",
        "board_token": "rubrik",
        "company": "Rubrik",
        "priority": 92,
        "category": "greenhouse",
    },
    {
        "name": "Databricks Greenhouse",
        "type": "greenhouse",
        "board_token": "databricks",
        "company": "Databricks",
        "priority": 90,
        "category": "greenhouse",
    },
    {
        "name": "Mistral Lever",
        "type": "lever",
        "company_slug": "mistral",
        "company": "Mistral AI",
        "priority": 95,
        "category": "lever",
    },
]

SOURCE_PRIORITY_BY_CATEGORY = {
    "greenhouse": 100,
    "lever": 95,
    "company_careers": 90,
    "yc_jobs": 80,
    "boss": 70,
    "lagou": 65,
    "linkedin": 40,
    "google_alert": 30,
    "other": 20,
}

TITLE_KEYWORDS = [
    "product manager",
    "ai product manager",
    "growth pm",
    "technical product manager",
    "program manager",
    "project manager",
    "operations manager",
    "product lead",
    "strategy",
    "ai",
    "machine learning",
    "llm",
    "genai",
    "agent",
    "产品经理",
    "ai产品经理",
    "genai产品经理",
    "gen-ai产品经理",
    "aigc产品经理",
    "大模型产品经理",
    "智能体产品经理",
    "ai平台产品经理",
    "产品负责人",
]

TARGET_ROLE_PATTERNS = [
    r"\bai product manager\b",
    r"\bproduct manager\b",
    r"\btechnical product manager\b",
    r"\bproduct lead\b",
    r"\bproduct ops\b",
    r"\bprogram manager\b",
    r"\bproject manager\b",
    r"\boperations manager\b",
    r"\boperations lead\b",
    r"\bops lead\b",
    r"\bstrategy and operations\b",
    r"\bstrategy & operations\b",
    r"\bbusiness operations\b",
    r"\bbizops\b",
    r"\bagent engineer\b",
    r"\bai agent engineer\b",
    r"\bagentic engineer\b",
    r"\bforward deployed engineer\b",
    r"\bapplied ai engineer\b",
    r"\bai engineer\b",
    r"ai产品经理",
    r"产品经理",
    r"高级产品经理",
    r"资深产品经理",
    r"gen-?ai产品经理",
    r"aigc产品经理",
    r"大模型产品经理",
    r"智能体产品经理",
    r"ai平台产品经理",
    r"大模型平台产品",
    r"智能体平台产品",
    r"产品负责人",
    r"ai产品负责人",
    r"产品负责人.*ai",
]

AI_CONTEXT_PATTERNS = [
    r"\bai\b",
    r"\bartificial intelligence\b",
    r"\bgenai\b",
    r"\bgen-ai\b",
    r"\baigc\b",
    r"\bllm\b",
    r"\blarge language model\b",
    r"\bagent\b",
    r"\bagents\b",
    r"\bagentic\b",
    r"\bmulti-agent\b",
    r"\bmulti agent\b",
    r"\bai native\b",
    r"\bmachine learning\b",
    r"\bml\b",
    r"人工智能",
    r"大模型",
    r"模型",
    r"生成式",
    r"智能体",
    r"多模态",
    r"知识图谱",
    r"知识库",
    r"agent",
    r"agentic",
    r"llm",
    r"genai",
]

WEAK_AI_CONTEXT_PATTERNS = [
    r"\bcopilot\b",
    r"\bai tool\b",
    r"\bai tools\b",
    r"\bmodel platform\b",
    r"\bmodel router\b",
    r"\bai gateway\b",
    r"\binference\b",
    r"\bprompt\b",
    r"\brag\b",
    r"\bmultimodal\b",
    r"\bassistant\b",
    r"\bagent platform\b",
    r"\bworkflow\b",
    r"\bworkflows\b",
    r"\btooling\b",
    r"\bmodel serving\b",
    r"\bllm application\b",
    r"\bllm apps\b",
    r"\bai应用\b",
    r"\b智能体平台\b",
    r"\b模型平台\b",
    r"\b推理\b",
    r"\b提示词\b",
    r"\b多模态\b",
    r"\bdify\b",
    r"\bcoze\b",
    r"\bprompt engineering\b",
    r"\bsystem prompt\b",
    r"\bn8n\b",
    r"百炼",
    r"知识图谱",
    r"知识库",
]

AI_COMPANY_KEYWORDS = (
    "minimax",
    "moonshot",
    "kimi",
    "01 ai",
    "01.ai",
    "zhipu",
    "智谱",
    "baichuan",
    "百川",
    "stepfun",
    "阶跃星辰",
    "modelbest",
    "面壁",
    "siliconflow",
    "rayneo",
    "wing assistant",
    "wuxi biologics",
    "药明生物",
)

NEGATIVE_TITLE_PATTERNS = [
    r"\btechnical program manager\b",
    r"\btpm\b",
    r"\baccount executive\b",
    r"\bsales\b",
    r"\brecruiter\b",
    r"\bcounsel\b",
    r"\bdesigner\b",
    r"\bintern\b",
    r"\bscientist\b",
    r"\bmember of technical staff\b",
]

NOISE_SUFFIXES = [
    "linkedin",
    "boss直聘",
    "boss",
    "拉勾招聘",
    "lagou",
    "google alerts",
]

LOCATION_HINTS = [
    "beijing",
    "shanghai",
    "shenzhen",
    "guangzhou",
    "hangzhou",
    "hong kong",
    "singapore",
    "remote",
    "hybrid",
    "onsite",
]

LOCATION_PRIORITY = {
    "guangdong": 1,
    "shenzhen": 1,
    "guangzhou": 1,
    "foshan": 1,
    "dongguan": 1,
    "hangzhou": 2,
    "shanghai": 3,
    "hong kong": 4,
    "hongkong": 4,
    "hk": 4,
    "singapore": 5,
}

TARGET_LOCATION_TOKENS = (
    "shenzhen",
    "guangzhou",
    "dongguan",
    "foshan",
    "guangdong",
    "hangzhou",
    "shanghai",
    "hong kong",
    "hongkong",
    "hk",
    "singapore",
    "广东",
    "深圳",
    "广州",
    "东莞",
    "佛山",
    "杭州",
    "上海",
    "香港",
    "新加坡",
)

REMOTE_LOCATION_TOKENS = (
    "remote",
    "hybrid",
)

REMOTE_APAC_HINTS = (
    "apac",
    "asia",
    "asia pacific",
    "china",
    "hong kong",
    "hongkong",
    "singapore",
    "gmt+8",
    "utc+8",
)

STRICT_REGION_SOURCE_TYPES = {
    "lagou",
    "boss",
    "rss",
    "linkedin",
    "linkedin_json",
}

SOFT_REGION_SOURCE_TYPES = {
    "greenhouse",
    "lever",
    "company_careers",
    "company_careers_page",
    "feishu_careers",
}

REVIEW_DECISION_CACHE: dict[str, str] | None = None


@dataclass(slots=True)
class JobPosting:
    title: str
    company: str
    location: str
    summary: str
    link: str
    published_at: datetime
    source: str
    source_type: str
    source_priority: int
    relevance_score: float | None = None
    required_skills: list[str] | None = None
    years_of_experience: str | None = None
    mentions_agent: bool | None = None
    mentions_ai_native: bool | None = None
    keywords: str | None = None

    @property
    def company_sort_key(self) -> str:
        return normalize_company_name(self.company) or "zzz"

    @property
    def is_engineering_role(self) -> bool:
        title = self.title.lower()
        engineering_tokens = (
            "engineer",
            "engineering",
            "forward deployed engineer",
            "applied ai engineer",
            "agent engineer",
            "agentic engineer",
        )
        return any(token in title for token in engineering_tokens)


def load_env() -> None:
    env_candidates = (
        ROOT / ".env",
        WORKSPACE_ROOT / ".env",
        ROOT / ".env.example",
        WORKSPACE_ROOT / ".env.example",
    )
    for env_path in env_candidates:
        if env_path.exists():
            load_dotenv(env_path)
            break

    if os.getenv("DISABLE_SYSTEM_PROXY", "1").strip() == "1":
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            os.environ.pop(key, None)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Track AI PM jobs and sync them to a Notion database.")
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=default_lookback_days(),
        help="Include jobs published within this rolling lookback window. Default is 60 days.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch and analyze jobs without writing to Notion.")
    parser.add_argument("--skip-analysis", action="store_true", help="Do not call the LLM analysis step. Useful for local validation.")
    parser.add_argument("--max-jobs", type=int, default=0, help="Limit the number of jobs processed after deduplication.")
    parser.add_argument("--output", type=Path, help="Write the processed jobs as JSON for inspection.")
    return parser.parse_args()


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_timeout_seconds() -> float:
    return float(os.getenv("RSS_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)).strip())


def get_lagou_timeout_seconds() -> float:
    return float(os.getenv("JOB_TRACKER_LAGOU_TIMEOUT_SECONDS", str(DEFAULT_LAGOU_TIMEOUT_SECONDS)).strip())


def get_lagou_max_retries() -> int:
    return int(os.getenv("JOB_TRACKER_LAGOU_MAX_RETRIES", str(DEFAULT_LAGOU_MAX_RETRIES)).strip())


def get_lagou_retry_backoff_seconds() -> float:
    return float(
        os.getenv(
            "JOB_TRACKER_LAGOU_RETRY_BACKOFF_SECONDS",
            str(DEFAULT_LAGOU_RETRY_BACKOFF_SECONDS),
        ).strip()
    )


def get_company_allowlist() -> set[str]:
    raw = os.getenv("JOB_TRACKER_COMPANY_ALLOWLIST", "").strip()
    if not raw:
        return set()
    return {
        normalize_company_name(item)
        for item in raw.split(",")
        if normalize_company_name(item)
    }


def load_sources() -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    builtin_sources_allowed = os.getenv("JOB_TRACKER_DISABLE_BUILTIN_SOURCES", "0").strip() != "1"
    include_supplemental_sources = os.getenv("JOB_TRACKER_INCLUDE_SUPPLEMENTAL_SOURCES", "0").strip() == "1"
    linkedin_path: Path | None = None
    linkedin_exists = False
    if os.getenv("JOB_TRACKER_INCLUDE_LINKEDIN_MIDDLE_LAYER", "1").strip() == "1":
        linkedin_path = Path(
            os.getenv("JOB_TRACKER_LINKEDIN_JSON_PATH", str(DEFAULT_LINKEDIN_MIDDLE_LAYER_PATH)).strip()
        )
        if not linkedin_path.is_absolute():
            linkedin_path = ROOT / linkedin_path
        linkedin_exists = linkedin_path.exists()
        if linkedin_exists:
            sources.append(
                {
                    "name": "LinkedIn Middle Layer",
                    "type": "linkedin_json",
                    "path": str(linkedin_path),
                    "priority": SOURCE_PRIORITY_BY_CATEGORY["linkedin"],
                    "category": "linkedin",
                }
            )

    # LinkedIn is now the default primary layer. Supplemental ATS/company sources
    # are only added when explicitly enabled, or when LinkedIn input is absent.
    if builtin_sources_allowed and (include_supplemental_sources or not linkedin_exists):
        if DEFAULT_SOURCE_CATALOG_PATH.exists():
            sources.extend(json.loads(DEFAULT_SOURCE_CATALOG_PATH.read_text(encoding="utf-8")))
        else:
            sources.extend(dict(item) for item in BUILTIN_FALLBACK_SOURCES)

    if os.getenv("JOB_TRACKER_INCLUDE_EXPERIMENTAL_LINKEDIN", "0").strip() == "1":
        sources.extend(dict(item) for item in EXPERIMENTAL_LINKEDIN_SOURCES)
    extra_json = os.getenv("JOB_TRACKER_SOURCES_JSON", "").strip()
    extra_path = os.getenv("JOB_TRACKER_SOURCES_PATH", "").strip()

    if extra_json:
        sources.extend(json.loads(extra_json))
    elif extra_path:
        extra_file = Path(extra_path)
        if not extra_file.is_absolute():
            extra_file = ROOT / extra_file
        sources.extend(json.loads(extra_file.read_text(encoding="utf-8")))

    deduped_sources: dict[str, dict[str, Any]] = {}
    for raw_source in sources:
        source = dict(raw_source)
        if source.get("enabled", True) is False:
            continue
        category = source.get("category", "other")
        source.setdefault("priority", SOURCE_PRIORITY_BY_CATEGORY.get(category, SOURCE_PRIORITY_BY_CATEGORY["other"]))
        deduped_sources[source["name"]] = source

    return list(deduped_sources.values())


def parse_entry_datetime(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=UTC)
            except Exception:
                pass

    for key in ("published", "updated", "created", "pubDate"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            parsed = date_parser.parse(raw)
        except Exception:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


def strip_html(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def canonicalize_url(raw_url: str) -> str:
    if not raw_url:
        return ""
    try:
        parsed = urlparse(raw_url)
    except Exception:
        return raw_url.strip()

    query_items = []
    for item in parsed.query.split("&"):
        if not item:
            continue
        key = item.split("=", 1)[0].lower()
        if key.startswith("utm_") or key in {"trk", "trackingid", "ref", "refid"}:
            continue
        query_items.append(item)

    cleaned = parsed._replace(query="&".join(query_items), fragment="")
    return urlunparse(cleaned).strip()


def load_review_decisions() -> dict[str, str]:
    global REVIEW_DECISION_CACHE
    if REVIEW_DECISION_CACHE is not None:
        return REVIEW_DECISION_CACHE

    review_path = Path(os.getenv("JOB_TRACKER_REVIEW_PACKET_PATH", str(DEFAULT_REVIEW_PACKET_PATH)).strip())
    if not review_path.is_absolute():
        review_path = ROOT / review_path

    decisions: dict[str, str] = {}
    if review_path.exists():
        try:
            payload = json.loads(review_path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    decision = str(item.get("decision") or "").strip().lower()
                    source_matches = item.get("source_matches") or []
                    first_match = source_matches[0] if isinstance(source_matches, list) and source_matches else {}
                    link = canonicalize_url(str(first_match.get("link") or item.get("link") or ""))
                    if link and decision in {"keep", "watch", "drop"}:
                        decisions[link] = decision
        except Exception:
            decisions = {}

    REVIEW_DECISION_CACHE = decisions
    return decisions


def get_review_decision(job: JobPosting) -> str:
    return load_review_decisions().get(canonicalize_url(job.link), "")


def clean_title(raw_title: str) -> str:
    title = strip_html(raw_title)
    title = re.sub(r"\s+", " ", title).strip()
    for suffix in NOISE_SUFFIXES:
        title = re.sub(rf"\s*[\-|–—|]\s*{re.escape(suffix)}$", "", title, flags=re.IGNORECASE)
    return title.strip(" -|")


def normalize_company_name(value: str) -> str:
    if not value:
        return ""
    company = re.sub(r"[()（）\[\]]", " ", value.lower())
    company = re.sub(r"\b(inc|llc|ltd|limited|corp|corporation|co|company)\b\.?", " ", company)
    company = re.sub(r"\s+", " ", company)
    return company.strip()


def normalize_job_title(value: str) -> str:
    title = value.lower()
    title = re.sub(r"\([^)]*\)", " ", title)
    title = re.sub(r"\b(remote|hybrid|onsite|beijing|shanghai|shenzhen|guangzhou|hangzhou|china)\b", " ", title)
    title = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip()


def normalize_location(value: str) -> str:
    location = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", value.lower())
    return re.sub(r"\s+", " ", location).strip()


def location_rank(value: str) -> tuple[int, str]:
    normalized = normalize_location(value)
    for token, rank in LOCATION_PRIORITY.items():
        if token in normalized:
            return rank, normalized
    return 999, normalized


def split_title_company_location(raw_title: str, summary: str) -> tuple[str, str, str]:
    title = clean_title(raw_title)
    summary_text = strip_html(summary)
    company = ""
    location = extract_location(title, summary_text)

    bracket_match = re.match(r"^\[(?P<company>[^\]]+)\]\s*(?P<role>.+)$", title)
    if bracket_match:
        company = bracket_match.group("company").strip(" -|")
        role = bracket_match.group("role").strip(" -|")
        return role, company, location

    match = re.match(r"^(?P<role>.+?)\s+at\s+(?P<company>.+)$", title, flags=re.IGNORECASE)
    if match:
        role = match.group("role").strip(" -|")
        company = match.group("company").strip(" -|")
        return role, company, location

    parts = [part.strip() for part in re.split(r"\s+[|\-–—]\s+", title) if part.strip()]
    if len(parts) >= 2:
        if contains_job_keywords(parts[0]):
            company = parts[1]
            return parts[0], company, location
        if contains_job_keywords(parts[1]):
            company = parts[0]
            return parts[1], company, location

    return title, company, location


def contains_job_keywords(text: str) -> bool:
    haystack = text.lower()
    return any(keyword in haystack for keyword in TITLE_KEYWORDS)


def has_ai_context_signal(job: JobPosting) -> bool:
    haystack = " ".join(
        [
            job.title or "",
            strip_html(job.summary or ""),
            job.company or "",
        ]
    ).lower()
    return any(re.search(pattern, haystack) for pattern in AI_CONTEXT_PATTERNS)


def is_ai_context_company(job: JobPosting) -> bool:
    company = normalize_company_name(job.company)
    return any(keyword in company for keyword in AI_COMPANY_KEYWORDS)


def has_weak_ai_context_signal(job: JobPosting) -> bool:
    haystack = " ".join(
        [
            job.title or "",
            strip_html(job.summary or ""),
            job.company or "",
        ]
    ).lower()
    return any(re.search(pattern, haystack) for pattern in WEAK_AI_CONTEXT_PATTERNS)


def is_generic_pm_without_ai_context(job: JobPosting) -> bool:
    title = normalize_job_title(job.title)
    generic_pm_patterns = (
        r"\bproduct manager\b",
        r"\bsenior product manager\b",
        r"\bstaff product manager\b",
        r"\bsoftware product manager\b",
        r"\bdigital product manager\b",
        r"\bproduct owner\b",
        r"\bproduct lead\b",
        r"\bprogram manager\b",
        r"产品经理",
        r"高级产品经理",
        r"资深产品经理",
        r"产品负责人",
    )
    if not any(re.search(pattern, title) for pattern in generic_pm_patterns):
        return False

    title_has_ai_signal = any(re.search(pattern, title) for pattern in AI_CONTEXT_PATTERNS)
    return not title_has_ai_signal


def extract_location(title: str, summary: str) -> str:
    haystack = f"{title} {summary}".lower()
    for hint in LOCATION_HINTS:
        if hint in haystack:
            return hint.title() if hint != "remote" else "Remote"
    for pattern in (
        r"\b(beijing|shanghai|shenzhen|guangzhou|hangzhou|hong kong|singapore)\b",
        r"\b(北京|上海|深圳|广州|杭州|香港|新加坡)\b",
    ):
        match = re.search(pattern, haystack)
        if match:
            return match.group(1)
    return ""


def parse_datetime_string(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = date_parser.parse(raw)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_datetime_ms(raw: int | float | None) -> datetime | None:
    if raw is None:
        return None
    try:
        return datetime.fromtimestamp(float(raw) / 1000, tz=UTC)
    except Exception:
        return None


def extract_json_script(html_text: str, script_id: str) -> dict[str, Any] | None:
    pattern = rf'<script[^>]+id="{re.escape(script_id)}"[^>]*>(.*?)</script>'
    match = re.search(pattern, html_text, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except Exception:
        return None


def fetch_html_with_retries(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
    max_retries: int,
    backoff_seconds: float,
) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = session.get(
                url,
                params=params,
                timeout=timeout,
                headers=headers,
                allow_redirects=True,
            )
            response.raise_for_status()
            return response
        except Exception as exc:
            last_error = exc
            if attempt == max_retries - 1:
                break
            time.sleep(backoff_seconds * (attempt + 1))
    assert last_error is not None
    raise last_error


def is_target_job(job: JobPosting) -> bool:
    title = job.title.lower()
    if any(re.search(pattern, title) for pattern in NEGATIVE_TITLE_PATTERNS):
        return False
    if not any(re.search(pattern, title) for pattern in TARGET_ROLE_PATTERNS):
        return False
    if is_generic_pm_without_ai_context(job):
        return has_ai_context_signal(job) or has_weak_ai_context_signal(job) or is_ai_context_company(job)
    return True


def is_target_location(job: JobPosting) -> bool:
    region_scope = os.getenv("JOB_TRACKER_REGION_SCOPE", DEFAULT_REGION_SCOPE).strip().lower()
    if region_scope in {"", "global", "off"}:
        return True

    haystack = " ".join(
        [
            job.location or "",
            job.title or "",
            job.summary or "",
        ]
    ).lower()

    if any(token in haystack for token in TARGET_LOCATION_TOKENS):
        return True

    has_remote = any(token in haystack for token in REMOTE_LOCATION_TOKENS)
    has_apac_hint = any(token in haystack for token in REMOTE_APAC_HINTS)
    if has_remote and has_apac_hint:
        return True

    source_type = (job.source_type or "").strip().lower()
    if source_type in SOFT_REGION_SOURCE_TYPES:
        return True

    if source_type in STRICT_REGION_SOURCE_TYPES:
        return False

    if region_scope in {"asia_focus", "target_core"}:
        return False

    return False


def is_target_company(job: JobPosting) -> bool:
    allowlist = get_company_allowlist()
    if not allowlist:
        return True
    return normalize_company_name(job.company) in allowlist


def should_keep_job(job: JobPosting) -> bool:
    review_decision = get_review_decision(job)
    if review_decision == "drop":
        return False
    if review_decision in {"keep", "watch"}:
        return is_target_location(job) and is_target_company(job)
    return is_target_job(job) and is_target_location(job) and is_target_company(job)


def fetch_rss_source(source: dict[str, Any], session: requests.Session, cutoff: datetime) -> list[JobPosting]:
    response = session.get(
        source["url"],
        timeout=get_timeout_seconds(),
        headers={"User-Agent": "JobTracker/1.0"},
        allow_redirects=True,
    )
    response.raise_for_status()
    parsed = feedparser.parse(response.content)

    jobs: list[JobPosting] = []
    for entry in parsed.entries:
        published_at = parse_entry_datetime(entry)
        if not published_at or published_at < cutoff:
            continue

        raw_link = entry.get("link") or entry.get("guid") or ""
        link = canonicalize_url(raw_link)
        if not link:
            continue

        raw_title = entry.get("title") or "Untitled"
        summary = strip_html(entry.get("summary") or entry.get("contentSnippet") or entry.get("description") or "")
        title, company, location = split_title_company_location(raw_title, summary)

        job = JobPosting(
            title=title,
            company=company,
            location=location,
            summary=summary,
            link=link,
            published_at=published_at,
            source=source["name"],
            source_type=source.get("type", "rss"),
            source_priority=int(source.get("priority", 0)),
        )
        if should_keep_job(job):
            jobs.append(job)

    return jobs


def fetch_greenhouse_source(source: dict[str, Any], session: requests.Session, cutoff: datetime) -> list[JobPosting]:
    board_token = source["board_token"]
    response = session.get(
        f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs",
        params={"content": "true"},
        timeout=get_timeout_seconds(),
        headers={"User-Agent": "JobTracker/1.0"},
        allow_redirects=True,
    )
    response.raise_for_status()
    payload = response.json()

    jobs: list[JobPosting] = []
    for entry in payload.get("jobs", []):
        published_at = parse_datetime_string(entry.get("updated_at")) or parse_datetime_string(entry.get("first_published"))
        if not published_at or published_at < cutoff:
            continue

        title = clean_title(entry.get("title") or "Untitled")
        company = source.get("company") or entry.get("company_name") or ""
        location = (entry.get("location") or {}).get("name", "")
        summary = strip_html(entry.get("content") or "")
        link = canonicalize_url(entry.get("absolute_url") or "")
        if not link:
            continue

        job = JobPosting(
            title=title,
            company=company,
            location=location,
            summary=summary,
            link=link,
            published_at=published_at,
            source=source["name"],
            source_type="greenhouse",
            source_priority=int(source.get("priority", 0)),
        )
        if should_keep_job(job):
            jobs.append(job)

    return jobs


def fetch_lever_source(source: dict[str, Any], session: requests.Session, cutoff: datetime) -> list[JobPosting]:
    company_slug = source["company_slug"]
    response = session.get(
        f"https://api.lever.co/v0/postings/{company_slug}",
        params={"mode": "json"},
        timeout=get_timeout_seconds(),
        headers={"User-Agent": "JobTracker/1.0"},
        allow_redirects=True,
    )
    response.raise_for_status()
    payload = response.json()

    jobs: list[JobPosting] = []
    for entry in payload:
        published_at = parse_datetime_ms(entry.get("createdAt"))
        if not published_at or published_at < cutoff:
            continue

        title = clean_title(entry.get("text") or "Untitled")
        company = source.get("company", company_slug)
        location = ((entry.get("categories") or {}).get("location") or "").strip()
        summary = strip_html(entry.get("descriptionPlain") or entry.get("description") or "")
        link = canonicalize_url(entry.get("hostedUrl") or entry.get("applyUrl") or "")
        if not link:
            continue

        job = JobPosting(
            title=title,
            company=company,
            location=location,
            summary=summary,
            link=link,
            published_at=published_at,
            source=source["name"],
            source_type="lever",
            source_priority=int(source.get("priority", 0)),
        )
        if should_keep_job(job):
            jobs.append(job)

    return jobs


def fetch_lagou_source(source: dict[str, Any], session: requests.Session, cutoff: datetime) -> list[JobPosting]:
    keyword = source["keyword"]
    city = source.get("city", "全国")
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    params = {"kd": keyword, "city": city}
    timeout = get_lagou_timeout_seconds()
    retries = get_lagou_max_retries()
    backoff = get_lagou_retry_backoff_seconds()

    response: requests.Response | None = None
    next_data: dict[str, Any] = {}
    for url in (
        "https://www.lagou.com/wn/jobs",
        "https://www.lagou.com/wn/zhaopin",
    ):
        response = fetch_html_with_retries(
            session,
            url,
            params=params,
            headers=headers,
            timeout=timeout,
            max_retries=retries,
            backoff_seconds=backoff,
        )
        next_data = extract_json_script(response.text, "__NEXT_DATA__") or {}
        if next_data:
            break

    page_props = (
        next_data.get("props", {})
        .get("pageProps", {})
    )
    positions = (
        page_props.get("positionResult", {})
        .get("result", [])
    )

    jobs: list[JobPosting] = []
    for entry in positions:
        published_at = parse_datetime_string(entry.get("createTime"))
        if not published_at or published_at < cutoff:
            continue

        title = clean_title(entry.get("positionName") or "Untitled")
        company = (entry.get("companyShortName") or entry.get("companyFullName") or "").strip()
        location = (entry.get("city") or "").strip()
        summary = strip_html(entry.get("positionDetail") or "")

        position_id = entry.get("positionId")
        encrypt_id = entry.get("encryptId")
        link = ""
        if position_id:
            link = canonicalize_url(f"https://www.lagou.com/wn/jobs/{position_id}.html")
        elif encrypt_id:
            link = canonicalize_url(f"https://www.lagou.com/wn/jobs/{encrypt_id}.html")
        if not link:
            continue

        job = JobPosting(
            title=title,
            company=company,
            location=location,
            summary=summary,
            link=link,
            published_at=published_at,
            source=source["name"],
            source_type="lagou",
            source_priority=int(source.get("priority", 0)),
        )
        if should_keep_job(job):
            jobs.append(job)

    return jobs


def fetch_linkedin_json_source(source: dict[str, Any], cutoff: datetime) -> list[JobPosting]:
    source_path = Path(source["path"])
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    raw_jobs = payload.get("jobs", []) if isinstance(payload, dict) else payload

    jobs: list[JobPosting] = []
    latest_published_at: datetime | None = None
    recent_raw_count = 0
    for entry in raw_jobs:
        if not isinstance(entry, dict):
            continue

        published_at = parse_datetime_string(str(entry.get("published_at") or ""))
        if published_at and (latest_published_at is None or published_at > latest_published_at):
            latest_published_at = published_at
        if not published_at or published_at < cutoff:
            continue
        recent_raw_count += 1

        title = clean_title(str(entry.get("title") or "Untitled"))
        company = strip_html(str(entry.get("company") or "")).strip()
        location = strip_html(str(entry.get("location") or "")).strip()
        summary = strip_html(str(entry.get("summary") or "")).strip()
        link = canonicalize_url(str(entry.get("link") or ""))
        if not link:
            continue

        job = JobPosting(
            title=title,
            company=company,
            location=location,
            summary=summary,
            link=link,
            published_at=published_at,
            source=str(entry.get("source") or source["name"]).strip() or source["name"],
            source_type="linkedin_json",
            source_priority=int(source.get("priority", SOURCE_PRIORITY_BY_CATEGORY["linkedin"])),
        )
        if should_keep_job(job):
            jobs.append(job)

    if latest_published_at and latest_published_at < cutoff:
        print(
            (
                f"Warning: {source['name']} has no records within the current lookback window. "
                f"Latest sample is {latest_published_at.date().isoformat()} from {source_path}."
            ),
            file=sys.stderr,
        )
    elif recent_raw_count > 0 and not jobs:
        print(
            (
                f"Warning: {source['name']} has {recent_raw_count} recent records in {source_path}, "
                "but none survived the current filters."
            ),
            file=sys.stderr,
        )

    return jobs


def fetch_jobs(lookback_days: int) -> list[JobPosting]:
    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    session = requests.Session()
    session.trust_env = False

    jobs: list[JobPosting] = []
    for source in load_sources():
        source_type = source.get("type", "greenhouse")
        try:
            if source_type == "rss":
                jobs.extend(fetch_rss_source(source, session, cutoff))
            elif source_type == "greenhouse":
                jobs.extend(fetch_greenhouse_source(source, session, cutoff))
            elif source_type == "lever":
                jobs.extend(fetch_lever_source(source, session, cutoff))
            elif source_type == "lagou":
                jobs.extend(fetch_lagou_source(source, session, cutoff))
            elif source_type == "linkedin_json":
                jobs.extend(fetch_linkedin_json_source(source, cutoff))
            else:
                print(f"Warning: unsupported source type {source_type} for {source['name']}, skipping.", file=sys.stderr)
        except Exception as exc:
            print(f"Warning: failed to fetch {source['name']}: {exc}", file=sys.stderr)

    jobs.sort(key=lambda item: (item.source_priority, item.published_at), reverse=True)
    return jobs


def dedupe_by_link(jobs: list[JobPosting]) -> list[JobPosting]:
    deduped: dict[str, JobPosting] = {}
    for job in jobs:
        deduped.setdefault(job.link, job)
    return list(deduped.values())


def build_company_role_key(job: JobPosting) -> tuple[str, str, str] | None:
    company = normalize_company_name(job.company)
    title = normalize_job_title(job.title)
    location = normalize_location(job.location)
    if not company or not title:
        return None
    return company, title, location


def dedupe_cross_source(jobs: list[JobPosting]) -> list[JobPosting]:
    merged: dict[tuple[str, str], JobPosting] = {}
    passthrough: list[JobPosting] = []

    for job in jobs:
        role_key = build_company_role_key(job)
        if role_key is None:
            passthrough.append(job)
            continue
        company_key, title_key, _ = role_key
        key = (company_key, title_key)
        existing = merged.get(key)
        if existing is None:
            merged[key] = job
            continue

        existing_rank = location_rank(existing.location)
        candidate_rank = location_rank(job.location)
        if candidate_rank < existing_rank:
            merged[key] = job
            continue
        if candidate_rank == existing_rank:
            if job.source_priority > existing.source_priority:
                merged[key] = job
                continue
            if job.source_priority == existing.source_priority and job.published_at > existing.published_at:
                merged[key] = job

    combined = list(merged.values()) + passthrough
    combined.sort(
        key=lambda item: (
            item.company_sort_key,
            normalize_job_title(item.title),
            -item.source_priority,
            -item.published_at.timestamp(),
        )
    )
    return combined


def apply_role_quotas(jobs: list[JobPosting]) -> list[JobPosting]:
    engineering_cap = int(os.getenv("JOB_TRACKER_ENGINEERING_ROLE_CAP", str(DEFAULT_ENGINEERING_ROLE_CAP)).strip())
    engineering_share_cap = float(
        os.getenv("JOB_TRACKER_ENGINEERING_SHARE_CAP", str(DEFAULT_ENGINEERING_SHARE_CAP)).strip()
    )
    engineering_per_company_cap = int(
        os.getenv("JOB_TRACKER_ENGINEERING_PER_COMPANY_CAP", str(DEFAULT_ENGINEERING_PER_COMPANY_CAP)).strip()
    )
    non_engineering_per_company_cap = int(
        os.getenv("JOB_TRACKER_NON_ENGINEERING_PER_COMPANY_CAP", str(DEFAULT_NON_ENGINEERING_PER_COMPANY_CAP)).strip()
    )

    engineering_jobs = [job for job in jobs if job.is_engineering_role]
    non_engineering_jobs = [job for job in jobs if not job.is_engineering_role]

    engineering_jobs.sort(
        key=lambda item: (
            location_rank(item.location),
            -item.source_priority,
            -item.published_at.timestamp(),
            item.company_sort_key,
        )
    )
    non_engineering_jobs.sort(
        key=lambda item: (
            item.company_sort_key,
            location_rank(item.location),
            -item.source_priority,
            -item.published_at.timestamp(),
        )
    )

    selected_non_engineering: list[JobPosting] = []
    non_engineering_counts: dict[str, int] = {}
    for job in non_engineering_jobs:
        company_key = job.company_sort_key
        if non_engineering_counts.get(company_key, 0) >= non_engineering_per_company_cap:
            continue
        selected_non_engineering.append(job)
        non_engineering_counts[company_key] = non_engineering_counts.get(company_key, 0) + 1

    max_engineering_by_share = max(1, int((len(selected_non_engineering) + len(engineering_jobs)) * engineering_share_cap))
    engineering_limit = min(engineering_cap, max_engineering_by_share)

    selected_engineering: list[JobPosting] = []
    engineering_counts: dict[str, int] = {}
    for job in engineering_jobs:
        if len(selected_engineering) >= engineering_limit:
            break
        company_key = job.company_sort_key
        if engineering_counts.get(company_key, 0) >= engineering_per_company_cap:
            continue
        selected_engineering.append(job)
        engineering_counts[company_key] = engineering_counts.get(company_key, 0) + 1

    combined = selected_non_engineering + selected_engineering
    combined.sort(
        key=lambda item: (
            item.company_sort_key,
            1 if item.is_engineering_role else 0,
            location_rank(item.location),
            normalize_job_title(item.title),
            -item.source_priority,
        )
    )
    return combined


def extract_json_blob(text: str) -> dict[str, Any]:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    object_match = re.search(r"(\{.*\})", text, flags=re.DOTALL)
    if object_match:
        return json.loads(object_match.group(1))

    raise json.JSONDecodeError("No JSON object found in model output.", text, 0)


def clamp_summary_for_llm(text: str) -> str:
    max_chars = int(
        os.getenv(
            "JOB_TRACKER_LLM_SUMMARY_MAX_CHARS",
            os.getenv("JOB_TRACKER_GLM_SUMMARY_MAX_CHARS", os.getenv("JOB_TRACKER_GEMINI_SUMMARY_MAX_CHARS", str(DEFAULT_LLM_SUMMARY_MAX_CHARS))),
        ).strip()
    )
    cleaned = strip_html(text)
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rsplit(" ", 1)[0].strip() + " ..."


def should_use_llm(job: JobPosting, existing_links: set[str]) -> bool:
    only_new = os.getenv(
        "JOB_TRACKER_LLM_ONLY_NEW",
        os.getenv("JOB_TRACKER_GLM_ONLY_NEW", os.getenv("JOB_TRACKER_GEMINI_ONLY_NEW", "1")),
    ).strip()
    if only_new == "1" and job.link in existing_links:
        return False

    title = job.title.lower()
    summary = strip_html(job.summary).lower()
    haystack = f"{title} {summary}"

    direct_priority_tokens = (
        "product manager",
        "product lead",
        "program manager",
        "project manager",
        "operations manager",
        "operations lead",
        "product ops",
        "business operations",
        "strategy and operations",
        "bizops",
        "agent",
        "agentic",
        "ai native",
        "genai",
        "llm",
        "multi-agent",
        "multi agent",
    )
    if any(token in haystack for token in direct_priority_tokens):
        return True

    if not job.is_engineering_role:
        return True

    engineering_upgrade_tokens = (
        "product roadmap",
        "roadmap",
        "customer",
        "customer-facing",
        "workflow",
        "workflows",
        "customer shaping",
        "go-to-market",
        "gtm",
        "cross-functional",
        "cross functional",
        "stakeholder",
        "agent",
        "agentic",
        "llm",
        "genai",
        "multi-agent",
        "multi agent",
    )
    return any(token in haystack for token in engineering_upgrade_tokens)


def build_analysis_prompt(job: JobPosting) -> str:
    clipped_summary = clamp_summary_for_llm(job.summary)
    return f"""You are reviewing a job posting for someone transitioning into AI product management with agent project experience.

Return JSON only with this exact schema:
{{
  "required_skills": ["skill 1", "skill 2"],
  "years_of_experience": "string",
  "mentions_agent": true,
  "mentions_ai_native": false,
  "relevance_score": 0.0,
  "keywords_summary": "short summary"
}}

Rules:
- required_skills: 3 to 8 concise items, deduplicated.
- years_of_experience: return the explicit requirement if present, otherwise "Not specified".
- mentions_agent: true only if the job explicitly mentions agent, agents, agentic, or a very close equivalent.
- mentions_ai_native: true only if the job explicitly mentions AI native or clearly describes the role/product as AI native.
- relevance_score must be a float between 0.0 and 1.0.
- Treat these as strong AI-native platform signals even if the exact words "AI native" do not appear:
  - multi-LLM platform / model hub / model aggregation
  - AI router / smart routing / traffic routing across models
  - LLM platform infrastructure / agent platform / model gateway
  - token metering / AI billing / standardized model APIs
- If the role owns an AI platform, model routing layer, model aggregation layer, or agent platform, mentions_ai_native should usually be true.
- If the role explicitly mentions agent, agents, agentic platform, agent workflow, or intelligent agents, mentions_agent should be true.
- Use this relevance logic for someone transitioning into AI Product Management with agent project experience:
  - Do not automatically score Program Manager roles lower than Product Manager roles. Judge by actual scope and responsibilities.
  - Do not penalize Public Sector, Defense, or Clearance-related roles, because this user has government work experience.
  - Forward Deployed Engineer roles are relevant but should generally not exceed 0.75 unless they show unusually strong product ownership, strategy, or customer-shaping responsibilities.
  - Applied AI Engineer roles do not need an artificial cap; score them based on actual fit.
  - Multi-LLM platform, model router, agent platform, AI infrastructure platform, and AI monetization platform PM roles are usually high-fit roles, often in the 0.85 to 1.0 range when ownership is clear.
  - 0.85 to 1.0 = highly relevant direct fit
  - 0.65 to 0.84 = strong adjacent fit
  - 0.4 to 0.64 = useful but not primary fit
  - 0.0 to 0.39 = low fit
- keywords_summary: one short line combining the skills and fit.

Job title: {job.title}
Company: {job.company or "Unknown"}
Location: {job.location or "Unknown"}
Summary: {clipped_summary or "No summary provided"}
"""


def build_llm_session() -> requests.Session:
    session = requests.Session()
    disable_proxy = os.getenv("DISABLE_SYSTEM_PROXY", "").strip().lower() in {"1", "true", "yes", "on"}
    if disable_proxy:
        session.trust_env = False
    return session


def normalize_chat_endpoint(raw_base_url: str) -> str:
    base_url = raw_base_url.strip().rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def apply_analysis_payload(job: JobPosting, payload: dict[str, Any]) -> None:
    skills = payload.get("required_skills") or []
    if not isinstance(skills, list):
        skills = [str(skills)]

    try:
        score = float(payload.get("relevance_score", 0.5))
    except Exception:
        score = 0.5
    score = min(1.0, max(0.0, score))

    job.required_skills = [str(item).strip() for item in skills if str(item).strip()]
    job.years_of_experience = str(payload.get("years_of_experience") or "Not specified").strip()
    job.mentions_agent = bool(payload.get("mentions_agent"))
    job.mentions_ai_native = bool(payload.get("mentions_ai_native"))
    job.relevance_score = score
    job.keywords = str(payload.get("keywords_summary") or "").strip()


class GLMRateLimitError(RuntimeError):
    pass


def is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc)
    return "429" in text or "Too Many Requests" in text


def analyze_job_with_glm(job: JobPosting, model: str) -> None:
    glm_api_key = required_env("GLM_API_KEY")
    glm_base_url = required_env("GLM_BASE_URL")
    prompt = build_analysis_prompt(job)
    payload: dict[str, Any] | None = None
    last_error: Exception | None = None

    retry_backoff_seconds = float(
        os.getenv("JOB_TRACKER_GLM_RETRY_BACKOFF_SECONDS", str(DEFAULT_GLM_RETRY_BACKOFF_SECONDS)).strip()
    )

    for attempt in range(3):
        session = build_llm_session()
        try:
            response = session.post(
                normalize_chat_endpoint(glm_base_url),
                headers={
                    "Authorization": f"Bearer {glm_api_key}",
                    "Content-Type": "application/json",
                    "Accept-Language": "en-US,en",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You extract structured hiring signals from job postings."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                },
                timeout=120.0,
            )
            response.raise_for_status()
            response_payload = response.json()
            choices = response_payload.get("choices") or []
            if not choices:
                raise ValueError(f"No choices in GLM response: {response_payload}")
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            payload = extract_json_blob(str(content))
            break
        except (requests.RequestException, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if is_rate_limit_error(exc):
                raise GLMRateLimitError(str(exc)) from exc
            if attempt < 2:
                time.sleep(retry_backoff_seconds * (attempt + 1))
                continue
            raise

    if payload is None:
        assert last_error is not None
        raise last_error

    apply_analysis_payload(job, payload)


def analyze_job_with_heuristics(job: JobPosting) -> None:
    haystack = f"{job.title} {job.summary}".lower()
    skills = []
    for keyword in (
        "sql",
        "python",
        "analytics",
        "experimentation",
        "roadmap",
        "stakeholder",
        "llm",
        "agent",
        "automation",
        "api",
    ):
        if keyword in haystack:
            skills.append(keyword)

    experience_match = re.search(r"(\d+\+?\s*(?:-|to)?\s*\d*\+?\s*years?)", haystack)
    mentions_agent = any(token in haystack for token in (" agent ", " agents ", "agentic"))
    mentions_ai_native = "ai native" in haystack or "ai-native" in haystack

    score = 0.25
    if any(token in haystack for token in ("product manager", "product management", "technical product manager", "ai pm")):
        score = 0.75
    if any(token in haystack for token in ("program manager", "project manager", "operations manager", "operations lead")):
        score = max(score, 0.6)
    if any(token in haystack for token in ("agent engineer", "agentic engineer", "applied ai engineer", "ai engineer", "forward deployed engineer")):
        score = max(score, 0.45)
    if any(token in haystack for token in ("agent", "llm", "genai", "artificial intelligence", "ai")):
        score = min(1.0, score + 0.15)
    if "forward deployed engineer" in haystack:
        score = min(score, 0.75)

    job.required_skills = skills[:8]
    job.years_of_experience = experience_match.group(1) if experience_match else "Not specified"
    job.mentions_agent = mentions_agent
    job.mentions_ai_native = mentions_ai_native
    job.relevance_score = score
    job.keywords = build_keywords(job)


def analyze_jobs(jobs: list[JobPosting], skip_analysis: bool, existing_links: set[str] | None = None) -> None:
    if skip_analysis:
        for job in jobs:
            job.required_skills = []
            job.years_of_experience = "Skipped"
            job.mentions_agent = False
            job.mentions_ai_native = False
            job.relevance_score = 0
            job.keywords = "Analysis skipped"
        return

    existing_links = existing_links or set()
    model = os.getenv(
        "GLM_MODEL",
        os.getenv("JOB_TRACKER_GLM_MODEL", os.getenv("JOB_TRACKER_GEMINI_MODEL", DEFAULT_GLM_MODEL)),
    ).strip() or DEFAULT_GLM_MODEL
    remaining_llm_calls = int(
        os.getenv(
            "JOB_TRACKER_LLM_MAX_JOBS",
            os.getenv("JOB_TRACKER_GLM_MAX_JOBS", os.getenv("JOB_TRACKER_GEMINI_MAX_JOBS", str(DEFAULT_GLM_MAX_JOBS))),
        ).strip()
    )
    request_interval_seconds = float(
        os.getenv("JOB_TRACKER_GLM_REQUEST_INTERVAL_SECONDS", str(DEFAULT_GLM_REQUEST_INTERVAL_SECONDS)).strip()
    )
    rate_limit_cooldown_seconds = float(
        os.getenv("JOB_TRACKER_GLM_RATE_LIMIT_COOLDOWN_SECONDS", str(DEFAULT_GLM_RATE_LIMIT_COOLDOWN_SECONDS)).strip()
    )
    llm_rate_limited = False
    for index, job in enumerate(jobs, start=1):
        if not llm_rate_limited and remaining_llm_calls > 0 and should_use_llm(job, existing_links):
            print(f"Analyzing job {index}/{len(jobs)}: {job.company or 'Unknown company'} - {job.title}", file=sys.stderr)
            try:
                analyze_job_with_glm(job, model)
                remaining_llm_calls -= 1
            except GLMRateLimitError as exc:
                print(
                    f"Warning: GLM rate limit hit for {job.link}: {exc}. Cooling down and falling back to heuristics for the remaining jobs in this run.",
                    file=sys.stderr,
                )
                analyze_job_with_heuristics(job)
                llm_rate_limited = True
                time.sleep(rate_limit_cooldown_seconds)
            except Exception as exc:
                print(f"Warning: GLM analysis failed for {job.link}: {exc}. Falling back to heuristics.", file=sys.stderr)
                analyze_job_with_heuristics(job)
            time.sleep(request_interval_seconds)
            continue

        print(
            f"Skipping LLM for {index}/{len(jobs)}: {job.company or 'Unknown company'} - {job.title}",
            file=sys.stderr,
        )
        try:
            analyze_job_with_heuristics(job)
        except Exception as exc:
            print(f"Warning: heuristic analysis failed for {job.link}: {exc}. Marking as skipped.", file=sys.stderr)
            job.required_skills = []
            job.years_of_experience = "Skipped"
            job.mentions_agent = False
            job.mentions_ai_native = False
            job.relevance_score = 0
            job.keywords = "Analysis skipped"


def datetime_to_feishu_ms(value: datetime) -> int:
    return int(value.astimezone(UTC).timestamp() * 1000)


def build_keywords(job: JobPosting) -> str:
    parts: list[str] = []
    if job.required_skills:
        parts.append("skills: " + ", ".join(job.required_skills))
    if job.years_of_experience:
        parts.append(f"yoe: {job.years_of_experience}")
    if job.mentions_agent is not None:
        parts.append("agent: yes" if job.mentions_agent else "agent: no")
    if job.mentions_ai_native is not None:
        parts.append("ai native: yes" if job.mentions_ai_native else "ai native: no")
    if job.keywords:
        parts.append(job.keywords)
    return " | ".join(parts)


def to_feishu_fields(job: JobPosting) -> dict[str, Any]:
    return {
        "Title": job.title,
        "Company": job.company,
        "Location": job.location,
        "Summary": job.summary,
        "Link": job.link,
        "Published Date": datetime_to_feishu_ms(job.published_at),
        "Source": job.source,
        "Required Skills": ", ".join(job.required_skills or []),
        "Years of Experience": job.years_of_experience or "Not specified",
        "Mentions Agent": "Yes" if job.mentions_agent else "No",
        "Mentions AI Native": "Yes" if job.mentions_ai_native else "No",
        "Relevance Score": round(float(job.relevance_score or 0.0), 2),
        "Keywords": build_keywords(job),
        "Status": "New",
    }


class FeishuBitableClient:
    def __init__(self) -> None:
        self.base_url = "https://open.feishu.cn/open-apis"
        self.app_id = required_env("FEISHU_APP_ID")
        self.app_secret = required_env("FEISHU_APP_SECRET")
        self.app_token = required_env("FEISHU_BITABLE_APP_TOKEN")
        self.table_id = required_env("FEISHU_BITABLE_TABLE_ID")
        self.session = requests.Session()
        self.session.trust_env = False
        self._tenant_access_token: str | None = None

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        headers = kwargs.pop("headers", {})
        if path != "/auth/v3/tenant_access_token/internal":
            headers["Authorization"] = f"Bearer {self.get_tenant_access_token()}"
        headers["Content-Type"] = "application/json; charset=utf-8"
        response = self.session.request(
            method=method,
            url=f"{self.base_url}{path}",
            headers=headers,
            timeout=get_timeout_seconds(),
            **kwargs,
        )
        response.raise_for_status()
        payload = response.json()
        code = payload.get("code", 0)
        if code not in (0, None):
            raise RuntimeError(f"Feishu API error {code}: {payload.get('msg')}")
        return response

    def get_tenant_access_token(self) -> str:
        if self._tenant_access_token:
            return self._tenant_access_token
        response = self._request(
            "POST",
            "/auth/v3/tenant_access_token/internal",
            data=json.dumps({"app_id": self.app_id, "app_secret": self.app_secret}),
        )
        self._tenant_access_token = response.json()["tenant_access_token"]
        return self._tenant_access_token

    def list_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_token = ""
        while True:
            params = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            response = self._request(
                "GET",
                f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records",
                params=params,
            )
            data = response.json()["data"]
            records.extend(data.get("items", []))
            if not data.get("has_more"):
                break
            page_token = data.get("page_token", "")
            if not page_token:
                break
        return records

    def create_record(self, fields: dict[str, Any]) -> None:
        self._request(
            "POST",
            f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records",
            data=json.dumps({"fields": fields}, ensure_ascii=False),
        )

    def update_record(self, record_id: str, fields: dict[str, Any]) -> None:
        self._request(
            "PUT",
            f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/{record_id}",
            data=json.dumps({"fields": fields}, ensure_ascii=False),
        )


def chunk_text(value: str, limit: int = 1900) -> list[dict[str, Any]]:
    text = (value or "").strip()
    if not text:
        return []
    chunks = [text[index : index + limit] for index in range(0, len(text), limit)]
    return [{"type": "text", "text": {"content": chunk}} for chunk in chunks]


def to_notion_properties(job: JobPosting) -> dict[str, Any]:
    return {
        "Title": {"title": chunk_text(job.title, limit=1800)},
        "Company": {"rich_text": chunk_text(job.company)},
        "Location": {"rich_text": chunk_text(job.location)},
        "Summary": {"rich_text": chunk_text(job.summary)},
        "Link": {"url": job.link},
        "Published Date": {"date": {"start": job.published_at.astimezone(UTC).isoformat()}},
        "Source": {"rich_text": chunk_text(job.source)},
        "Required Skills": {"rich_text": chunk_text(", ".join(job.required_skills or []))},
        "Years of Experience": {"rich_text": chunk_text(job.years_of_experience or "Not specified")},
        "Mentions Agent": {"select": {"name": "Yes" if job.mentions_agent else "No"}},
        "Mentions AI Native": {"select": {"name": "Yes" if job.mentions_ai_native else "No"}},
        "Relevance Score": {"number": round(float(job.relevance_score or 0.0), 2)},
        "Keywords": {"rich_text": chunk_text(build_keywords(job))},
        "Status": {"select": {"name": "New"}},
    }


class NotionDatabaseClient:
    def __init__(self) -> None:
        self.base_url = "https://api.notion.com/v1"
        self.api_key = required_env("NOTION_API_KEY")
        self.database_id = required_env("NOTION_DATABASE_ID")
        self.session = requests.Session()
        self.session.trust_env = False

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.api_key}"
        headers["Notion-Version"] = "2022-06-28"
        headers["Content-Type"] = "application/json"
        response = self.session.request(
            method=method,
            url=f"{self.base_url}{path}",
            headers=headers,
            timeout=get_timeout_seconds(),
            **kwargs,
        )
        response.raise_for_status()
        return response.json()

    def list_pages(self) -> list[dict[str, Any]]:
        pages: list[dict[str, Any]] = []
        next_cursor: str | None = None
        while True:
            payload: dict[str, Any] = {"page_size": 100}
            if next_cursor:
                payload["start_cursor"] = next_cursor
            data = self._request(
                "POST",
                f"/databases/{self.database_id}/query",
                data=json.dumps(payload),
            )
            pages.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            next_cursor = data.get("next_cursor")
            if not next_cursor:
                break
        return pages

    def create_page(self, properties: dict[str, Any]) -> None:
        self._request(
            "POST",
            "/pages",
            data=json.dumps(
                {
                    "parent": {"database_id": self.database_id},
                    "properties": properties,
                },
                ensure_ascii=False,
            ),
        )

    def update_page(self, page_id: str, properties: dict[str, Any]) -> None:
        self._request(
            "PATCH",
            f"/pages/{page_id}",
            data=json.dumps({"properties": properties}, ensure_ascii=False),
        )


def extract_notion_url(page: dict[str, Any], property_name: str) -> str:
    prop = (page.get("properties") or {}).get(property_name) or {}
    if prop.get("type") == "url":
        return str(prop.get("url") or "").strip()
    return ""


def list_existing_notion_links() -> set[str]:
    if not os.getenv("NOTION_API_KEY", "").strip() or not os.getenv("NOTION_DATABASE_ID", "").strip():
        return set()
    client = NotionDatabaseClient()
    links: set[str] = set()
    for page in client.list_pages():
        link = canonicalize_url(extract_notion_url(page, "Link"))
        if link:
            links.add(link)
    return links


def sync_to_notion(jobs: list[JobPosting], dry_run: bool) -> tuple[int, int]:
    if dry_run:
        return 0, 0

    client = NotionDatabaseClient()
    existing_by_link: dict[str, dict[str, Any]] = {}
    for page in client.list_pages():
        link = canonicalize_url(extract_notion_url(page, "Link"))
        if link:
            existing_by_link[link] = page

    created = 0
    updated = 0
    for job in jobs:
        properties = to_notion_properties(job)
        existing = existing_by_link.get(job.link)
        if existing:
            client.update_page(existing["id"], properties)
            updated += 1
        else:
            client.create_page(properties)
            created += 1
    return created, updated


def jobs_to_json(jobs: list[JobPosting]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for job in jobs:
        item = asdict(job)
        item["published_at"] = job.published_at.isoformat()
        payload.append(item)
    return payload


def main() -> None:
    load_env()
    args = parse_args()

    if args.lookback_days <= 0:
        raise RuntimeError("--lookback-days must be positive")

    jobs = fetch_jobs(args.lookback_days)
    jobs = dedupe_by_link(jobs)
    jobs = dedupe_cross_source(jobs)
    jobs = apply_role_quotas(jobs)

    if args.max_jobs > 0:
        jobs = jobs[: args.max_jobs]

    existing_links = set()
    if not args.skip_analysis:
        try:
            existing_links = list_existing_notion_links()
        except Exception as exc:
            print(f"Warning: failed to read existing Notion links before analysis: {exc}", file=sys.stderr)
    analyze_jobs(jobs, skip_analysis=args.skip_analysis, existing_links=existing_links)

    if args.output:
        args.output.write_text(json.dumps(jobs_to_json(jobs), ensure_ascii=False, indent=2), encoding="utf-8")

    created, updated = sync_to_notion(jobs, dry_run=args.dry_run)

    print(
        json.dumps(
            {
                "processed_jobs": len(jobs),
                "created_records": created,
                "updated_records": updated,
                "would_sync_records": len(jobs) if args.dry_run else created + updated,
                "lookback_days": args.lookback_days,
                "dry_run": args.dry_run,
                "skip_analysis": args.skip_analysis,
                "default_weekly_cron_utc": DEFAULT_WEEKLY_CRON_UTC,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
