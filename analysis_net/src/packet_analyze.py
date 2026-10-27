from dataclasses import dataclass, field
from ipaddress import ip_address
from pathlib import Path
from typing import Optional

import numpy as np
from numpy.typing import NDArray
from scipy import signal
from src.packet_reader import (
    VALID_PAYLOAD,
    DNSData,
    HTTPData,
    Packet,
    PacketReader,
    TLSData,
)

TRANSPORT_PROTO: list[str] = [
    "UDP",
    "UDP_RAW",
    "TCP_RAW",
    "DATA",
]

MAP_PORT_APP: dict[int, str] = {
    443: "HTTPS",
    853: "DNS",
    8883: "MQTT",
    993: "IMAPS",
    995: "POP3S",
    990: "FTPS",
    636: "LDAPS",
    8443: "HTTPS",
}


@dataclass
class PacketInfo:
    frame_number: int
    arrival_time: float
    src_eth: Optional[str]
    dst_eth: Optional[str]
    src_ip: Optional[str]
    dst_ip: Optional[str]
    src_port: Optional[int]
    dst_port: Optional[int]
    transport: Optional[str]
    transport_stream: Optional[int]
    application: str
    data_size: int
    payload: Optional[VALID_PAYLOAD]


@dataclass
class Flow:
    num_packets: int
    bytes: int
    bytes_in: int
    bytes_out: int
    start_time: int
    duration: float
    target_eth: str | None
    target_ip: str | None
    target_port: int | None
    protocol: str | None
    application: str

    hostnames: list[str] | None

    packets: list[PacketInfo]


@dataclass
class FlowGroup:
    flows: list[Flow]
    num_flows: int = 0
    num_packets: int = 0
    bytes: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    target_eth: str | None = None
    target_ip: str | None = None
    target_port: int | None = None
    interarrival_times: list[float] = field(default_factory=list)
    arrival_times: list[int] = field(default_factory=list)
    transport: str | None = None
    application: str | None = None

    hostnames: list[str] | None = None


def extract_packet_info(packet: Packet) -> PacketInfo:
    src_eth = packet.eth.src_mac if packet.eth else None
    dst_eth = packet.eth.dst_mac if packet.eth else None

    src_ip = packet.ip.src_ip if packet.ip else None
    dst_ip = packet.ip.dst_ip if packet.ip else None

    src_port = None
    dst_port = None
    transport = None
    transport_stream = None
    data_size = packet.frame_size
    application = packet.highest_proto.upper()
    payload = None

    if packet.tcp:
        src_port = packet.tcp.src_port
        dst_port = packet.tcp.dst_port
        transport = "TCP"
        transport_stream = packet.tcp.stream
        data_size = packet.tcp.length if packet.tcp.length else data_size
    elif packet.udp:
        src_port = packet.udp.src_port
        dst_port = packet.udp.dst_port
        transport = "UDP"
        transport_stream = packet.udp.stream
        data_size = packet.udp.length if packet.udp.length else data_size
    elif packet.icmp:
        transport = "ICMP"
        data_size = packet.icmp.data_length if packet.icmp.data_length else data_size

    if packet.tls:
        payload = packet.tls
        data_size = packet.tls.data_length if packet.tls.data_length else data_size
    elif packet.dns:
        payload = packet.dns
    elif packet.quic:
        payload = packet.quic
        data_size = packet.quic.length if packet.quic.length else data_size
    elif packet.mqtt:
        payload = packet.mqtt
        data_size = len(str(packet.mqtt.message)) if packet.mqtt.message else data_size
    elif packet.http:
        payload = packet.http
        data_size = packet.http.content_size if packet.http.content_size else data_size

    assert payload is None or isinstance(payload, VALID_PAYLOAD)

    return PacketInfo(
        frame_number=packet.frame_number,
        arrival_time=packet.timestamp.timestamp() * 1000,  # milliseconds
        src_eth=src_eth,
        dst_eth=dst_eth,
        src_ip=src_ip,
        dst_ip=dst_ip,
        src_port=src_port,
        dst_port=dst_port,
        transport=transport,
        transport_stream=transport_stream,
        application=application,
        data_size=data_size,
        payload=payload,
    )


