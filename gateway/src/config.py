import json
import os

USER_SERVICE = os.getenv("USER_SERVICE", "localhost:4040")

DATA_SERVICE = os.getenv("DATA_SERVICE", "localhost:4070")

ANALYSIS_POLICY_SERVICE = os.getenv("ANALYSIS_POLICY_SERVICE", "localhost:4050")
ANALYSIS_NET_SERVICE = os.getenv("ANALYSIS_NET_SERVICE", "localhost:4060")
ANALYSIS_FIRMWARE_SERVICE = os.getenv("ANALYSIS_FIRMWARE_SERVICE", "localhost:4090")


ORIGIN = json.loads(
    os.environ.get("ORIGIN", '["http://localhost:4040", "http://localhost:5173"]')
)
