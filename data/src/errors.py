from dataclasses import dataclass


@dataclass
class PublicError(Exception):
    """Base class for public errors presented to users."""

    error_code: str
    http_status: int
    message: str


class EntryIDNotFoundError(PublicError):
    """Raised when a metadata entry with the given ID is not found."""

    def __init__(self, entry_id: str) -> None:
        super().__init__(
            error_code="ENTRY_ID_NOT_FOUND",
            http_status=404,
            message=f"Metadata entry with ID '{entry_id}' not found.",
        )


class ReportIDNotFoundError(PublicError):
    """Raised when a report with the given ID is not found."""

    def __init__(self, report_id: str) -> None:
        super().__init__(
            error_code="REPORT_ID_NOT_FOUND",
            http_status=404,
            message=f"Report with ID '{report_id}' not found.",
        )


class ImageFormatError(PublicError):
    """Raised when an uploaded image has an unsupported format."""

    def __init__(
        self,
    ) -> None:
        super().__init__(
            error_code="IMAGE_FORMAT_ERROR",
            http_status=400,
            message="Uploaded image format is not supported. Only '.png', '.jpg', and '.jpeg' are allowed.",
        )


class ImageIDNotAssociatedError(PublicError):
    """Raised when an image ID is not associated with a metadata entry."""

    def __init__(self, image_id: str) -> None:
        super().__init__(
            error_code="IMAGE_ID_NOT_ASSOCIATED",
            http_status=404,
            message=f"Image with ID '{image_id}' is not associated with the specified metadata entry.",
        )