def collect_packets(
    input_file: str | Path,
    device_eth: str | None,
    device_ip: str | None,
) -> list[PacketInfo]:
    """
    Collect packets from a pcapng file and extract relevant information.
    """

    host_filter: str | None

    if device_ip is not None:
        host_filter = f"ip.addr == {device_ip}"
    elif device_eth is not None:
        host_filter = f"eth.addr == {device_eth}"
    else:
        host_filter = None

    packets: list[PacketInfo] = list()

    with PacketReader(input_file, display_filter=host_filter) as recorded:
        for i, packet in enumerate(recorded):
            print("[INFO ] Processing packet: ", i, end="\r")

            info = extract_packet_info(packet)

            if info:
                packets.append(info)

    if packets == []:
        print(
            "[ERROR] No packets found. Maybe the device_eth or device_ip is incorrect?"
        )
        return []

    return packets


def find_collection_duration_sec(packets: list[PacketInfo]) -> float:
    """Find the duration of the packet collection in the pcap file.

    Returns the duration in seconds
    """

    if packets == []:
        return 0

    start = min(packets, key=lambda x: x.arrival_time).arrival_time
    end = max(packets, key=lambda x: x.arrival_time).arrival_time

    duration = end - start

    return int(duration) / 1000


def check_ip_validity(ip: str) -> bool:
    try:
        ip_address(ip)
        return True
    except ValueError:
        return False


def create_reverse_dns_table(packets: list[PacketInfo]) -> dict[str, list[str]]:
    """Create a reverse DNS table from DNS packets."""

    reverse_dns_table: dict[str, list[str]] = dict()

    # Build reverse DNS table
    for packet in packets:
        if isinstance(packet.payload, DNSData):
            payload: DNSData = packet.payload

            if payload.query_name and payload.a_record:
                for a_record in payload.a_record:
                    if a_record not in reverse_dns_table:
                        reverse_dns_table[a_record] = []
                    reverse_dns_table[a_record].append(payload.query_name)

            if payload.c_name and payload.a_record:
                for a_record in payload.a_record:
                    if a_record not in reverse_dns_table:
                        reverse_dns_table[a_record] = []
                    reverse_dns_table[a_record].extend(payload.c_name)

    # de-duplicate entries
    for ip, names in reverse_dns_table.items():
        reverse_dns_table[ip] = list(set(names))

    return reverse_dns_table


def build_flows(
    packets: list[PacketInfo],
    device_eth: str,
) -> dict[tuple, Flow]:
    flows: dict[tuple, list[PacketInfo]] = dict()

    # collect packages into flows
    for packet in packets:
        dst = None
        if packet.src_ip is not None and packet.dst_ip is not None:
            dst = packet.src_ip if packet.src_eth != device_eth else packet.dst_ip

        elif packet.src_eth is not None and packet.dst_eth is not None:
            dst = packet.src_eth if packet.src_eth != device_eth else packet.dst_eth

        assert device_eth in [
            packet.src_eth,
            packet.dst_eth,
        ], (
            f"[ERROR] Device MAC {device_eth} not found in {[packet.src_eth, packet.dst_eth]}"
        )

        flow_key = (
            packet.transport,
            packet.transport_stream,
            dst,
        )
        if flow_key not in flows:
            flows[flow_key] = []
        flows[flow_key].append(packet)

    complete_flows: dict[tuple, Flow] = dict()

    for key, pkts in flows.items():
        pkts.sort(key=lambda p: p.arrival_time)
        num_packets = len(pkts)
        num_bytes = sum(p.data_size for p in pkts)
        bytes_in = sum(p.data_size for p in pkts if p.src_eth != device_eth)
        bytes_out = sum(p.data_size for p in pkts if p.src_eth == device_eth)
        duration = pkts[-1].arrival_time - pkts[0].arrival_time
        protocol = pkts[0].transport
        application = pkts[0].application
        hostnames: list[str] = []

        target_eth = None
        target_ip = None
        target_port = None
        for p in pkts:
            if p.src_eth == device_eth:
                target_eth = p.dst_eth
                target_ip = p.dst_ip
                target_port = p.dst_port
            elif p.dst_eth == device_eth:
                target_eth = p.src_eth
                target_ip = p.src_ip
                target_port = p.src_port
            else:
                assert False

            assert target_eth != device_eth

            if p.application != application:
                if application in ["UDP", "TCP", "DATA"]:
                    application = p.application

            if p.payload:
                if isinstance(p.payload, TLSData):
                    if p.payload.server_name:
                        hostnames.append(p.payload.server_name)
                elif isinstance(p.payload, HTTPData):
                    if p.payload.host:
                        hostnames.append(p.payload.host)

        complete_flows[key] = Flow(
            num_packets=num_packets,
            bytes=num_bytes,
            bytes_in=bytes_in,
            bytes_out=bytes_out,
            start_time=int(pkts[0].arrival_time),
            duration=duration,
            target_eth=target_eth,
            target_ip=target_ip,
            target_port=target_port,
            protocol=protocol,
            application=application,
            hostnames=hostnames if hostnames else None,
            packets=pkts,
        )

    return complete_flows


