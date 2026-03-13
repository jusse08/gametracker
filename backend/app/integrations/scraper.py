import logging
import re
import time
from typing import Dict, List, Optional
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Rate limiting: delay between API requests to avoid being blocked
REQUEST_DELAY = 0.5  # seconds


def _is_fandom_url(url: str) -> bool:
    """Checks if the URL belongs to a Fandom/Wikia site."""
    return "fandom.com" in url or "wikia.org" in url


def _extract_fandom_info(url: str):
    """Extracts base domain and page title from a Fandom URL."""
    parsed = urlparse(url)
    domain = parsed.netloc
    path_parts = parsed.path.split("/")
    if len(path_parts) >= 3 and path_parts[1] == "wiki":
        title = unquote(path_parts[2])
        return domain, title
    return None, None


def _fetch_fandom_api(
    domain: str,
    title: str,
    depth: int = 0,
    category_context: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Uses MediaWiki API to fetch data from Fandom with redirect support."""
    if depth > 2:
        return []

    api_url = f"https://{domain}/api.php"
    items: List[Dict[str, str]] = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    time.sleep(REQUEST_DELAY)
    normalized_title = title.replace(" ", "_")

    if normalized_title.startswith("Category:"):
        current_cat = category_context or normalized_title.replace("Category:", "").replace("_", " ")
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": normalized_title,
            "cmlimit": 500,
            "format": "json",
            "origin": "*",
        }
        try:
            response = requests.get(api_url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError):
            logger.exception("Fandom API category fetch failed: %s", normalized_title)
        else:
            members = data.get("query", {}).get("categorymembers", [])
            if not members and depth == 0:
                logger.info("Fandom category is empty: %s", normalized_title)

            for member in members:
                namespace = member.get("ns")
                member_title = member.get("title")
                if not member_title:
                    continue
                if namespace == 0:
                    items.append({"title": member_title, "category": current_cat})
                elif namespace == 14:
                    sub_cat_name = member_title.replace("Category:", "").replace("_", " ")
                    items.extend(
                        _fetch_fandom_api(
                            domain,
                            member_title,
                            depth + 1,
                            category_context=sub_cat_name,
                        )
                    )

    if not items and depth == 0:
        resolve_params = {
            "action": "query",
            "titles": normalized_title,
            "redirects": 1,
            "format": "json",
            "origin": "*",
        }
        actual_title = normalized_title
        try:
            response = requests.get(api_url, params=resolve_params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError):
            logger.exception("Fandom redirect resolution failed for %s", normalized_title)
        else:
            pages = data.get("query", {}).get("pages", {})
            if isinstance(pages, dict) and pages:
                page_id = next(iter(pages))
                page = pages.get(page_id, {})
                if page_id == "-1":
                    logger.warning("Fandom title not found: %s on %s", normalized_title, domain)
                    return []
                actual_title = page.get("title", actual_title)

        parse_params = {
            "action": "parse",
            "page": actual_title,
            "prop": "text",
            "format": "json",
            "origin": "*",
        }
        try:
            response = requests.get(api_url, params=parse_params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError):
            logger.exception("Fandom parse failed for %s", actual_title)
        else:
            html_content = data.get("parse", {}).get("text", {}).get("*")
            if isinstance(html_content, str) and html_content:
                items = _parse_html_lists(html_content, default_category=actual_title.replace("_", " "))
            else:
                logger.warning("Fandom parse returned empty content: %s", actual_title)

    return items


def _parse_html_lists(html: str, default_category: str = "General") -> List[Dict[str, str]]:
    """Helper to extract clean list items from HTML content, using headers as categories."""
    soup = BeautifulSoup(html, "html.parser")
    items = []

    for junk in soup.find_all(["table", "div"], class_=["navbox", "toc", "sidebar", "client-js", "asst-ad"]):
        junk.decompose()

    content_div = soup.find(id="mw-content-text") or soup
    current_category = default_category

    for element in content_div.find_all(["h2", "h3", "h4", "ul", "ol"]):
        if element.name in ["h2", "h3", "h4"]:
            new_cat = element.get_text(strip=True).replace("[edit]", "").strip()
            if len(new_cat) > 2 and new_cat.lower() not in [
                "notes",
                "references",
                "see also",
                "gallery",
                "external links",
            ]:
                current_category = new_cat
            continue

        list_items = element.find_all("li", recursive=False)
        for li in list_items:
            text = li.get_text(strip=True)
            if not text or not 3 < len(text) < 150:
                continue
            if re.match(r"^\d+(\.\d+)*\s+", text):
                text = re.sub(r"^\d+(\.\d+)*\s+", "", text)
            if text.lower() in ["navigation", "search"]:
                continue

            text = re.sub(r"\[\d+\]", "", text)
            text = re.sub(r"\[edit\]", "", text, flags=re.IGNORECASE)
            text = text.strip()
            if text:
                items.append({"title": text, "category": current_category})

    return items


def parse_wiki_missions(url: str) -> List[Dict[str, str]]:
    """
    Fetch the URL and extract potential mission/checklist items with categories.
    """
    items: List[Dict[str, str]] = []

    if _is_fandom_url(url):
        domain, title = _extract_fandom_info(url)
        if domain and title:
            items = _fetch_fandom_api(domain, title)
            if items:
                logger.info("Fetched %s items via Fandom API", len(items))
                return _deduplicate(items)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("Error fetching wiki missions from %s", url)
        return []

    items = _parse_html_lists(response.text)
    return _deduplicate(items)


def _deduplicate(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Deduplicates items by title while preserving order."""
    seen = set()
    result = []
    for item in items:
        if item["title"] not in seen:
            result.append(item)
            seen.add(item["title"])
    return result
