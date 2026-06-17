#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = ROOT.parent.parent
DEFAULT_INPUT_PATH = ROOT / "data" / "job-tracker-60d-preview.json"
DEFAULT_OUTPUT_PATH = ROOT / "data" / "glm-quality-preview.json"
DEFAULT_MODEL = "glm-5.2"
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_RETRIES = 3


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


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def extract_json_blob(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise json.JSONDecodeError("Empty response", text, 0)
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise json.JSONDecodeError("No JSON object found", text, 0)
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise json.JSONDecodeError("Response JSON is not an object", text, start)
    return payload


def build_prompt(job: dict[str, Any]) -> str:
    summary = str(job.get("summary") or "")[:2200]
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
- If the role owns an AI platform, model routing layer, model aggregation layer, or agent platform, `mentions_ai_native` should usually be true.
- If the role explicitly mentions agent, agents, agentic platform, agent workflow, or intelligent agents, `mentions_agent` should be true.
- Use this relevance logic for someone transitioning into AI Product Management with agent project experience:
  - Do not automatically score Program Manager roles lower than Product Manager roles. Judge by actual scope and responsibilities.
  - Do not penalize Public Sector, Defense, or Clearance-related roles, because the user has government work experience.
  - Forward Deployed Engineer roles are relevant but should generally not exceed 0.75 unless they show unusually strong product ownership, strategy, or customer-shaping responsibilities.
  - Applied AI Engineer roles do not need an artificial cap; score them based on actual fit.
  - Multi-LLM platform, model router, agent platform, AI infrastructure platform, and AI monetization platform PM roles are usually high-fit roles, often in the 0.85 to 1.0 range when ownership is clear.
  - 0.85 to 1.0 = highly relevant direct fit
  - 0.65 to 0.84 = strong adjacent fit
  - 0.4 to 0.64 = useful but not primary fit
  - 0.0 to 0.39 = low fit
- keywords_summary: one short line combining the skills and fit.

Job title: {job.get("title") or "Unknown"}
Company: {job.get("company") or "Unknown"}
Location: {job.get("location") or "Unknown"}
Summary: {summary or "No summary provided"}
"""


def normalize_chat_endpoint(raw_base_url: str) -> str:
    base_url = raw_base_url.strip().rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def build_session() -> requests.Session:
    session = requests.Session()
    disable_proxy = os.getenv("DISABLE_SYSTEM_PROXY", "").strip().lower() in {"1", "true", "yes", "on"}
    if disable_proxy:
        session.trust_env = False
    return session


def call_glm(
    job: dict[str, Any],
    base_url: str,
    api_key: str,
    model: str,
    timeout: float,
    max_retries: int,
) -> dict[str, Any]:
    prompt = build_prompt(job)
    last_error: Exception | None = None
    for attempt in range(max_retries):
        session = build_session()
        try:
            response = session.post(
                normalize_chat_endpoint(base_url),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You extract structured hiring signals from job postings."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                },
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            break
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= max_retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    else:
        assert last_error is not None
        raise last_error

    choices = payload.get("choices") or []
    if not choices:
        raise ValueError(f"No choices in response: {payload}")
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return extract_json_blob(str(content))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a small-sample GLM quality test on job tracker data.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT_PATH), help="Input JSON file with job postings.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON file for GLM results.")
    parser.add_argument("--limit", type=int, default=3, help="Number of jobs to test.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="Per-request timeout in seconds.")
    parser.add_argument("--model", default=os.getenv("GLM_MODEL", DEFAULT_MODEL), help="GLM model name.")
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES, help="Max retries per GLM request.")
    args = parser.parse_args()

    load_env()
    api_key = required_env("GLM_API_KEY")
    base_url = required_env("GLM_BASE_URL")

    input_path = Path(args.input)
    jobs = json.loads(input_path.read_text())
    selected_jobs = jobs[: max(0, args.limit)]

    results: list[dict[str, Any]] = []
    for index, job in enumerate(selected_jobs, start=1):
        print(f"Testing job {index}/{len(selected_jobs)}: {job.get('company') or 'Unknown'} - {job.get('title')}", file=sys.stderr)
        analysis = call_glm(
            job,
            base_url=base_url,
            api_key=api_key,
            model=args.model,
            timeout=args.timeout,
            max_retries=args.max_retries,
        )
        results.append(
            {
                "title": job.get("title"),
                "company": job.get("company"),
                "location": job.get("location"),
                "link": job.get("link"),
                "published_at": job.get("published_at"),
                "glm_model": args.model,
                "analysis": analysis,
            }
        )

    output_path = Path(args.output)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"tested_jobs": len(results), "output": str(output_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
