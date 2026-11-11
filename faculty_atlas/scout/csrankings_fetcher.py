"""Fetches and filters CSRankings faculty data from GitHub raw CSV files."""

import csv
import io
import re
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict

# DBLP appends " 0001", " 0002", … to disambiguate people with identical names.
# Strip these so "Zhendong Su 0001" and "Zhendong Su" are treated as the same person.
_DBLP_SUFFIX = re.compile(r"\s+\d+$")

_BASE = "https://raw.githubusercontent.com/emeryberger/CSrankings/gh-pages"
_URLS = {
    "faculty": f"{_BASE}/csrankings.csv",
    "country": f"{_BASE}/institutions.csv",
    "author":  f"{_BASE}/generated-author-info.csv",
}

_cache: dict = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 3600  # 1 hour


# ---------------------------------------------------------------------------
# Venue → canonical area code
# ---------------------------------------------------------------------------
VENUE_TO_AREA: dict[str, str] = {
    # Artificial Intelligence
    "aaai": "ai", "ijcai": "ai",
    # Machine Learning
    "icml": "mlmining", "nips": "mlmining", "iclr": "mlmining", "kdd": "mlmining",
    # Computer Vision
    "cvpr": "vision", "eccv": "vision", "iccv": "vision",
    # Natural Language Processing
    "acl": "nlp", "emnlp": "nlp", "naacl": "nlp",
    # Information Retrieval
    "sigir": "ir", "www": "ir",
    # Robotics
    "icra": "robotics", "iros": "robotics", "rss": "robotics",
    # Computer Architecture
    "asplos": "arch", "isca": "arch", "micro": "arch", "hpca": "arch",
    # Computer Networks
    "sigcomm": "comm", "nsdi": "comm", "imc": "comm",
    # Mobile Computing
    "mobicom": "mob", "mobisys": "mob", "sensys": "mob",
    # Computer Security
    "ccs": "sec", "oakland": "sec", "usenixsec": "sec", "ndss": "sec", "pets": "sec",
    # Cryptography
    "crypto": "crypt", "eurocrypt": "crypt",
    # Databases
    "sigmod": "mod", "vldb": "mod", "icde": "mod", "pods": "mod",
    # Design Automation
    "dac": "da", "iccad": "da",
    # Embedded & Real-Time Systems
    "emsoft": "bed", "rtas": "bed", "rtss": "bed",
    # High-Performance Computing
    "sc": "hpc", "hpdc": "hpc", "ics": "hpc",
    # Operating Systems
    "sosp": "ops", "osdi": "ops", "eurosys": "ops", "usenixatc": "ops", "fast": "ops",
    # Programming Languages
    "pldi": "plan", "popl": "plan", "icfp": "plan", "oopsla": "plan",
    # Software Engineering
    "icse": "soft", "fse": "soft", "ase": "soft", "issta": "soft",
    # Algorithms & Complexity
    "stoc": "act", "focs": "act", "soda": "act",
    # Logic & Verification
    "cav": "log", "lics": "log",
    # Economics & Computation
    "ec": "ecom", "wine": "ecom",
    # Bioinformatics
    "ismb": "bio", "recomb": "bio",
    # CS Education
    "sigcse": "csed",
    # Measurement & Performance
    "sigmetrics": "met",
    # Visualization & Graphics
    "vis": "vis", "siggraph": "vis", "siggraph-asia": "vis",
    "eurographics": "vis", "vr": "vis",
    # Human-Computer Interaction
    "chiconf": "chi", "uist": "chi", "ubicomp": "chi",
}

AREA_NAMES: dict[str, str] = {
    "ai":       "Artificial Intelligence",
    "mlmining": "Machine Learning",
    "vision":   "Computer Vision",
    "nlp":      "Natural Language Processing",
    "ir":       "Information Retrieval",
    "robotics": "Robotics",
    "arch":     "Computer Architecture",
    "comm":     "Computer Networks",
    "mob":      "Mobile Computing",
    "sec":      "Computer Security",
    "crypt":    "Cryptography",
    "mod":      "Databases",
    "da":       "Design Automation",
    "bed":      "Embedded & Real-Time Systems",
    "hpc":      "High-Performance Computing",
    "ops":      "Operating Systems",
    "plan":     "Programming Languages",
    "soft":     "Software Engineering",
    "act":      "Algorithms & Complexity",
    "log":      "Logic & Verification",
    "ecom":     "Economics & Computation",
    "bio":      "Bioinformatics",
    "csed":     "CS Education",
    "met":      "Measurement & Performance",
    "vis":      "Visualization & Graphics",
    "chi":      "Human-Computer Interaction",
}

