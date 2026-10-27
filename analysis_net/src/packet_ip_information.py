import gzip
import io
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv6Address, ip_address
from pathlib import Path

import maxminddb
import pandas as pd
import requests

COUNTRY_CODE_LOOKUP = {
    "AF": "Afghanistan",
    "AL": "Albania",
    "DZ": "Algeria",
    "AS": "American Samoa",
    "AD": "Andorra",
    "AO": "Angola",
    "AI": "Anguilla",
    "AG": "Antigua and Barbuda",
    "AR": "Argentina",
    "AM": "Armenia",
    "AW": "Aruba",
    "AU": "Australia",
    "AT": "Austria",
    "AZ": "Azerbaijan",
    "BS": "Bahamas",
    "BH": "Bahrain",
    "BD": "Bangladesh",
    "BB": "Barbados",
    "BY": "Belarus",
    "BE": "Belgium",
    "BZ": "Belize",
    "BJ": "Benin",
    "BM": "Bermuda",
    "BT": "Bhutan",
    "BO": "Bolivia",
    "BA": "Bosnia and Herzegovina",
    "BW": "Botswana",
    "BR": "Brazil",
    "VG": "British Virgin Islands",
    "BN": "Brunei Darussalam",
    "BG": "Bulgaria",
    "BF": "Burkina Faso",
    "BI": "Burundi",
    "KH": "Cambodia",
    "CM": "Cameroon",
    "CA": "Canada",
    "CV": "Cape Verde",
    "CF": "Central African Republic",
    "TD": "Chad",
    "CL": "Chile",
    "CN": "China",
    "HK": "Hong Kong",
    "MO": "Macao",
    "CO": "Colombia",
    "KM": "Comoros",
    "CG": "Congo",
    "CR": "Costa Rica",
    "CI": "Côte d'Ivoire",
    "HR": "Croatia",
    "CU": "Cuba",
    "CY": "Cyprus",
    "CZ": "Czech Republic",
    "DK": "Denmark",
    "DJ": "Djibouti",
    "DM": "Dominica",
    "DO": "Dominican Republic",
    "EC": "Ecuador",
    "EG": "Egypt",
    "SV": "El Salvador",
    "GQ": "Equatorial Guinea",
    "ER": "Eritrea",
    "EE": "Estonia",
    "ET": "Ethiopia",
    "EU": "European Union",
    "FO": "Faroe Islands",
    "FJ": "Fiji",
    "FI": "Finland",
    "FR": "France",
    "GF": "French Guiana",
    "PF": "French Polynesia",
    "GA": "Gabon",
    "GM": "Gambia",
    "GE": "Georgia",
    "DE": "Germany",
    "GH": "Ghana",
    "GR": "Greece",
    "GL": "Greenland",
    "GD": "Grenada",
    "GP": "Guadeloupe",
    "GU": "Guam",
    "GT": "Guatemala",
    "GW": "Guinea-Bissau",
    "HT": "Haiti",
    "HN": "Honduras",
    "HU": "Hungry",
    "IS": "Iceland",
    "IN": "India",
    "ID": "Indonesia",
    "IR": "Iran (Islamic Republic of)",
    "IQ": "Iraq",
    "IE": "Ireland",
    "IL": "Israel",
    "IT": "Italy",
    "JP": "Japan",
    "JO": "Jordan",
    "KZ": "Kazakhstan",
    "KE": "Kenya",
    "KI": "Kiribati",
    "KP": "Korea",
    "KR": "Korea",
    "KW": "Kuwait",
    "KG": "Kyrgyzstan",
    "LA": "Lao PDR",
    "LV": "Latvia",
    "LB": "Lebanon",
    "LS": "Lesotho",
    "LR": "Liberia",
    "LY": "Libya",
    "LI": "Liechtenstein",
    "LT": "Lithuania",
    "LU": "Luxembourg",
    "MG": "Madagascar",
    "MW": "Malawi",
    "MY": "Malaysia",
    "MV": "Maldives",
    "ML": "Mali",
    "MT": "Malta",
    "MH": "Marshall Islands",
    "MQ": "Martinique",
    "MR": "Mauritania",
    "MU": "Mauritius",
    "MX": "Mexico",
    "FM": "Micronesia, Federated States of",
    "MD": "Moldova",
    "MC": "Monaco",
    "MN": "Mongolia",
    "ME": "Montenegro",
    "MS": "Montserrat",
    "MA": "Morocco",
    "MZ": "Mozambique",
    "MM": "Myanmar",
    "NA": "Namibia",
    "NR": "Nauru",
    "NP": "Nepal",
    "NL": "Netherlands",
    "AN": "Netherlands Antilles",
    "NC": "New Caledonia",
    "NZ": "New Zealand",
    "NI": "Nicaragua",
    "NE": "Niger",
    "NG": "Nigeria",
    "MP": "Northern Mariana Islands",
    "NO": "Norway",
    "OM": "Oman",
    "PK": "Pakistan",
    "PW": "Palau",
    "PS": "Palestinian Territory",
    "PA": "Panama",
    "PG": "Papua New Guinea",
    "PY": "Paraguay",
    "PE": "Peru",
    "PH": "Philippines",
    "PN": "Pitcairn",
    "PL": "Poland",
    "PT": "Portugal",
    "PR": "Puerto Rico",
    "QA": "Qatar",
    "RE": "Réunion",
    "RO": "Romania",
    "RU": "Russian Federation",
    "RW": "Rwanda",
    "KN": "Saint Kitts and Nevis",
    "LC": "Saint Lucia",
    "VC": "Saint Vincent and Grenadines",
    "WS": "Samoa",
    "SM": "San Marino",
    "ST": "Sao Tome and Principe",
    "SA": "Saudi Arabia",
    "SN": "Senegal",
    "RS": "Serbia",
    "SC": "Seychelles",
    "SL": "Sierra Leone",
    "SG": "Singapore",
    "SK": "Slovakia",
    "SI": "Slovenia",
    "SB": "Solomon Islands",
    "SO": "Somalia",
    "ZA": "South Africa",
    "ES": "Spain",
    "LK": "Sri Lanka",
    "SD": "Sudan",
    "SR": "Suriname",
    "SZ": "Swaziland",
    "SE": "Sweden",
    "CH": "Switzerland",
    "SY": "Syrian Arab Republic",
    "TW": "Taiwan (Province of China)",
    "TJ": "Tajikistan",
    "TZ": "Tanzania",
    "TH": "Thailand",
    "TL": "Timor-Leste",
    "TG": "Togo",
    "TO": "Tonga",
    "TT": "Trinidad and Tobago",
    "TN": "Tunisia",
    "TR": "Turkey",
    "TM": "Turkmenistan",
    "TV": "Tuvalu",
    "UG": "Uganda",
    "UA": "Ukraine",
    "AE": "United Arab Emirates",
    "GB": "United Kingdom",
    "US": "United States of America",
    "UY": "Uruguay",
    "UZ": "Uzbekistan",
    "VU": "Vanuatu",
    "VE": "Venezuela",
    "VN": "Viet Nam",
    "VI": "Virgin Islands, US",
    "YE": "Yemen",
    "ZM": "Zambia",
    "ZW": "Zimbabwe",
}


