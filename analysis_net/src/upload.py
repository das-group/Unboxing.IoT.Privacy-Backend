import json
import os
from pathlib import Path

import aiofiles
from src.config import UPLOADS_DIR


def chunk_dir(file_id) -> Path:
    d = UPLOADS_DIR / f"{file_id}_chunks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def manifest_path(file_id) -> Path:
    return chunk_dir(file_id) / "manifest.json"


async def receive_chunk(
    upload_id: str,
    chunk_index: int,
    total_chunks: int,
    chunk: bytes,
) -> Path | None:
    directory = chunk_dir(upload_id)

    # Each chunk is written as an individual file: 0.part, 1.part, ...
    part_path = directory / f"{chunk_index}.part"

    async with aiofiles.open(part_path, "wb") as f:
        await f.write(chunk)

    # Update manifest
    mpath = manifest_path(upload_id)
    if not os.path.exists(mpath):
        manifest = {"received": set(), "total": total_chunks}
    else:
        manifest = json.load(open(mpath))
        manifest["received"] = set(manifest["received"])

    manifest["received"].add(chunk_index)
    manifest["total"] = total_chunks

    # Convert back to list for JSON
    with open(mpath, "w") as f:
        json.dump(
            {"received": list(manifest["received"]), "total": manifest["total"]}, f
        )

    # If all chunks received → assemble
    if len(manifest["received"]) == total_chunks:
        final_path = await assemble_file(upload_id, total_chunks)
        return final_path

    return None


async def assemble_file(file_id: str, total_chunks: int) -> Path:
    directory = chunk_dir(file_id)
    final_path = UPLOADS_DIR / file_id

    async with aiofiles.open(final_path, "wb") as outfile:
        for idx in range(total_chunks):
            part_path = directory / f"{idx}.part"
            async with aiofiles.open(part_path, "rb") as part:
                await outfile.write(await part.read())

    # Optional: cleanup chunk directory
    import shutil

    shutil.rmtree(directory)

    return final_path