def build_flows_with_ip(packets: list[PacketInfo], device_ip: str) -> dict[tuple, Flow]:
    flows: dict[tuple, list[PacketInfo]] = dict()

    # collect packages into flows
    for packet in packets:
        dst = None
        if packet.src_ip is not None and packet.dst_ip is not None:
            dst = packet.src_ip if packet.src_ip != device_ip else packet.dst_ip

        elif packet.src_eth is not None and packet.dst_eth is not None:
            dst = packet.src_eth if packet.src_ip != device_ip else packet.dst_eth

        flow_key = (
            packet.transport,
            packet.transport_stream,
            dst,
        )
        if flow_key not in flows:
            flows[flow_key] = []
        flows[flow_key].append(packet)

    complete_flows: dict[tuple, Flow] = dict()

    for key, pkts in flows.items():
        pkts.sort(key=lambda p: p.arrival_time)
        num_packets = len(pkts)
        num_bytes = sum(p.data_size for p in pkts)
        bytes_in = sum(p.data_size for p in pkts if p.src_ip != device_ip)
        bytes_out = sum(p.data_size for p in pkts if p.src_ip == device_ip)
        duration = pkts[-1].arrival_time - pkts[0].arrival_time
        protocol = pkts[0].transport
        application = pkts[0].application
        hostnames: list[str] = []

        target_eth = None
        target_ip = None
        target_port = None
        for p in pkts:
            if p.src_ip == device_ip:
                target_eth = p.dst_eth
                target_ip = p.dst_ip
                target_port = p.dst_port
            elif p.dst_ip == device_ip:
                target_eth = p.src_eth
                target_ip = p.src_ip
                target_port = p.src_port
            else:
                assert False

            assert target_ip != device_ip

            if p.application != application:
                if application in ["UDP", "TCP", "DATA"]:
                    application = p.application

            if p.payload:
                if isinstance(p.payload, TLSData):
                    if p.payload.server_name:
                        hostnames.append(p.payload.server_name)
                elif isinstance(p.payload, HTTPData):
                    if p.payload.host:
                        hostnames.append(p.payload.host)

        complete_flows[key] = Flow(
            num_packets=num_packets,
            bytes=num_bytes,
            bytes_in=bytes_in,
            bytes_out=bytes_out,
            start_time=int(pkts[0].arrival_time),
            duration=duration,
            target_eth=target_eth,
            target_ip=target_ip,
            target_port=target_port,
            protocol=protocol,
            application=application,
            hostnames=hostnames if hostnames else None,
            packets=pkts,
        )

    return complete_flows


