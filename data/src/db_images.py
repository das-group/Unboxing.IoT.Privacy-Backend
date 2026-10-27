import asyncio
import hashlib
import io
import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import aiofiles
from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError
from src.config import IMAGE_UPLOAD_DIR, MONGO_COLLECTION_IMAGES
from src.database import DATA_DB
from src.db_meta import add_image_to_entry, get_metadata_entry_by_id
from src.errors import EntryIDNotFoundError, ImageFormatError
from src.models import DeviceEntry

Path(IMAGE_UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


@dataclass
class StoredImage:
    _id: str
    created_at: str
    uploaded_by: str
    file_hash: str | None = None
    hidden: bool = False


async def save_image_metadata(image_id: str, user_id: str, file_hash: str) -> StoredImage:
    """Save image metadata to the database."""

    image_collection = DATA_DB.get_collection(MONGO_COLLECTION_IMAGES)

    created_at = datetime.now(timezone.utc).isoformat()
    document = {
        "_id": image_id,
        "created_at": created_at,
        "uploaded_by": user_id,
        "file_hash": file_hash
    }

    await image_collection.insert_one(document)

    return StoredImage(
        _id=image_id, created_at=created_at, uploaded_by=user_id, file_hash=file_hash
    )


async def get_image_by_id(image_id: str) -> StoredImage | None:
    """Retrieve an image by its ID."""

    metadata_collection = DATA_DB.get_collection(MONGO_COLLECTION_IMAGES)

    document = await metadata_collection.find_one({"_id": image_id})

    if document:
        return StoredImage(**document)

    return None


async def try_increment_image_count(file_id: str) -> bool:
    """Increment the usage count of an existing image."""

    image_collection = DATA_DB.get_collection(MONGO_COLLECTION_IMAGES)

    result = await image_collection.update_one({"_id": file_id}, {"$inc": {"count": 1}})

    if result.matched_count > 0:
        return True
    return False


def verify_image(content: bytes):
    try:
        img = Image.open(io.BytesIO(content))
        img.verify()
    except UnidentifiedImageError:
        raise ImageFormatError()


async def save_image(
    file: UploadFile, entry_id: str, user_id: str
) -> tuple[str, DeviceEntry]:
    """Save uploaded image and return image ID."""

    assert file is not None and file.filename is not None
    file_suf = Path(file.filename).suffix.lower()
    if file_suf not in [".jpg", ".jpeg", ".png"]:
        raise ImageFormatError()

    content = await file.read()
    verify_image(content)

    # check if entry exists
    metadata_entry = await get_metadata_entry_by_id(entry_id)
    if not metadata_entry:
        raise EntryIDNotFoundError(entry_id)

    # read file content and compute hash
    file_hash: str = hashlib.sha256(content).hexdigest()

    # generate unique image ID and save file
    image_base_id = str(uuid.uuid4())
    
    image_ident = Path(image_base_id).with_suffix(".png")  # all images saved as PNG
    image_ident_thumb = Path(f"{image_base_id}_thumb").with_suffix(".png")

    image_id = str(image_ident)
    await save_image_metadata(image_id, user_id, file_hash)

    QUALITY = 90

    # run saving image and thumbnail concurrently

    _, _, entry = await asyncio.gather(
        save_compressed_image(
            content, str(IMAGE_UPLOAD_DIR / image_ident), quality=QUALITY
        ),
        save_thumbnail(
            content,
            new_height=256,
            output_path=str(IMAGE_UPLOAD_DIR / image_ident_thumb),
            quality=QUALITY,
        ),
        add_image_to_entry(entry_id, image_id, user_id),
    )

    return image_id, entry


async def save_compressed_image(content: bytes, output_path: str, quality: int):
    # Use a thread to avoid blocking event loop for Pillow operations
    def process_image():
        # Open image from bytes
        img = Image.open(io.BytesIO(content))
        # Save to bytes buffer with compression
        buf = io.BytesIO()
        img = img.quantize(colors=256)
        img.save(buf, format="PNG", quality=quality, optimize=True, compress_level=9)
        buf.seek(0)
        return buf

    buf = await asyncio.to_thread(process_image)

    # Write compressed bytes asynchronously
    async with aiofiles.open(output_path, "wb") as f:
        await f.write(buf.read())


async def save_thumbnail(
    content: bytes, new_height: int, output_path: str, quality: int
):
    # Use a thread to avoid blocking event loop for Pillow operations
    def process_image():
        # Open image from bytes
        img = Image.open(io.BytesIO(content))

        # Save to bytes buffer with resized image
        _, height = img.size
        ratio = new_height / height
        new_width = int(img.width * ratio)
        # img.thumbnail((new_width, new_height))
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="PNG", quality=quality, optimize=True, compress_level=9)
        buf.seek(0)
        return buf

    buf = await asyncio.to_thread(process_image)

    # Write resized bytes asynchronously
    async with aiofiles.open(output_path, "wb") as f:
        await f.write(buf.read())


async def delete_title_image(image_id: str) -> bool:
    image_collection = DATA_DB.get_collection(MONGO_COLLECTION_IMAGES)
    img = await get_image_by_id(image_id)

    if img is None:
        return False

    await delete_image_file(img)
    res = await image_collection.delete_one({"_id": img._id})
    return res.deleted_count == 1


async def delete_stored_images(image_ids: list[Image]) -> int:
    image_collection = DATA_DB.get_collection(MONGO_COLLECTION_IMAGES)
    images = image_collection.find({"$or": [{"_id": img.id} for img in image_ids]})

    res = 0
    async for image in images:
        img = StoredImage(**image)
        await delete_image_file(img)
        res += (await image_collection.delete_one({"_id": img._id})).deleted_count

    return res

async def hide_stored_image(image_id: str):
    collection = DATA_DB.get_collection(MONGO_COLLECTION_IMAGES)

    _ = await collection.update_one(
        {
            "_id": image_id
        },
        {
            "$set": { "hidden": True }
        }
    )

async def is_image_hidden(image_id: str) -> bool:
    image_id = image_id.replace("_thumb", "", 1)
    image = await get_image_by_id(image_id)
    return image.hidden if image else False

async def delete_image_file(image: StoredImage):
    def delete_img():
        path = Path(image._id.rstrip(".png"))
        path_thumb = Path(f"{path}_thumb")
        os.remove(IMAGE_UPLOAD_DIR / path.with_suffix(".png"))
        os.remove(IMAGE_UPLOAD_DIR / path_thumb.with_suffix(".png"))

    # Delete image on different thread
    await asyncio.to_thread(delete_img)
