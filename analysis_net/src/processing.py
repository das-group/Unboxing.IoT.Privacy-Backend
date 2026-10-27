from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import requests
from src.config import CACHE_DIR, DATA_SERVICE, IPINFO_TOKEN, UPLOADS_DIR
from src.errors import NoFileUploadFound
from src.packet_pipeline import AnalysisPipeline

pipeline = AnalysisPipeline(
    ipinfo_token=IPINFO_TOKEN,
    logging=True,
    cache_duration_days=2,
    cache_dir=CACHE_DIR,
)

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


def analyze_file_worker(
    entry_id: str, file_path: Path, mac_address: str | None, user_id: str, upload_type: str
):
    """Worker function that runs in separate process"""

    if not file_path.exists():
        print("[ERROR] File does not exist: ", file_path)
        return

    if mac_address is None or mac_address == "":
        print("[INFO] No MAC address provided for file: ", file_path)
        mac_address = None

    report = pipeline.run_pipeline(file_path, mac_address)

    if report is None:
        print("[ERROR] Analysis pipeline failed for file: ", file_path)
        return

    # send results to database
    resp = requests.post(
        f"http://{DATA_SERVICE}/report/net",
        json={
            "entry_id": entry_id,
            "report": report,
            "user_id": user_id,
            "report_type": upload_type
        },
    )

    if resp.status_code != 200:
        print("[ERROR] Failed to send results to data service:", resp.text)
        return

    file_path.unlink(missing_ok=True)

    return


def submit_analysis_task(upload_id: str, mac_address: str, user_id: str, upload_type: str):
    """Submit analysis task to the process pool"""

    assert isinstance(upload_id, str)
    assert isinstance(mac_address, str)
    assert isinstance(user_id, str)

    [entry_id, _] = upload_id.split("_")
    file_path = file_path = UPLOADS_DIR / upload_id

    if not file_path.exists():
        raise NoFileUploadFound(upload_id)

    analyze_file_worker(entry_id, file_path, mac_address, user_id, upload_type)

    # process_pool.submit(analyze_file_worker, entry_id, file_path, mac_address, user_id)
