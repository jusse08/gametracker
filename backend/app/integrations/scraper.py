import requests
from bs4 import BeautifulSoup
from typing import List, Optional, Dict
import re
from urllib.parse import urlparse, unquote
import time
import logging

logger = logging.getLogger(__name__)

# Rate limiting: delay between API requests to avoid being blocked
REQUEST_DELAY = 0.5  # seconds

def _is_fandom_url(url: str) -> bool:
    """Checks if the URL belongs to a Fandom/Wikia site."""
    return 'fandom.com' in url or 'wikia.org' in url

def _extract_fandom_info(url: str):
    """Extracts base domain and page title from a Fandom URL."""
    parsed = urlparse(url)
    domain = parsed.netloc
    path_parts = parsed.path.split('/')
    if len(path_parts) >= 3 and path_parts[1] == 'wiki':
        title = unquote(path_parts[2])
        return domain, title
    return None, None

def _fetch_fandom_api(domain: str, title: str, depth: int = 0, category_context: Optional[str] = None) -> List[Dict[str, str]]:
    """Uses MediaWiki API to fetch data from Fandom with redirect support."""
    if depth > 2:
        return []

    api_url = f"https://{domain}/api.php"
    items = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    # Rate limiting
    time.sleep(REQUEST_DELAY)

    # Normalize title: replace spaces with underscores, but MediaWiki is case-sensitive for the first letter
    normalized_title = title.replace(' ', '_')

    # Case 1: Category page
    if normalized_title.startswith('Category:'):
        current_cat = category_context or normalized_title.replace('Category:', '').replace('_', ' ')
        
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": normalized_title,
            "cmlimit": 500,
            "format": "json",
            "origin": "*"
        }
        try:
            res = requests.get(api_url, params=params, headers=headers, timeout=10)
            res.raise_for_status()
            data = res.json()
            if 'query' in data and 'categorymembers' in data['query']:
                members = data['query']['categorymembers']
                if not members and depth == 0:
                    logger.info("Fandom category is empty: %s", normalized_title)
                    
                for member in members:
                    ns = member.get('ns')
                    m_title = member.get('title')
                    
                    if ns == 0: # Regular Page
                        items.append({"title": m_title, "category": current_cat})
                    elif ns == 14: # Subcategory
                        sub_cat_name = m_title.replace('Category:', '').replace('_', ' ')
                        sub_items = _fetch_fandom_api(domain, m_title, depth + 1, category_context=sub_cat_name)
                        items.extend(sub_items)
        except Exception:
            logger.exception("Fandom API category fetch failed: %s", normalized_title)

    # Case 2: Regular page - Use 'parse' but with 'redirects=1' equivalent (via query first if needed)
    if not items and depth == 0:
        # First, resolve the true title in case of redirects
        resolve_params = {
            "action": "query",
            "titles": normalized_title,
            "redirects": 1,
            "format": "json",
            "origin": "*"
        }
        actual_title = normalized_title
        try:
            r_res = requests.get(api_url, params=resolve_params, headers=headers, timeout=10)
            r_data = r_res.json()
            if 'query' in r_data and 'pages' in r_data['query']:
                pages = r_data['query']['pages']
                page_id = list(pages.keys())[0]
                if page_id != "-1":
                    actual_title = pages[page_id]['title']
                else:
                    logger.warning("Fandom title not found: %s on %s", normalized_title, domain)
                    return []
        except Exception:
            logger.exception("Fandom redirect resolution failed for %s", normalized_title)

        # Now parse the actual title
        parse_params = {
            "action": "parse",
            "page": actual_title,
            "prop": "text",
            "format": "json",
            "origin": "*"
        }
        try:
            res = requests.get(api_url, params=parse_params, headers=headers, timeout=10)
            res.raise_for_status()
            data = res.json()
            if 'parse' in data and 'text' in data['parse']:
                html_content = data['parse']['text']['*']
                items = _parse_html_lists(html_content, default_category=actual_title.replace('_', ' '))
            else:
                logger.warning("Fandom parse returned empty content: %s", actual_title)
        except Exception:
            logger.exception("Fandom parse failed for %s", actual_title)

    return items

def _parse_html_lists(html: str, default_category: str = "General") -> List[Dict[str, str]]:
    """Helper to extract clean list items from HTML content, using headers as categories."""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    
    # Remove junk before processing
    for junk in soup.find_all(['table', 'div'], class_=['navbox', 'toc', 'sidebar', 'client-js', 'asst-ad']):
        junk.decompose()
        
    content_div = soup.find(id='mw-content-text') or soup
    
    # We'll iterate through elements to track the current heading
    current_category = default_category
    
    for element in content_div.find_all(['h2', 'h3', 'h4', 'ul', 'ol']):
        if element.name in ['h2', 'h3', 'h4']:
            # Update current category from header
            new_cat = element.get_text(strip=True).replace('[edit]', '').strip()
            # Ignore very short or navigation-like headers
            if len(new_cat) > 2 and new_cat.lower() not in ['notes', 'references', 'see also', 'gallery', 'external links']:
                current_category = new_cat
        else:
            # It's a list (ul/ol)
            list_items = element.find_all('li', recursive=False)
            for li in list_items:
                text = li.get_text(strip=True)
                # Validation: not empty, not too long, not a TOC item (usually starts with numbers)
                if text and 3 < len(text) < 150:
                    # Filter TOC-looking items like "1.1 Mission Name"
                    if re.match(r'^\d+(\.\d+)*\s+', text):
                        # Some wikis have numbering in content, but if it looks too much like TOC navigation, skip
                        # Actually, let's just clean the numbers if it's a real mission
                        text = re.sub(r'^\d+(\.\d+)*\s+', '', text)
                    
                    if text.lower() in ['navigation', 'search']: continue

                    text = re.sub(r'\[\d+\]', '', text)
                    text = re.sub(r'\[edit\]', '', text, flags=re.IGNORECASE)
                    
                    if text:
                        items.append({
                            "title": text.strip(),
                            "category": current_category
                        })
                
    return items

def parse_wiki_missions(url: str) -> List[Dict[str, str]]:
    """
    Fetches the URL and extracts potential mission/checklist items with categories.
    """
    items = []
    
    if _is_fandom_url(url):
        domain, title = _extract_fandom_info(url)
        if domain and title:
            items = _fetch_fandom_api(domain, title)
            if items:
                logger.info("Fetched %s items via Fandom API", len(items))
                return _deduplicate(items)

    # Fallback
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        items = _parse_html_lists(response.text)
    except Exception:
        logger.exception("Error parsing wiki missions from %s", url)

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