IP2ASN_DATABASE_URL = "https://iptoasn.com/data/ip2asn-combined.tsv.gz"
ASN2COMPANY_DATABASE_URL = (
    "https://raw.githubusercontent.com/ipverse/asn-info/master/as.csv"
)


# TODO: Replace with your own token from ipinfo.io
TOKEN = "af073f0261e83e"
TOKEN = "711a971a423570"
# IP2GEO_2_DATABASE_URL = f"https://ipinfo.io/data/ipinfo_lite.csv.gz?token={TOKEN}"
IP2GEO_2_DATABASE_URL = "https://ipinfo.io/data/ipinfo_lite.mmdb?token={token}"


GeoDB = maxminddb.Reader


@dataclass
class IPInfo:
    country: str
    country_c: str
    entity: str | None
    ent_origin: str
    ent_origin_c: str
    ent_domain: str | None


def load_ip2asn_database() -> pd.DataFrame | ConnectionError:
    response = requests.get(IP2ASN_DATABASE_URL)

    if response.status_code != 200:
        raise ConnectionError(
            f"Failed to download IP to ASN database from {IP2ASN_DATABASE_URL}"
        )

    decompressed = gzip.decompress(response.content)

    df = pd.read_table(
        io.BytesIO(decompressed),
        sep="\t",
        header=None,
        names=["Start", "End", "asn", "Country", "Entity"],
        na_values=["Not routed"],
    )

    # Force new allocation, to free up old one
    df = df.dropna(inplace=False)
    df = df.drop(columns=["Entity"], inplace=False)

    return df


