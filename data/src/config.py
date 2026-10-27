import os

MONGO_HOST = os.environ.get("MONGO_HOST", "localhost")
MONGO_PORT = int(os.environ.get("MONGO_PORT", 27019))
MONGO_USER = os.environ.get("MONGO_USER", "admin")
MONGO_PASS = os.environ.get("MONGO_PASS", "password")
MONGO_DB = os.environ.get("MONGO_DB", "datadb")
MONGO_COLLECTION_METADATA = os.environ.get("MONGO_COLLECTION_METADATA", "metadata")
MONGO_COLLECTION_ENTRY_REPORTS = os.environ.get("MONGO_COLLECTION_ENTRY_REPORTS", "entry_reports")
MONGO_COLLECTION_ENTRY_RATINGS = os.environ.get("MONGO_COLLECTION_ENTRY_RATINGS", "entry_ratings")
MONGO_COLLECTION_ENTRY_UPDATES = os.environ.get("MONGO_COLLECTION_ENTRY_UPDATES", "entry_updates")
MONGO_COLLECTION_REPORTS_POLICY = os.environ.get(
    "MONGO_COLLECTION_REPORTS_POLICY", "reports_policy"
)
MONGO_COLLECTION_REPORTS_NET = os.environ.get(
    "MONGO_COLLECTION_REPORTS_NET", "reports_net"
)
MONGO_COLLECTION_REPORTS_FIRMWARE = os.environ.get(
    "MONGO_COLLECTION_REPORTS_FIRMWARE", "reports_firmware"
)
MONGO_COLLECTION_IMAGES = os.environ.get("MONGO_COLLECTION_IMAGES", "images")


IMAGE_UPLOAD_DIR = "data/" + os.environ.get("IMAGE_UPLOAD_DIR", "/images")

ANALYSIS_POLICY_SERVICE = os.getenv("ANALYSIS_POLICY_SERVICE", "localhost:4050")
ANALYSIS_NET_SERVICE = os.getenv("ANALYSIS_NET_SERVICE", "localhost:4060")
ANALYSIS_FIRMWARE_SERVICE = os.getenv("ANALYSIS_FIRMWARE_SERVICE", "localhost:4090")