COUNTRY_NAMES: dict[str, str] = {
    "ae": "United Arab Emirates", "ar": "Argentina",   "at": "Austria",
    "au": "Australia",            "bd": "Bangladesh",  "be": "Belgium",
    "bg": "Bulgaria",             "br": "Brazil",      "ca": "Canada",
    "ch": "Switzerland",          "cl": "Chile",       "cn": "China",
    "co": "Colombia",             "cy": "Cyprus",      "cz": "Czech Republic",
    "de": "Germany",              "dk": "Denmark",     "ee": "Estonia",
    "eg": "Egypt",                "es": "Spain",       "fi": "Finland",
    "fr": "France",               "gb": "United Kingdom", "gr": "Greece",
    "hk": "Hong Kong",            "hr": "Croatia",     "hu": "Hungary",
    "id": "Indonesia",            "ie": "Ireland",     "il": "Israel",
    "in": "India",                "ir": "Iran",        "it": "Italy",
    "jo": "Jordan",               "jp": "Japan",       "kr": "South Korea",
    "lb": "Lebanon",              "lk": "Sri Lanka",   "lt": "Lithuania",
    "lu": "Luxembourg",           "lv": "Latvia",      "ma": "Morocco",
    "mo": "Macau",                "mt": "Malta",       "my": "Malaysia",
    "nl": "Netherlands",          "no": "Norway",      "nz": "New Zealand",
    "ph": "Philippines",          "pk": "Pakistan",    "pl": "Poland",
    "pt": "Portugal",             "qa": "Qatar",       "ro": "Romania",
    "rs": "Serbia",               "ru": "Russia",      "sa": "Saudi Arabia",
    "se": "Sweden",               "sg": "Singapore",   "si": "Slovenia",
    "sk": "Slovakia",             "th": "Thailand",    "tr": "Turkey",
    "tw": "Taiwan",               "ua": "Ukraine",     "us": "United States",
    "vn": "Vietnam",              "za": "South Africa",
}

# Reverse lookups (built once at module load, after dicts are defined)
_COUNTRY_BY_NAME: dict[str, str] = {v.lower(): k for k, v in COUNTRY_NAMES.items()}
_AREA_BY_NAME: dict[str, str] = {v.lower(): k for k, v in AREA_NAMES.items()}


def _fetch_url(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "phd-scout/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status} fetching {url}")
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"Failed to fetch CSRankings data from {url}: {e}") from e


def _load_data() -> tuple[list[dict], dict[str, str], dict[str, list[dict]]]:
    """Return (faculty_rows, institution->country_code, name->area_rows). Uses TTL cache."""
    now = time.time()
    with _cache_lock:
        if _cache.get("ts", 0) + _CACHE_TTL > now:
            return _cache["faculty"], _cache["country"], _cache["author"]

        faculty_text = _fetch_url(_URLS["faculty"])
        country_text = _fetch_url(_URLS["country"])
        author_text  = _fetch_url(_URLS["author"])

        seen_faculty: dict[tuple, dict] = {}
        for row in csv.DictReader(io.StringIO(faculty_text)):
            row["name"] = _DBLP_SUFFIX.sub("", row.get("name", "")).strip()
            key = (row["name"], row.get("affiliation", ""))
            if key not in seen_faculty:
                seen_faculty[key] = row
        faculty_rows = list(seen_faculty.values())

        country_map: dict[str, str] = {
            row["institution"]: row.get("countryabbrv", "").lower()
            for row in csv.DictReader(io.StringIO(country_text))
        }

        author_map: dict[str, list[dict]] = defaultdict(list)
        for row in csv.DictReader(io.StringIO(author_text)):
            name = _DBLP_SUFFIX.sub("", row.get("name", "")).strip()
            author_map[name].append({
                "area":  row["area"],
                "count": round(float(row.get("count", 0) or 0)),
                "adj":   float(row.get("adjustedcount", 0) or 0),
            })

        _cache.update({
            "ts": now,
            "faculty": faculty_rows,
            "country": country_map,
            "author": author_map,
        })
        return faculty_rows, country_map, author_map


