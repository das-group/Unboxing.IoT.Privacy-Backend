import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Generator, Optional


@dataclass
class EthData:
    src_mac: str
    dst_mac: str


@dataclass
class IPData:
    src_ip: str
    dst_ip: str


@dataclass
class TCPData:
    src_port: int
    dst_port: int
    stream: int | None
    length: int | None


@dataclass
class UDPData:
    src_port: int
    dst_port: int
    stream: int | None
    length: int | None


@dataclass
class TLSData:
    server_name: Optional[str]
    alpn: Optional[list[str]]
    data_length: Optional[int]


@dataclass
class DNSData:
    query_name: Optional[str]
    a_record: Optional[list[str]]
    c_name: Optional[list[str]]


@dataclass
class HTTPData:
    host: Optional[str]
    request_method: Optional[str]
    response_code: Optional[str]
    request_uri: Optional[str]
    content_size: Optional[int]


@dataclass
class ICMPData:
    type: Optional[str]
    data_length: Optional[int]


@dataclass
class QUICData:
    length: Optional[int]


@dataclass
class MQTTData:
    topic: Optional[str]
    username: Optional[str]
    password: Optional[str]
    message: Optional[dict]


VALID_PAYLOAD = DNSData | HTTPData | TLSData | QUICData | MQTTData


@dataclass
class Packet:
    timestamp: datetime
    frame_number: int
    frame_size: int
    protocols: list[str]
    highest_proto: str

    # Optional layer data
    eth: Optional[EthData]
    ip: Optional[IPData]
    icmp: Optional[ICMPData]
    tcp: Optional[TCPData]
    udp: Optional[UDPData]
    tls: Optional[TLSData]
    quic: Optional[QUICData]
    dns: Optional[DNSData]
    http: Optional[HTTPData]
    mqtt: Optional[MQTTData]


