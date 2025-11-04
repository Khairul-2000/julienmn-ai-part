
from typing import Optional, List, Dict, Any
from urllib.parse import quote

import httpx

# Stable geosearch useing EN Wikipedia only
EN_GEOSEARCH_API = "https://en.wikipedia.org/w/api.php"

# Get Wikidata QID (wikibase_item) for an EN pageid
EN_PAGEPROPS_API = (
    "https://en.wikipedia.org/w/api.php"
    "?action=query&prop=pageprops&pageids={pageid}&ppprop=wikibase_item&format=json"
)

WIKIDATA_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"

FULL_EXTRACT_URL = (
    "https://{lang}.wikipedia.org/w/api.php"
    "?action=query&prop=extracts&explaintext=1&redirects=1&titles={title}&format=json"
)

# Language-specific REST endpoints
SUMMARY_URL = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
PLAIN_URL   = "https://{lang}.wikipedia.org/api/rest_v1/page/plain/{title}"

async def _get_json(url: str, params: Optional[Dict[str, Any]] = None,
                    headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params or {}, headers=headers or {}, timeout=15)
        r.raise_for_status()
        return r.json()

async def _get_text(url: str, headers: Optional[Dict[str, str]] = None) -> Optional[str]:
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=headers or {}, timeout=20)
        if r.status_code == 200 and r.text:
            return r.text
        return None

async def full_extract(title: str, lang: str) -> Optional[str]:
    """
    Return the full article as plain text (no markup).
    Uses the stable 'extracts' API (works in most languages).
    """
    url = FULL_EXTRACT_URL.format(lang=lang, title=quote(title, safe=""))
    try:
        data = await _get_json(url, headers={"accept-language": lang})
    except httpx.HTTPError:
        return None

    pages = data.get("query", {}).get("pages", {})
    if not pages:
        return None
    page = next(iter(pages.values()))
    txt = page.get("extract")
    if isinstance(txt, str):
        txt = txt.strip()
        return txt if txt else None
    return None

async def geosearch_en(lat: float, lng: float, radius: int = 8000, limit: int = 8) -> List[Dict[str, Any]]:
    """
    Search EN Wikipedia for pages near given coordinates; returns the 'geosearch' list.
    """
    params = {
        "action": "query",
        "list": "geosearch",
        "gscoord": f"{lat}|{lng}",
        "gsradius": radius,
        "gslimit": limit,
        "format": "json",
    }
    data = await _get_json(EN_GEOSEARCH_API, params=params)
    return data.get("query", {}).get("geosearch", [])


async def wikidata_qid_for_pageid(pageid: int) -> Optional[str]:
    """
    Given an EN Wikipedia pageid, return the Wikidata QID (e.g., 'Q12345').
    """
    url = EN_PAGEPROPS_API.format(pageid=pageid)
    data = await _get_json(url)
    pages = data.get("query", {}).get("pages", {})
    if not pages:
        return None
    page = next(iter(pages.values()))
    return (page.get("pageprops") or {}).get("wikibase_item")


async def title_in_lang_from_qid(qid: str, lang: str) -> Optional[str]:
    """
    Given a Wikidata QID and target language, return the exact page title
    on that language's Wikipedia (via sitelinks). Returns None if missing.
    """
    if not qid:
        return None
    data = await _get_json(WIKIDATA_ENTITY.format(qid=qid))
    ent = data.get("entities", {}).get(qid, {})
    sitelinks = ent.get("sitelinks", {})
    key = f"{lang}wiki"
    link = sitelinks.get(key)
    if link and link.get("title"):
        return link["title"]
    return None


async def summary_in_lang(title: str, lang: str) -> Optional[Dict[str, Any]]:
    """
    REST summary for a given title on a specific language wiki.
    """
    try:
        url = SUMMARY_URL.format(lang=lang, title=quote(title, safe=""))
        data = await _get_json(url, headers={"accept-language": lang})
        if not isinstance(data, dict) or data.get("type", "").endswith("problem+json"):
            return None
        return data
    except httpx.HTTPError:
        return None


async def plain_text(title: str, lang: str) -> Optional[str]:
    """
    Fetch plain article text (no markup) for richer "Tell me more".
    Falls back to None if the endpoint isn't available.
    """
    url = PLAIN_URL.format(lang=lang, title=quote(title, safe=""))
    try:
        text = await _get_text(url, headers={"accept-language": lang, "accept": "text/plain"})
        return text.strip() if text else None
    except httpx.HTTPError:
        return None


def normalize(candidate: Dict[str, Any], s: Dict[str, Any], lang: str) -> Dict[str, Any]:
    """
    Shape a single place entry for the API response.
    - candidate: row from geosearch (lat/lon/pageid/title)
    - s: REST summary payload from the language wiki
    """
    return {
        "title": s.get("title") or candidate.get("title"),
        "normalized_title": (s.get("titles") or {}).get("normalized") or s.get("title"),
        "description": s.get("description"),
        "extract": s.get("extract"),
        "coordinates": {"lat": candidate.get("lat"), "lng": candidate.get("lon")},
        # Distance intentionally omitted per product choice
        "page_url": ((s.get("content_urls") or {}).get("desktop") or {}).get("page"),
        "thumbnail_url": (s.get("thumbnail") or {}).get("source"),
        "original_image_url": (s.get("originalimage") or {}).get("source"),
        "pageid": candidate.get("pageid"),
        "lang": lang,
    }