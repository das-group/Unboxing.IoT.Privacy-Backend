from dataclasses import dataclass


@dataclass
class PublicError(Exception):
    """Base class for public errors presented to users."""

    error_code: str
    http_status: int
    message: str


class NoFileUploadFound(PublicError):
    def __init__(self, upload_id: str):
        super().__init__(
            error_code="NO_FILE_UPLOAD_FOUND",
            http_status=404,
            message=f"No file upload found with ID: {upload_id}",
        )
