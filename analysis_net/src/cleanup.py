import asyncio
from pathlib import Path
from typing import Set
import shutil


from src.config import UPLOADS_DIR, UPLOADS_CLEANUP_MIN


seen_files: Set[str] = set()


async def cleanup_old_files():
    """Background task that deletes files seen in previous scan"""
    global seen_files

    while True:
        try:
            await asyncio.sleep(UPLOADS_CLEANUP_MIN * 60)

            # Get current files
            current_files = set()
            if UPLOADS_DIR.exists():
                for file_path in UPLOADS_DIR.iterdir():
                    current_files.add(file_path.name)

            # Delete files that were seen in previous scan
            for filename in current_files:
                if filename in seen_files:
                    file_path: Path = UPLOADS_DIR / filename

                    if file_path.is_dir():
                        shutil.rmtree(file_path, ignore_errors=True)
                    try:
                        file_path.unlink(missing_ok=True)
                        print(f"Deleted: {filename}")
                    except Exception as e:
                        print(f"Error deleting {filename}: {e}")

            # Update seen files for next iteration
            seen_files = current_files - seen_files  # Only keep files we didn't delete

        except Exception as e:
            print(f"Error in cleanup task: {e}")