def load_asn2company_database() -> pd.DataFrame | ConnectionError:
    response = requests.get(ASN2COMPANY_DATABASE_URL)

    if response.status_code != 200:
        raise ConnectionError(
            f"Failed to download ASN to Company database from {ASN2COMPANY_DATABASE_URL}"
        )

    df = pd.read_csv(
        io.StringIO(response.text),
        on_bad_lines=lambda bline: [bline[0], bline[1], " ".join(bline[2:])],
        engine="python",
        usecols=["asn"],
    )

    return df


def build_ip2geo_database(output_path: str, token: str) -> GeoDB:
    # make sure the output path exists, before downloading
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)

    url_with_token = IP2GEO_2_DATABASE_URL.format(token=token)
    response = requests.get(url_with_token)

    if response.status_code != 200:
        # delete file if download failed
        path.unlink(missing_ok=True)
        print(f"[ERROR] Failed to download IP2GEO database: {response.status_code}")
        raise Exception(f"Failed to download IP2GEO database: {response.status_code}")

    with open(output_path, "wb") as f:
        f.write(response.content)

    return maxminddb.open_database(output_path)


def build_ip2company_database() -> tuple[pd.DataFrame, pd.DataFrame]:
    # load seperate databases
    ip2ans = load_ip2asn_database()
    ans2company = load_asn2company_database()

    if isinstance(ip2ans, ConnectionError):
        raise ip2ans

    if isinstance(ans2company, ConnectionError):
        raise ans2company

    # join databases
    df = pd.merge(ip2ans, ans2company, how="outer")
    df = df.dropna()
    df = df.drop(columns=["asn"], inplace=False)

    df = df.rename(columns={"Country": "Code"}, inplace=False)

    # seperate into IPv4 & IPv6
    mask = df["Start"].apply(lambda ip: isinstance(ip_address(ip), IPv6Address))
    df_ip4 = df[~mask].copy()
    df_ip6 = df[mask].copy()

    del df

    # Sort both based on Start IP
    df_ip4["ip_as_int"] = df_ip4["Start"].apply(lambda ip: int(ip_address(ip)))
    df_ip6["ip_as_int"] = df_ip6["Start"].apply(lambda ip: int(ip_address(ip)))

    df_ip4 = df_ip4.sort_values(by="ip_as_int")
    df_ip6 = df_ip6.sort_values(by="ip_as_int")

    df_ip4 = df_ip4.drop(columns="ip_as_int", inplace=False)
    df_ip6 = df_ip6.drop(columns="ip_as_int", inplace=False)

    # reset indicies
    df_ip4 = df_ip4.reset_index(drop=True)
    df_ip6 = df_ip6.reset_index(drop=True)

    return (df_ip4, df_ip6)


