from concurrent.futures import ProcessPoolExecutor
from logging import error, info
from typing import Literal

import requests
from src.analysis import AnalysisResult, analyze_policy
from src.config import DATA_SERVICE

process_pool: ProcessPoolExecutor | None = None


def start_processing_pool(max_workers: int):
    """Start the process pool for analysis tasks"""
    global process_pool
    if process_pool is None:
        process_pool = ProcessPoolExecutor(max_workers=max_workers)


def stop_processing_pool(wait: bool):
    """Shut down the process pool"""
    global process_pool
    if process_pool is not None:
        process_pool.shutdown(wait=wait, cancel_futures=True)
        process_pool = None


def analyze_policy_worker(
    entry_id: str,
    user_id: str,
    type: Literal["html", "url"],
    content: str,
    additional: str | None,
):
    try:
        result: AnalysisResult | None = analyze_policy(type, content, additional)

        if result is None:
            print(f"[ERROR] Analysis failed for entry_id: {entry_id}")
            return

        print(f"[INFO] Analysis completed for entry_id: {entry_id}")

        report = result.model_dump()

        print("Uploading results...")

        resp = requests.post(
            f"http://{DATA_SERVICE}/report/policy",
            json={
                "entry_id": entry_id,
                "report": report,
                "user_id": user_id,
            },
        )

        if resp.status_code != 200:
            error(f"[ERROR] Failed to upload results for entry_id: {entry_id}")
            error(f"[ERROR] Response: {resp.status_code} - {resp.text}")

        info(f"[INFO] Successfully uploaded results for entry_id: {entry_id}")
    except Exception as e:
        error(f"[ERROR] Exception during analysis for entry_id: {entry_id}: {e}")


def submit_analysis_task(
    entry_id: str,
    user_id: str,
    type: Literal["html", "url"],
    content: str,
    additional: str | None,
):
    assert process_pool is not None
    # analyze_policy_worker(entry_id, user_id, type, content, additional)

    process_pool.submit(
        analyze_policy_worker, entry_id, user_id, type, content, additional
    )
