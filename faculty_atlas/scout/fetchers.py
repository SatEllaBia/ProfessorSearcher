"""Async fetchers for professor data from DBLP, OpenAlex, and arXiv."""

import logging
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote

import aiohttp

_log = logging.getLogger(__name__)

# How many items to keep from each source
_MAX_DBLP_PUBLICATIONS = 20
_OPENALEX_CANDIDATE_AUTHORS = 5
_MAX_OPENALEX_WORKS = 10
_MAX_ARXIV_PAPERS = 10


def _reconstruct_abstract(inverted_index: dict) -> str:
    """Reconstruct an abstract from an OpenAlex inverted index.

    The index maps word -> [position, ...]. Positions are sorted and joined.
    """
    if not inverted_index:
        return ""
    positions: dict[int, str] = {}
    for word, pos_list in inverted_index.items():
        for pos in pos_list:
            positions[pos] = word
    return " ".join(positions[i] for i in sorted(positions))


async def fetch_dblp(dblp_url: str) -> dict | None:
    """Fetch and parse DBLP publications for a professor.

    Args:
        dblp_url: DBLP profile URL (e.g. https://dblp.org/pid/93/2189)

    Returns:
        {"publications": [...up to 20, sorted by year desc...]} or None on failure.
    """
    try:
        match = re.search(r"dblp\.org/pid/(.+?)(?:\.html|\.xml)?$", dblp_url)
        if not match:
            return None
        pid = match.group(1)
        xml_url = f"https://dblp.org/pid/{pid}.xml"

        async with aiohttp.ClientSession() as session:
            async with session.get(
                xml_url, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    return None
                content = await resp.text()

        root = ET.fromstring(content)

        publications = []
        for r_elem in root.findall(".//r"):
            for pub_elem in r_elem:
                title_elem = pub_elem.find("title")
                year_elem = pub_elem.find("year")
                if title_elem is None or year_elem is None:
                    continue

                title = (title_elem.text or "").strip().rstrip(".")
                try:
                    year = int(year_elem.text)
                except (TypeError, ValueError):
                    continue

                venue_elem = pub_elem.find("booktitle") or pub_elem.find("journal")
                venue = (venue_elem.text or "").strip() if venue_elem is not None else ""

                publications.append({"title": title, "year": year, "venue": venue})
                break  # only one publication per <r>

        publications.sort(key=lambda p: p["year"], reverse=True)
        return {"publications": publications[:_MAX_DBLP_PUBLICATIONS]}

    except (aiohttp.ClientError, TimeoutError, ET.ParseError, ValueError, KeyError) as e:
        _log.debug("fetch_dblp failed for %s: %s", dblp_url, e)
        return None


async def fetch_openalex(name: str, university: str) -> dict | None:
    """Fetch author data and recent works from OpenAlex.

    Args:
        name: Professor's full name (e.g. "Martin T. Vechev")
        university: Institution name to match (e.g. "ETH Zurich")

    Returns:
        Dict with openalex_id, h_index, cited_by_count, works_count, topics, works
        or None on failure.
    """
    try:
        search_url = (
            f"https://api.openalex.org/authors"
            f"?search={quote(name)}&per_page={_OPENALEX_CANDIDATE_AUTHORS}"
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(
                search_url, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

        results = data.get("results", [])
        if not results:
            return None

        # Prefer a result whose institution name contains the university string
        university_lower = university.lower()
        matched = next(
            (
                r for r in results
                if any(
                    university_lower in inst.get("display_name", "").lower()
                    for inst in (r.get("last_known_institutions") or [])
                )
            ),
            results[0],  # fall back to first result
        )

        author_id = matched["id"].rstrip("/").split("/")[-1]
        h_index = matched.get("summary_stats", {}).get("h_index", 0)
        cited_by_count = matched.get("cited_by_count", 0)
        works_count = matched.get("works_count", 0)
        topics = [
            t["display_name"]
            for t in matched.get("topics", [])[:5]
            if "display_name" in t
        ]

        works_url = (
            f"https://api.openalex.org/works"
            f"?filter=author.id:{author_id}"
            f"&sort=publication_date:desc&per_page={_MAX_OPENALEX_WORKS}"
            f"&select=title,publication_year,primary_location,abstract_inverted_index,topics"
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(
                works_url, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    return None
                works_data = await resp.json()

        works = []
        for work in works_data.get("results", []):
            source = (work.get("primary_location") or {}).get("source") or {}
            works.append({
                "title": work.get("title") or "",
                "year": work.get("publication_year"),
                "venue": source.get("display_name", ""),
                "abstract": _reconstruct_abstract(
                    work.get("abstract_inverted_index") or {}
                ),
                "topics": [
                    t["display_name"]
                    for t in (work.get("topics") or [])[:3]
                    if "display_name" in t
                ],
            })

        return {
            "openalex_id": author_id,
            "h_index": h_index,
            "cited_by_count": cited_by_count,
            "works_count": works_count,
            "topics": topics,
            "works": works,
        }

    except (aiohttp.ClientError, TimeoutError, ValueError, KeyError) as e:
        _log.debug("fetch_openalex failed for %s: %s", name, e)
        return None


async def fetch_arxiv(lastname: str) -> dict | None:
    """Fetch recent arXiv papers by author last name.

    Args:
        lastname: Author's last name (e.g. "Vechev")

    Returns:
        {"papers": [{"title", "abstract", "year", "categories"}]} or None on failure.
    """
    try:
        url = (
            f"https://export.arxiv.org/api/query"
            f"?search_query=au:{quote(lastname)}"
            f"&start=0&max_results={_MAX_ARXIV_PAPERS}"
            f"&sortBy=submittedDate&sortOrder=descending"
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return None
                content = await resp.text()

        ns = "http://www.w3.org/2005/Atom"
        arxiv_ns = "http://arxiv.org/schemas/atom"
        root = ET.fromstring(content)

        papers = []
        for entry in root.findall(f"{{{ns}}}entry"):
            title_elem = entry.find(f"{{{ns}}}title")
            summary_elem = entry.find(f"{{{ns}}}summary")
            published_elem = entry.find(f"{{{ns}}}published")

            title = (title_elem.text or "").strip() if title_elem is not None else ""
            abstract = (summary_elem.text or "").strip() if summary_elem is not None else ""
            year = (
                published_elem.text[:4]
                if published_elem is not None and published_elem.text
                else ""
            )

            categories = [
                cat.get("term", "")
                for cat in entry.findall(f"{{{ns}}}category")
                if cat.get("term")
            ]
            for cat in entry.findall(f"{{{arxiv_ns}}}primary_category"):
                term = cat.get("term", "")
                if term and term not in categories:
                    categories.append(term)

            if title:
                papers.append({
                    "title": title,
                    "abstract": abstract,
                    "year": year,
                    "categories": categories,
                })

        return {"papers": papers}

    except (aiohttp.ClientError, TimeoutError, ET.ParseError, ValueError) as e:
        _log.debug("fetch_arxiv failed for %s: %s", lastname, e)
        return None
