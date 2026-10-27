import ipaddress
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from src.packet_analyze import (
    Flow,
    FlowGroup,
    PacketInfo,
    apply_fast_auto_correlation,
    apply_furrier_transform,
    apply_mean_periodicity_test,
    build_flow_groups,
    build_flows,
    build_flows_with_ip,
    build_time_series,
    collect_packets,
    create_reverse_dns_table,
    find_collection_duration_sec,
)
from src.packet_dns_information import load_block_list, search_block_list
from src.packet_ip_information import GeoDB, IPInfo, load_databases, search_database

PERIODICITY_MIN_FLOWS: int = 10


@dataclass
class FlowReport:
    target_eth: str | None
    target_ip: str | None
    target_port: int | None

    hostname: list[str] | None
    dns_names: list[str] | None

    dns_blocked: bool | None
    target_info: IPInfo | None
    flows: int
    packets: int
    avg_flow_duration: float
    avg_package_per_flow: float
    avg_bytes_per_flow: float
    bytes: int | None
    bytes_in: int | None
    bytes_out: int | None
    periodicity_atc: int | None
    periodicity_furrier: int | None
    periodicity_mean: int | None
    transport: str | None
    application: str | None


def build_ip_info_table(
    packets: list[PacketInfo], asn_v4: pd.DataFrame, asn_v6: pd.DataFrame, geo: GeoDB
) -> dict[str, IPInfo | None]:
    ip_info: dict[str, IPInfo | None] = dict()

    for packet in packets:
        if packet.src_ip and packet.src_ip not in ip_info:
            ip_info[packet.src_ip] = search_database(packet.src_ip, asn_v4, asn_v6, geo)

        if packet.dst_ip and packet.dst_ip not in ip_info:
            ip_info[packet.dst_ip] = search_database(packet.dst_ip, asn_v4, asn_v6, geo)

    return ip_info


def create_group_reports(
    flow_group: FlowGroup,
    reverse_dns_table: dict[str, list[str]],
    dns_blocklist: set[str],
    ip_info_table: dict[str, IPInfo | None],
) -> FlowReport:
    dst_eth = flow_group.target_eth
    target = flow_group.target_ip
    dst_port = flow_group.target_port
    flows = flow_group.num_flows
    packets = flow_group.num_packets
    transport = flow_group.transport
    application = flow_group.application
    bytes = flow_group.bytes
    bytes_in = flow_group.bytes_in
    bytes_out = flow_group.bytes_out

    # avg flow duration
    flow_durs = [flow.duration for flow in flow_group.flows if flow.duration != 0]
    avg_flow_dur = np.mean(flow_durs) if flow_durs else 0

    # avg package per flow
    pckts_per_flow = [flow.num_packets for flow in flow_group.flows]
    avg_package_per_flow = np.mean(pckts_per_flow) if pckts_per_flow else 0

    # avg bytes per flow
    bytes_per_flow = [flow.bytes for flow in flow_group.flows]
    avg_bytes_per_flow = np.mean(bytes_per_flow) if bytes_per_flow else 0

    periodicity_atc = None
    periodicity_furrier = None
    periodicity_mean = None
    if flows > PERIODICITY_MIN_FLOWS:
        arrival_array = np.array(flow_group.arrival_times, dtype=np.int64)
        time_indices, time_series = build_time_series(arrival_array)

        periodicity_atc = apply_fast_auto_correlation(time_series)
        periodicity_furrier = apply_furrier_transform(time_series)

        interarrival_array = np.array(flow_group.interarrival_times, dtype=np.int64)
        periodicity_mean = apply_mean_periodicity_test(interarrival_array)

    # try to resolve ip addresses
    resolved_target = (
        None
        if not flow_group.target_ip
        else reverse_dns_table.get(flow_group.target_ip)
    )
    dns_blocked = False
    if resolved_target is not None:
        for name in resolved_target:
            dns_blocked |= search_block_list(name, dns_blocklist)

    return FlowReport(
        target_eth=dst_eth,
        target_ip=target,
        target_port=dst_port,
        hostname=flow_group.hostnames if flow_group.hostnames else None,
        dns_names=resolved_target,
        dns_blocked=dns_blocked,
        target_info=None if not target else ip_info_table.get(target),
        flows=flows,
        packets=packets,
        avg_flow_duration=float(avg_flow_dur),
        avg_package_per_flow=float(avg_package_per_flow),
        avg_bytes_per_flow=float(avg_bytes_per_flow),
        bytes=bytes,
        bytes_in=bytes_in,
        bytes_out=bytes_out,
        periodicity_atc=periodicity_atc,
        periodicity_furrier=periodicity_furrier,
        periodicity_mean=periodicity_mean,
        transport=transport,
        application=application,
    )


def find_source_eth(packets: list[PacketInfo]) -> str | None:
    dict_eth_count: dict[str, set] = dict()

    for packet in packets:
        if packet.src_eth:
            if packet.src_ip:
                ip = ipaddress.ip_address(packet.src_ip)
                if not ip.is_private:
                    continue

            if packet.src_eth not in dict_eth_count:
                dict_eth_count[packet.src_eth] = set()

            dict_eth_count[packet.src_eth].add(packet.transport)

    if dict_eth_count:
        # select eth addr with most diverse transport protocols
        sorted_eths = sorted(
            dict_eth_count.items(), key=lambda item: len(item[1]), reverse=True
        )
        return sorted_eths[0][0]

    return None


