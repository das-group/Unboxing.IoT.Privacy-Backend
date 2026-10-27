import json
from pathlib import Path

from src.packet_pipeline import AnalysisPipeline

pipeline = AnalysisPipeline(
    ipinfo_token="711a971a423570",
    logging=True,
    cache_duration_days=2,
    cache_dir=Path("./data/db_cache"),
)


if __name__ == "__main__":
    input = Path("D:/Downloads/renpho_app.pcap")
    assert input.exists(), f"Input file {input} does not exist."

    report = pipeline.run_pipeline(input, device_eth_ip=None)

    with open(f"{input.stem}.json", "w") as f:
        json.dump(report, f, indent=2)