def fetch_csrankings(filters: dict) -> list[dict]:
    """Return professors from CSRankings matching the given filters.

    Filters:
        country  (str)  — country name (e.g. "Austria") or ISO code (e.g. "at")
        area     (str)  — area name (e.g. "Machine Learning") or code (e.g. "mlmining")
        min_pub  (int)  — minimum total publication count
        min_adj  (float)— minimum total adjusted count
        q        (str)  — substring match on name or affiliation
    """
    faculty_rows, country_map, author_map = _load_data()

    country_raw = (filters.get("country") or "").strip()
    country_f = (
        _COUNTRY_BY_NAME.get(country_raw.lower(), country_raw.lower())
        if len(country_raw) > 2
        else country_raw.lower()
    )

    area_raw = (filters.get("area") or "").strip()
    area_code_f = (
        _AREA_BY_NAME.get(area_raw.lower(), area_raw.lower())
        if area_raw and area_raw not in AREA_NAMES
        else area_raw.lower()
    )

    min_pub = filters.get("min_pub")
    min_adj = filters.get("min_adj")
    q = (filters.get("q") or "").lower().strip()

    results = []
    for row in faculty_rows:
        name        = row.get("name", "").strip()
        affiliation = row.get("affiliation", "").strip()
        homepage    = row.get("homepage", "").strip()
        scholar_id  = row.get("scholarid", "").strip()
        dblp_url    = row.get("dblp", "").strip()

        country_code = country_map.get(affiliation, "")
        area_rows    = author_map.get(name, [])
        venues       = [a["area"] for a in area_rows]
        area_codes   = list(dict.fromkeys(
            VENUE_TO_AREA[v] for v in venues if v in VENUE_TO_AREA
        ))
        pub_count    = sum(a["count"] for a in area_rows)
        adj_count    = sum(a["adj"]   for a in area_rows)

        if country_f and country_code != country_f:
            continue
        if area_code_f and area_code_f not in area_codes:
            continue
        if min_pub is not None and pub_count < min_pub:
            continue
        if min_adj is not None and adj_count < min_adj:
            continue
        if q and q not in name.lower() and q not in affiliation.lower():
            continue

        area_names = [AREA_NAMES[c] for c in area_codes]
        results.append({
            "name":         name,
            "university":   affiliation,
            "homepage_url": homepage or None,
            "scholar_url":  (
                f"https://scholar.google.com/citations?user={scholar_id}"
                if scholar_id else None
            ),
            "dblp_url":     dblp_url or None,
            "country":      COUNTRY_NAMES.get(country_code, country_code or None),
            "country_code": country_code or None,
            "areas":        " · ".join(area_names) if area_names else None,
            "pub_count":    pub_count or None,
            "adj_count":    round(adj_count, 2) if adj_count else None,
            "source":       "csrankings",
        })

    return results


def get_meta() -> dict:
    """Return autocomplete metadata: countries, areas, and institutions present in the data."""
    faculty_rows, country_map, _ = _load_data()

    seen_codes = {country_map.get(row.get("affiliation", ""), "") for row in faculty_rows}
    seen_codes.discard("")

    return {
        "countries": sorted(
            [{"code": c, "name": COUNTRY_NAMES.get(c, c.upper())} for c in seen_codes],
            key=lambda x: x["name"],
        ),
        "areas": sorted(
            [{"code": k, "name": v} for k, v in AREA_NAMES.items()],
            key=lambda x: x["name"],
        ),
        "institutions": sorted(
            row.get("affiliation", "") for row in faculty_rows if row.get("affiliation")
        ),
    }