def build_flow_groups(flows: dict[tuple, Flow]) -> dict[tuple, FlowGroup]:
    assert all(isinstance(flow, Flow) for flow in flows.values())

    flow_groups: dict[tuple, FlowGroup] = dict()

    for _, flow in flows.items():
        key = (
            flow.target_eth,
            flow.target_ip,
            flow.target_port,
            flow.protocol,
            flow.application,
        )
        if key not in flow_groups:
            flow_groups[key] = FlowGroup(flows=[])
        flow_groups[key].flows.append(flow)

    # calculate interarrival time
    for group in flow_groups.values():
        bytes = sum(flow.bytes for flow in group.flows)
        bytes_in = sum(flow.bytes_in for flow in group.flows)
        bytes_out = sum(flow.bytes_out for flow in group.flows)

        interarrival_times = []
        arrival_times = []
        for i in range(1, len(group.flows)):
            interarrival_time = (
                group.flows[i].start_time - group.flows[i - 1].start_time
            )
            interarrival_times.append(interarrival_time)
            arrival_times.append(group.flows[i].start_time)

        # assert hostnames are the same
        group.num_flows = len(group.flows)
        group.num_packets = sum(flow.num_packets for flow in group.flows)
        group.interarrival_times = interarrival_times
        group.arrival_times = arrival_times
        group.target_eth = group.flows[0].target_eth
        group.target_ip = group.flows[0].target_ip
        group.target_port = group.flows[0].target_port
        group.bytes = bytes
        group.bytes_in = bytes_in
        group.bytes_out = bytes_out
        group.application = group.flows[0].application
        group.transport = group.flows[0].protocol
        group.hostnames = []
        for flow in group.flows:
            if flow.hostnames:
                group.hostnames.extend(flow.hostnames)
        group.hostnames = list(set(group.hostnames))

        if group.application == "TLS":
            assert isinstance(group.target_port, int)
            mapped = MAP_PORT_APP.get(group.target_port, None)
            group.application = f"TLS/{mapped}" if mapped else group.application

    # free memory
    for group in flow_groups.values():
        group.flows = []

    return flow_groups


def build_time_series(event_times: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Build a time series from event timestamps."""

    if len(event_times) == 0:
        return np.array([]), np.array([])

    start_time = min(event_times)
    end_time = max(event_times)

    # Create a time series array initialized to zero
    time_series_length = end_time - start_time + 1
    time_series = np.zeros(time_series_length, dtype=int)

    # Mark the event occurrences in the time series
    for event_time in event_times:
        index = event_time - start_time
        time_series[index] = 1

    time_indices = np.arange(start_time, end_time + 1)

    return time_indices, time_series


def round_adaptive(value: float) -> int:
    if value >= 10000:
        return int(round(value, -3))
    if value >= 1000:
        return int(round(value, -2))
    if value >= 100:
        return int(round(value, -1))
    return int(round(value))


def apply_mean_periodicity_test(interarrival: NDArray[np.int64]) -> int | None:
    """Apply mean periodicity test to interarrival times."""

    mean = np.mean(interarrival)
    s = np.std(interarrival, ddof=1)  # Sample standard deviation

    threshold = 0.01 * mean

    if s < threshold:
        return int(round_adaptive(float(mean)))
    else:
        return None


def apply_fast_auto_correlation(series: NDArray[np.int64]) -> int | None:
    """Apply Fast Auto-Correlation to identify periodicity in a binary time series."""
    assert all(x in [0, 1] for x in series)

    # Full autocorrelation
    result: NDArray = signal.correlate(series, series, mode="full", method="fft")[
        len(series) - 1 :
    ]
    acorr = result / np.max(result)

    # Identify significant lags
    threshold = 0.05  # Example threshold for peak detection
    significant_lags = np.where(acorr > threshold)[0]

    significant_lags = significant_lags[significant_lags != 0]

    if significant_lags.size == 0:
        return None

    significant_lags = np.vectorize(round_adaptive)(significant_lags)

    return int(np.min(significant_lags))


def apply_furrier_transform(time_series: NDArray[np.int64]) -> int | None:
    """Apply Fast Fourier Transform to identify periodicity in a binary time series."""
    assert all(x in [0, 1] for x in time_series)

    # Compute the Fast Fourier Transform (FFT) of the binary time series
    N = len(time_series)
    fft_values = np.fft.fft(time_series)
    fft_frequencies = np.fft.fftfreq(N, d=1)  # d is the time between samples

    # Consider only the positive frequencies
    positive_indexes = np.arange(N // 2)
    frequencies = fft_frequencies[positive_indexes]
    magnitudes = np.abs(fft_values[positive_indexes])

    # Identify significant frequencies
    threshold = 0.65 * np.max(magnitudes)  # Example threshold
    significant_frequencies = frequencies[magnitudes > threshold][1:]
    significant_periods = 1 / significant_frequencies

    if significant_periods.size == 0:
        print(
            "[INFO ] No significant periods found: ",
            significant_frequencies,
            significant_periods,
        )
        return None

    return int(round_adaptive(np.max(significant_periods)))
