#!/usr/bin/env python3
"""
Fetch GitHub Actions workflow runs + jobs for a repo and generate JSON/CSV/HTML reports.
Works with GitHub Enterprise (set API_BASE in .env).
"""

import os, asyncio, json, time
from pathlib import Path
import httpx
import pandas as pd
from jinja2 import Template
from dotenv import load_dotenv

from scripts.utils import HEADERS, API_BASE, iso_now

load_dotenv()

DEFAULT_PER_PAGE = int(os.getenv("PER_PAGE", "100"))
DEFAULT_MAX_PAGES = int(os.getenv("MAX_PAGES", "3"))

semaphore = asyncio.Semaphore(10)

async def get_json(client, url, params=None):
    """Fetch JSON from GitHub API with basic rate-limit handling."""
    async with semaphore:
        r = await client.get(url, params=params)
    if r.status_code == 403 and "rate limit" in (r.text or "").lower():
        reset = r.headers.get("X-RateLimit-Reset")
        if reset:
            wait = int(reset) - int(time.time()) + 5
            print(f"Rate limited. Sleeping {wait}s")
            await asyncio.sleep(max(5, wait))
            return await get_json(client, url, params)
    r.raise_for_status()
    return r.json()

async def fetch_runs_for_repo(client, owner, repo, per_page=DEFAULT_PER_PAGE, max_pages=DEFAULT_MAX_PAGES):
    """Get workflow runs for a repo (limited by pagination)."""
    runs = []
    for page in range(1, max_pages + 1):
        url = f"{API_BASE}/repos/{owner}/{repo}/actions/runs"
        params = {"per_page": per_page, "page": page}
        j = await get_json(client, url, params=params)
        if not j:
            break
        page_runs = j.get("workflow_runs", [])
        runs.extend(page_runs)
        if len(page_runs) < per_page:
            break
    return runs

async def fetch_jobs_for_run(client, owner, repo, run_id):
    """Fetch jobs for a given workflow run."""
    url = f"{API_BASE}/repos/{owner}/{repo}/actions/runs/{run_id}/jobs"
    j = await get_json(client, url)
    return j.get("jobs", [])

def infer_queued_reason(run, jobs):
    """Try to guess why a run is queued (best-effort)."""
    if run.get("status") == "queued":
        if jobs:
            all_awaiting = all(job.get("status") == "queued" and not job.get("runner_name") for job in jobs)
            if all_awaiting:
                return "no_available_runner"
            if any(job.get("status") == "queued" and not job.get("runner_name") for job in jobs):
                return "runner_capacity"
        return "unknown_or_concurrency"
    return None

async def process_repo(owner_repo, per_page, max_pages, out_prefix):
    """Fetch runs + jobs, then write JSON, CSV, and HTML reports."""
    owner, repo = owner_repo.split("/")
    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        runs = await fetch_runs_for_repo(client, owner, repo, per_page, max_pages)

        # Fetch jobs only for queued/in_progress runs
        detail_runs = [r for r in runs if r.get("status") in ("queued", "in_progress")]
        tasks = [fetch_jobs_for_run(client, owner, repo, r["id"]) for r in detail_runs]
        jobs_results = await asyncio.gather(*tasks, return_exceptions=True)
        jobs_map = {
            detail_runs[i]["id"]: jobs_results[i]
            for i in range(len(detail_runs))
            if not isinstance(jobs_results[i], Exception)
        }

        # Build rows
        rows = []
        for r in runs:
            rid = r["id"]
            jobs = jobs_map.get(rid)
            inferred = infer_queued_reason(r, jobs or [])
            rows.append({
                "org_repo": f"{owner}/{repo}",
                "workflow_run_id": rid,
                "workflow_name": r.get("name"),
                "workflow_id": r.get("workflow_id"),
                "head_branch": r.get("head_branch"),
                "head_sha": r.get("head_sha"),
                "event": r.get("event"),
                "status": r.get("status"),
                "conclusion": r.get("conclusion"),
                "created_at": r.get("created_at"),
                "run_started_at": r.get("run_started_at"),
                "updated_at": r.get("updated_at"),
                "actor": (r.get("actor") or {}).get("login"),
                "html_url": r.get("html_url"),
                "jobs": jobs,
                "queued_reason_inferred": inferred
            })

        # === Write outputs ===
        json_out = f"{out_prefix}.json"
        with open(json_out, "w") as jf:
            json.dump(rows, jf, default=str, indent=2)

        df = pd.DataFrame([{
            "org_repo": r["org_repo"],
            "workflow_run_id": r["workflow_run_id"],
            "workflow_name": r["workflow_name"],
            "head_branch": r["head_branch"],
            "event": r["event"],
            "status": r["status"],
            "conclusion": r["conclusion"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "actor": r["actor"],
            "jobs_count": len(r["jobs"]) if r["jobs"] else None,
            "queued_reason_inferred": r["queued_reason_inferred"],
            "html_url": r["html_url"]
        } for r in rows])

        csv_out = f"{out_prefix}.csv"
        df.to_csv(csv_out, index=False)

        counts = df.groupby(["status","conclusion"]).size().reset_index(name="count")
        template = Template("""
        <html><head><meta charset='utf-8'><title>GH Actions Report</title></head><body>
        <h1>Report generated {{now}}</h1>
        <h2>Summary</h2>
        {{ summary|safe }}
        <h2>Queued Runs (first 200)</h2>
        {{ queued|safe }}
        </body></html>
        """)
        html = template.render(
            now=iso_now(),
            summary=counts.to_html(index=False),
            queued=df[df["status"]=="queued"].head(200).to_html(index=False)
        )
        html_out = f"{out_prefix}.html"
        with open(html_out, "w") as hf:
            hf.write(html)

        print("Wrote:", json_out, csv_out, html_out)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--out-prefix", required=True)
    parser.add_argument("--per-page", type=int, default=DEFAULT_PER_PAGE)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    args = parser.parse_args()
    owner_repo = f"{args.owner}/{args.repo}"
    asyncio.run(process_repo(owner_repo, args.per_page, args.max_pages, args.out_prefix))

if __name__ == "__main__":
    main()