def find_source_ip(packets: list[PacketInfo]) -> str | None:
    dict_ip_count: dict[str, set] = dict()

    for packet in packets:
        if packet.src_ip:
            if packet.src_ip not in dict_ip_count:
                ip = ipaddress.ip_address(packet.src_ip)
                if not ip.is_private:
                    continue
                dict_ip_count[packet.src_ip] = set()

            dict_ip_count[packet.src_ip].add(packet.transport)

    if dict_ip_count:
        # select ip addr with most diverse transport protocols
        sorted_ips = sorted(
            dict_ip_count.items(), key=lambda item: len(item[1]), reverse=True
        )
        return sorted_ips[0][0]

    return None


class AnalysisPipeline:
    ipinfo_token: str
    cache_dir: Path
    cache_duration_days: int
    logging: bool

    def __init__(
        self,
        ipinfo_token: str,
        cache_dir: Path,
        cache_duration_days: int,
        logging: bool = False,
    ):
        cache_dir_path = Path(cache_dir)
        cache_dir_path.mkdir(parents=True, exist_ok=True)

        self.ipinfo_token = ipinfo_token
        self.cache_dir = cache_dir
        self.cache_duration_days = 86400 * cache_duration_days
        self.logging = logging

    def run_pipeline(
        self, input_file: str | Path, device_eth_ip: str | None
    ) -> dict | None:
        if self.logging:
            print("[INFO ] Analyzing file:  ", input_file)

        device_ip: None | str
        device_eth: None | str
        if device_eth_ip is None:
            device_ip = None
            device_eth = None
        else:
            try:
                ipaddress.ip_address(device_eth_ip)
                device_ip = device_eth_ip
                device_eth = None
            except Exception:
                device_ip = None
                device_eth = device_eth_ip.lower().strip()

        if device_eth and device_eth == "":
            print("[ERROR] Device ETH address is empty.")
            return None

        packets: list[PacketInfo] = collect_packets(input_file, device_eth, device_ip)
        if self.logging:
            print(f"[INFO ] Collected packets: {len(packets)}")

        if device_eth is None and device_ip is None:
            device_eth = find_source_eth(packets)
            if device_eth is None:
                device_ip = find_source_ip(packets)
                if device_ip is None:
                    print("[ERROR] Could not determine source IP address.")
                    return None
                if self.logging:
                    print(f"[INFO ] Determined source IP address: {device_ip}")
            else:
                if self.logging:
                    print(f"[INFO ] Determined source ETH address: {device_eth}")

            packets = collect_packets(input_file, device_eth, device_ip)
            if self.logging:
                print(f"[INFO ] Re-collected packets: {len(packets)}")

        if not packets:
            print("[WARN ] Probably wrong Device ETH address...")
            return None

        # determine collection duration
        duration = find_collection_duration_sec(packets)
        if self.logging:
            print(f"[INFO ] Collection duration: {duration} seconds")

        # create reverse dns table
        reverse_dns = create_reverse_dns_table(packets)
        if self.logging:
            print(f"[INFO ] Reverse DNS entries: {len(reverse_dns)}")

        # load ip databases and build ip info table
        db_result = load_databases(
            ipinfo_token=self.ipinfo_token,
            trace=self.logging,
            cache_duration_sec=self.cache_duration_days,
            cache_folder=self.cache_dir,
        )

        if isinstance(db_result, ConnectionError):
            print(f"[ERROR] Failed to load IP databases: {db_result}")
            return None

        db_asn_ip4, db_asn_ip6, db_geo = db_result
        ip_info: dict[str, IPInfo | None] = build_ip_info_table(
            packets, db_asn_ip4, db_asn_ip6, db_geo
        )
        if self.logging:
            print(f"[INFO ] Collected IP information: {len(ip_info)}")

        # load dns blocklist
        dns_blocklist = load_block_list(Path(self.cache_dir) / "_dns_blocklist.txt")
        if self.logging:
            print(f"[INFO ] Loaded DNS blocklist entries: {len(dns_blocklist)}")

        # build flows
        flows: dict[tuple, Flow]
        if device_eth:
            flows = build_flows(packets, device_eth=device_eth)
        elif device_ip:
            flows = build_flows_with_ip(packets, device_ip=device_ip)
        else:
            assert False, "Either device_eth or device_ip must be provided."

        if self.logging:
            print(f"[INFO ] Identified flows: {len(flows)}")

        # build flow groups
        flow_groups: dict[tuple, FlowGroup] = build_flow_groups(flows)
        if self.logging:
            print(f"[INFO ] Grouped flows: {len(flow_groups)}")

        reports = [
            create_group_reports(group, reverse_dns, dns_blocklist, ip_info)
            for group in flow_groups.values()
        ]

        flow_report = pd.json_normalize([asdict(obj) for obj in reports])

        flow_report["target_port"] = flow_report["target_port"].astype("Int64")

        source_ips: list[str | None]
        if device_eth:
            source_ips = [
                packet.src_ip for packet in packets if packet.src_eth == device_eth
            ]
        elif device_ip:
            source_ips = [device_ip]
        else:
            assert False, "Either device_eth or device_ip must be provided."

        source_ips_filtered: list[str] = list(
            set(
                ip
                for ip in source_ips
                if ip is not None
                and ip != "0.0.0.0"
                and ipaddress.ip_address(ip).is_private
            )
        )
        source_ips_filtered.sort()

        flow_report: pd.DataFrame = flow_report.replace(
            [np.nan], [None], regex=False, inplace=False
        )

        flow_report_dict: list[dict] = flow_report.to_dict(orient="records")

        final = {
            "flows": flow_report_dict,
            "info": {
                "device_eth": device_eth,
                "date": date.today().isoformat(),
                "device_ip": device_ip
                if device_ip
                else source_ips_filtered[0]
                if source_ips_filtered
                else None,
                "duration_sec": duration,
            },
        }

        if self.logging:
            print("[INFO ] Analysis complete.")

        return final