def parse_packet(raw_packet: dict) -> Packet:
    layers = raw_packet

    try:
        timestamp = datetime.fromtimestamp(
            float(layers["frame.time_epoch"])
        ).astimezone(UTC)
    except Exception:
        timestamp = datetime.fromisoformat(layers["frame.time_epoch"]).astimezone(UTC)

    frame_number = int(layers["frame.number"])
    frame_size = int(layers["frame.len"])
    protocols = layers["frame.protocols"].split(":")
    highest_proto = protocols[-1]

    eth_data = None
    ip_data = None
    tcp_data = None
    udp_data = None
    tls_data = None
    dns_data = None
    http_data = None
    icmp_data = None
    quic_data = None
    mqtt_data = None

    if "eth" in protocols:
        assert isinstance(layers.get("eth.src"), str)
        assert isinstance(layers.get("eth.dst"), str)

        eth_data = EthData(
            src_mac=layers["eth.src"],
            dst_mac=layers["eth.dst"],
        )

    if "ip" in protocols:
        assert isinstance(layers.get("ip.src"), (str, list)), type(layers.get("ip.src"))
        assert isinstance(layers.get("ip.dst"), (str, list)), type(layers.get("ip.dst"))

        src_ip = layers["ip.src"]
        if isinstance(src_ip, list):
            src_ip = src_ip[0]

        dst_ip = layers["ip.dst"]
        if isinstance(dst_ip, list):
            dst_ip = dst_ip[0]

        ip_data = IPData(
            src_ip=src_ip,
            dst_ip=dst_ip,
        )

    if "tcp" in protocols:
        assert isinstance(layers.get("tcp.srcport"), str)
        assert isinstance(layers.get("tcp.dstport"), str)
        assert isinstance(layers.get("tcp.stream"), (str, type(None)))
        assert isinstance(layers.get("tcp.len"), (str, type(None)))

        tcp_data = TCPData(
            src_port=int(layers["tcp.srcport"]),
            dst_port=int(layers["tcp.dstport"]),
            stream=int(layers["tcp.stream"]) if "tcp.stream" in layers else None,
            length=int(layers["tcp.len"]) if "tcp.len" in layers else None,
        )

    if "udp" in protocols:
        assert isinstance(layers.get("udp.srcport"), str)
        assert isinstance(layers.get("udp.dstport"), str)
        assert isinstance(layers.get("udp.stream"), (str, type(None)))
        assert isinstance(layers.get("udp.length"), (str, type(None)))

        udp_data = UDPData(
            src_port=int(layers["udp.srcport"]),
            dst_port=int(layers["udp.dstport"]),
            stream=int(layers["udp.stream"]) if "udp.stream" in layers else None,
            length=int(layers["udp.length"]) if "udp.length" in layers else None,
        )

    if "tls" in protocols:
        tls_content_types = None
        if "tls.record.content_type" in layers:
            if isinstance(layers["tls.record.content_type"], list):
                tls_content_types = layers["tls.record.content_type"]
            else:
                tls_content_types = [layers["tls.record.content_type"]]

        tls_length = None
        if tls_content_types and "23" in tls_content_types:  # Application Data
            if isinstance(layers.get("tls.record.length"), list):
                tls_length = sum(
                    [
                        int(lens)
                        for ct, lens in zip(
                            layers["tls.record.content_type"],
                            layers["tls.record.length"],
                        )
                        if ct == "23"
                    ]
                )
            elif isinstance(layers.get("tls.record.length"), str):
                tls_length = int(layers["tls.record.length"])

        server_name = None
        if "tls.handshake.extensions_server_name" in layers:
            if isinstance(layers["tls.handshake.extensions_server_name"], list):
                server_name = layers["tls.handshake.extensions_server_name"][0]
            else:
                server_name = layers["tls.handshake.extensions_server_name"]

        alpn = None
        if "tls.handshake.extensions_alpn_str" in layers:
            if isinstance(layers["tls.handshake.extensions_alpn_str"], list):
                alpn = layers["tls.handshake.extensions_alpn_str"]
            else:
                alpn = [layers["tls.handshake.extensions_alpn_str"]]

        tls_data = TLSData(
            server_name=server_name,
            alpn=alpn,
            data_length=tls_length,
        )

    if "dns" in protocols:
        assert isinstance(layers.get("dns.qry.name"), (str, type(None)))

        a_record = layers.get("dns.a")
        if isinstance(a_record, str):
            a_record = [a_record]

        c_name = layers.get("dns.cname")
        if isinstance(c_name, str):
            c_name = [c_name]

        dns_data = DNSData(
            query_name=layers.get("dns.qry.name"),
            a_record=a_record,
            c_name=c_name,
        )

    if "http" in protocols:
        assert isinstance(layers.get("http.host"), (str, type(None)))
        assert isinstance(layers.get("http.request.method"), (str, type(None)))
        assert isinstance(layers.get("http.response.code"), (str, type(None)))
        assert isinstance(layers.get("http.request.uri"), (str, type(None)))
        assert isinstance(layers.get("http.content_length"), (str, type(None)))

        http_data = HTTPData(
            host=layers.get("http.host"),
            request_method=layers.get("http.request.method"),
            response_code=layers.get("http.response.code"),
            request_uri=layers.get("http.request.uri"),
            content_size=(
                int(layers["http.content_length"])
                if "http.content_length" in layers
                else None
            ),
        )

    if "icmp" in protocols:
        assert isinstance(layers.get("icmp.type"), (str, type(None)))
        assert isinstance(layers.get("icmp.data"), (str, type(None)))

        icmp_type = layers.get("icmp.type")
        data_length = None
        if layers.get("icmp.data"):
            data_length = len(layers["icmp.data"])
        icmp_data = ICMPData(
            type=icmp_type,
            data_length=data_length,
        )

    if "quic" in protocols:
        length = None
        if isinstance(layers.get("quic.length"), list):
            length = sum(int(length) for length in layers["quic.length"])
        elif isinstance(layers.get("quic.length"), str):
            length = int(layers["quic.length"])

        quic_data = QUICData(length=length)

    if "mqtt" in protocols:
        assert isinstance(layers.get("mqtt.msg"), (str, type(None)))
        assert isinstance(layers.get("mqtt.topic"), (str, type(None)))
        assert isinstance(layers.get("mqtt.username"), (str, type(None)))
        assert isinstance(layers.get("mqtt.passwd"), (str, type(None)))

        msg = None
        if layers.get("mqtt.msg"):
            msg = bytes.fromhex(layers["mqtt.msg"].replace(":", "")).decode("utf-8")
            msg = json.loads(msg)
        mqtt_data = MQTTData(
            topic=layers.get("mqtt.topic"),
            username=layers.get("mqtt.username"),
            password=layers.get("mqtt.passwd"),
            message=msg,
        )

    return Packet(
        timestamp=timestamp,
        frame_number=frame_number,
        frame_size=frame_size,
        protocols=protocols,
        highest_proto=highest_proto,
        eth=eth_data,
        ip=ip_data,
        tcp=tcp_data,
        udp=udp_data,
        tls=tls_data,
        dns=dns_data,
        http=http_data,
        icmp=icmp_data,
        quic=quic_data,
        mqtt=mqtt_data,
    )