def load_databases(
    ipinfo_token: str,
    cache_folder: Path = Path("./"),
    version_file: str = "_ip2cacheinfo.txt",
    ipv4_file: str = "_ip2company_ip4.csv",
    ipv6_file: str = "_ip2company_ip6.csv",
    geo_file: str = "_ip2geo.mmdb",
    cache_duration_sec: int = 86400 * 2,  # 86400 seconds == 1 day
    trace: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, GeoDB] | ConnectionError:
    assert ipinfo_token != "", "IPInfo token must be provided."

    refresh = False

    # check version file
    version_fpath: Path = cache_folder / version_file

    try:
        if version_fpath.exists():
            with open(version_fpath, "r") as f:
                content_str = float(f.read())
                dt = datetime.fromtimestamp(content_str)
                now = datetime.now()

                diff_d: timedelta = now - dt
                diff: float = timedelta.total_seconds(diff_d)

                # if last fetch is too old, refresh,
                refresh = diff >= cache_duration_sec
                if refresh:
                    print("[INFO ] Cache too old...")

        # if version file does not exists, refresh
        else:
            refresh = True
    except Exception as e:
        if trace:
            print(f"[ERROR] {e}")
        refresh = True

    ip4_asn_fpath: str = os.path.join(cache_folder, ipv4_file)
    ip6_asn_fpath: str = os.path.join(cache_folder, ipv6_file)
    ip_geo_fpath: str = os.path.join(cache_folder, geo_file)

    # if either file does not exists, refresh
    if (
        not os.path.exists(ip4_asn_fpath)
        or not os.path.exists(ip6_asn_fpath)
        or not os.path.exists(ip_geo_fpath)
    ):
        refresh = True

    # cached databank needs refresh
    if refresh:
        if trace:
            print("[INFO ] Need refresh...")

        now: datetime = datetime.now()
        now_str: str = str(now.timestamp())

        #########################

        if trace:
            print("[TRACE] Build company databases...")
        df_asn_ip4, df_asn_ip6 = build_ip2company_database()

        df_asn_ip4.to_csv(ip4_asn_fpath, index=False)
        df_asn_ip6.to_csv(ip6_asn_fpath, index=False)

        #########################

        if trace:
            print("[TRACE] Build geo databases...")

        geo = build_ip2geo_database(ip_geo_fpath, token=ipinfo_token)

        #########################

        with open(version_fpath, "w") as f:
            f.write(now_str)

        return (df_asn_ip4, df_asn_ip6, geo)

    else:
        if trace:
            print("[INFO ] No refresh...")

        df_asn_ip4 = pd.read_csv(ip4_asn_fpath)
        df_asn_ip6 = pd.read_csv(ip6_asn_fpath)
        geo = maxminddb.open_database(ip_geo_fpath)

        return (df_asn_ip4, df_asn_ip6, geo)


def search(ip: IPv4Address | IPv6Address, df: pd.DataFrame) -> pd.Series | None:
    low, high = 0, len(df) - 1
    while low <= high:
        mid = (low + high) // 2
        start_ip = ip_address(df.loc[mid, "Start"])

        if start_ip <= ip:
            # Check if the IP falls within the range of the current middle row
            end_ip = ip_address(df.loc[mid, "End"])
            if ip <= end_ip:
                return df.loc[mid]

            else:
                low = mid + 1
        else:
            high = mid - 1

    return None


def search_database(
    ip: str, asn_v4: pd.DataFrame, asn_v6: pd.DataFrame, geo: GeoDB
) -> IPInfo | None:
    ip_obj = None

    try:
        ip_obj = ip_address(ip)
    except ValueError:
        return None

    # check if IP is for private use
    if ip_obj.is_private:
        return IPInfo(
            country="Private",
            country_c="Private",
            entity="Private Network",
            ent_origin="Private",
            ent_origin_c="Private",
            ent_domain="Private",
        )

    df_asn = asn_v4 if ip_obj.version == 4 else asn_v6

    result_asn = search(ip_obj, df_asn)
    result_geo = geo.get(ip)

    country = None
    country_c = None
    entity = None
    ent_origin = None
    ent_origin_c = None
    ent_domain = None

    if result_asn is not None:
        ent_origin = COUNTRY_CODE_LOOKUP[result_asn["Code"]]
        ent_origin_c = result_asn["Code"]

    if result_geo is not None:
        country = result_geo["country"]
        ent_domain = result_geo.get("as_domain")
        entity = result_geo.get("as_name")
        country_c = result_geo["country_code"]

    if (entity and ent_origin) or country:
        return IPInfo(
            country=country,
            country_c=country_c,
            entity=entity,
            ent_origin=ent_origin,
            ent_origin_c=ent_origin_c,
            ent_domain=ent_domain,
        )

    return None