FIELDS = [
    "frame.number",
    "frame.protocols",
    "frame.len",
    "tls.handshake.extensions_server_name",
    "tls.handshake.extensions_alpn_str",
    "tls.record.length",
    "tls.record.content_type",
    "ip.src",
    "ip.dst",
    "tcp.srcport",
    "tcp.dstport",
    "tcp.stream",
    "tcp.len",
    "frame.time_epoch",
    "udp.srcport",
    "udp.dstport",
    "udp.stream",
    "udp.length",
    "eth.src",
    "eth.dst",
    "dns.qry.name",
    "dns.a",
    "dns.cname",
    "http.host",
    "http.request.method",
    "http.response.code",
    "http.request.uri",
    "icmp.type",
    # "icmp.data",
    "quic.length",
    "mqtt.topic",
    "mqtt.passwd",
    "mqtt.username",
    "mqtt.msg",
]


class PacketReader:
    proc: subprocess.Popen

    def __init__(self, file: str | Path, display_filter: Optional[str] = None):
        if not isinstance(file, (str, Path)):
            raise TypeError("file must be a string path. Is: " + str(type(file)))

        # check if tshark is installed
        if not shutil.which("tshark"):
            raise RuntimeError("tshark is not installed or not found in PATH")

        # check if file exists
        path = Path(file)
        if not path.exists():
            raise FileNotFoundError(f"File {path} does not exist")

        cmd = [
            "tshark",
            "-r",
            str(file),
            "-T",
            "fields",
            "-2",
            "-E",
            "separator=|",
            "-E",
            "occurrence=a",
            "-E",
            "aggregator=;",
        ]

        for field in FIELDS:
            cmd.extend(["-e", field])

        if display_filter:
            cmd += ["-Y", display_filter]

        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,  # capture errors
            bufsize=1_048_576,  # large buffer for performance,
            text=True,
        )

    # Can be used as an iterator
    def __iter__(self) -> Generator[Packet, None, None]:
        assert self.proc.stdout is not None
        assert self.proc.stderr is not None

        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue

            values = line.split("|")
            packet_dict = {}

            for field, value in zip(FIELDS, values):
                if value == "":
                    continue
                # Split semicolon-separated values for fields with multiple occurrences
                if ";" in value:
                    packet_dict[field] = value.split(";")
                else:
                    packet_dict[field] = value

            yield parse_packet(packet_dict)

        # Verify tshark exit status
        self.proc.wait()
        if self.proc.returncode != 0:
            err = self.proc.stderr.read()
            raise RuntimeError(f"tshark exited with error:\n{err}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # Always try to terminate asyncio/tshark cleanly
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

        # Wait for it to exit and clean up
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()

        return False
