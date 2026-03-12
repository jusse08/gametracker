import json
import random
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

REQUEST_DELAY = 0.35
MIN_ARTICLE_WORDS = 25
MAX_FACT_LENGTH = 180

DEFAULT_SEED_URLS = [
    "https://eldenring.fandom.com/wiki/Category:Characters",
    "https://eldenring.fandom.com/wiki/Category:Bosses",
    "https://sonic.fandom.com/wiki/Category:Characters",
    "https://streetsofrage.fandom.com/wiki/Category:Characters",
    "https://metalgear.fandom.com/wiki/Category:Characters",
    "https://tekken.fandom.com/wiki/Category:Characters",
    "https://mortalkombat.fandom.com/wiki/Category:Characters",
]

INVALID_PREFIXES = (
    "Category:",
    "Template:",
    "File:",
    "Help:",
    "User:",
    "Talk:",
    "Portal:",
    "Special:",
    "Module:",
)
GENERIC_LIST_TITLES = {
    "characters",
    "bosses",
    "npcs",
    "enemies",
    "items",
    "weapons",
    "armor",
    "locations",
}


def _project_root() -> Path:
    cursor = Path(__file__).resolve()
    for parent in cursor.parents:
        if (parent / ".git").exists():
            return parent
    return Path.cwd()


def facts_json_path() -> Path:
    docker_path = Path("/app/data/game_facts.json")
    if docker_path.parent.exists():
        return docker_path
    return _project_root() / "gametracker_data" / "game_facts.json"


def _api_url(domain: str, lang_prefix: str = "") -> str:
    if lang_prefix:
        return f"https://{domain}/{lang_prefix}/api.php"
    return f"https://{domain}/api.php"


def _is_fandom_url(url: str) -> bool:
    return "fandom.com" in url or "wikia.org" in url


def _extract_fandom_info(url: str) -> Tuple[Optional[str], Optional[str], str]:
    parsed = urlparse(url)
    domain = parsed.netloc.strip().lower()
    path_parts = [part for part in parsed.path.split("/") if part]
    if not domain or "wiki" not in path_parts:
        return None, None, ""
    wiki_idx = path_parts.index("wiki")
    if wiki_idx + 1 >= len(path_parts):
        return None, None, ""
    lang_prefix = path_parts[wiki_idx - 1] if wiki_idx > 0 and len(path_parts[wiki_idx - 1]) <= 5 else ""
    return domain, unquote(path_parts[wiki_idx + 1]).replace(" ", "_"), lang_prefix


def _is_bad_title(title: str) -> bool:
    clean = title.strip()
    if not clean:
        return True
    if clean.startswith(INVALID_PREFIXES):
        return True
    if clean.replace("_", " ").strip().lower() in GENERIC_LIST_TITLES:
        return True
    return False


def _normalize_text(text: str) -> str:
    clean = re.sub(r"\[[^\]]+\]", "", text)
    clean = clean.replace("\u00a0", " ")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _humanize_slug(slug: str) -> str:
    return slug.replace("_", " ").strip()


def infer_game_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if ".fandom.com" in host:
        sub = host.split(".fandom.com")[0].replace("-", " ").replace("_", " ").strip()
        if sub:
            return " ".join(part.capitalize() for part in sub.split())
    return "Unknown Game"


def _split_sentences(text: str) -> List[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", normalized) if part.strip()]
    return parts


def _is_generic_sentence(sentence: str, title: str) -> bool:
    s = sentence.lower()
    t = title.replace("_", " ").lower()
    if "disambiguation" in s or "may refer to" in s:
        return True
    patterns = [
        rf"^{re.escape(t)}\s+is\s+(a|an|the)\s+",
        rf"^{re.escape(t)}\s+was\s+(a|an|the)\s+",
        r"\bfictional character\b",
        r"\bvideo game\b",
        r"\bmedia franchise\b",
        r"\bthis article\b",
        r"\bthis page\b",
    ]
    return any(re.search(pattern, s) for pattern in patterns)


def _is_unusable_sentence(sentence: str) -> bool:
    s = sentence.lower()
    if len(s) < 35:
        return True
    stat_noise = [
        " hp ",
        " location ",
        " locations ",
        " drops ",
        " runes ",
        "weakness",
        "overview",
        "boss type",
        "enemy type",
        "fp cost",
        "acquisition",
    ]
    if any(token in f" {s} " for token in stat_noise):
        return True
    if ":" in sentence and sentence.count(":") >= 2:
        return True
    return False


def _choose_fact_sentence(sentences: List[str], title: str) -> Optional[str]:
    if not sentences:
        return None

    first = sentences[0]
    if len(first) >= 45 and not _is_generic_sentence(first, title) and not _is_unusable_sentence(first):
        return first

    for candidate in sentences[1:4]:
        if (
            len(candidate) >= 35
            and not _is_generic_sentence(candidate, title)
            and not _is_unusable_sentence(candidate)
        ):
            return candidate

    return first if len(first) >= 35 and not _is_unusable_sentence(first) else None


def _trim_fact(text: str, max_len: int = MAX_FACT_LENGTH) -> str:
    if len(text) <= max_len:
        return text
    trimmed = text[: max_len - 1].rsplit(" ", 1)[0].strip()
    return f"{trimmed}…"


def _extract_candidate_sentence(text: str, title: str) -> Optional[str]:
    sentence = _choose_fact_sentence(_split_sentences(text), title)
    if not sentence:
        return None
    sentence = _trim_fact(sentence)
    if not sentence.endswith((".", "!", "?")):
        sentence = f"{sentence}."
    return sentence


def _build_fact(title: str, extract: str) -> Optional[Dict[str, str]]:
    if len(_normalize_text(extract).split()) < MIN_ARTICLE_WORDS:
        return None

    sentence = _extract_candidate_sentence(extract, title)
    if not sentence:
        return None

    return {"GAME": _humanize_slug(title), "FACT": sentence}


def _request_json(api_url: str, params: Dict[str, str], timeout: int = 12) -> Dict:
    headers = {
        "User-Agent": "GameTrackerFactsBot/1.0 (+https://github.com)",
    }
    time.sleep(REQUEST_DELAY)
    res = requests.get(api_url, params=params, headers=headers, timeout=timeout)
    res.raise_for_status()
    payload = res.json()
    return payload if isinstance(payload, dict) else {}


def _fetch_category_titles(domain: str, category_title: str, limit: int = 80, lang_prefix: str = "") -> List[str]:
    titles: List[str] = []
    api_url = _api_url(domain, lang_prefix)
    cmcontinue: Optional[str] = None

    while len(titles) < limit:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category_title,
            "cmtype": "page",
            "cmnamespace": "0",
            "cmlimit": str(min(100, limit - len(titles))),
            "format": "json",
            "origin": "*",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue

        data = _request_json(api_url, params)
        members = data.get("query", {}).get("categorymembers", [])
        for member in members:
            title = str(member.get("title", "")).strip().replace(" ", "_")
            if title and not _is_bad_title(title):
                titles.append(title)

        cmcontinue = data.get("continue", {}).get("cmcontinue")
        if not cmcontinue:
            break

    return list(dict.fromkeys(titles))


def _fetch_extract(domain: str, title: str, lang_prefix: str = "") -> Optional[str]:
    api_url = _api_url(domain, lang_prefix)
    params = {
        "action": "query",
        "prop": "extracts",
        "titles": title,
        "redirects": "1",
        "explaintext": "1",
        "exintro": "1",
        "format": "json",
        "origin": "*",
    }
    data = _request_json(api_url, params)
    pages = data.get("query", {}).get("pages", {})
    if not isinstance(pages, dict):
        return None

    for page in pages.values():
        if not isinstance(page, dict):
            continue
        extract = page.get("extract")
        if isinstance(extract, str) and extract.strip():
            return extract
    # Fandom wikis often don't expose prop=extracts. Fallback to parse->HTML.
    parse_params = {
        "action": "parse",
        "page": title,
        "prop": "text",
        "format": "json",
        "origin": "*",
    }
    data = _request_json(api_url, parse_params)
    html = data.get("parse", {}).get("text", {}).get("*")
    if not isinstance(html, str) or not html.strip():
        return None
    soup = BeautifulSoup(html, "html.parser")
    for junk in soup.select(
        "table, aside, .toc, .navbox, .infobox, .portable-infobox, .pi-item, .reference, .thumb, script, style"
    ):
        junk.decompose()
    root = soup.select_one(".mw-parser-output") or soup
    direct_paragraphs = [p.get_text(" ", strip=True) for p in root.find_all("p", recursive=False)]
    paragraphs = direct_paragraphs if direct_paragraphs else [p.get_text(" ", strip=True) for p in root.find_all("p")]
    clean_paragraphs = []
    for paragraph in paragraphs:
        normalized = _normalize_text(paragraph)
        if len(normalized.split()) < 10:
            continue
        if _is_unusable_sentence(normalized):
            continue
        clean_paragraphs.append(normalized)
        if len(clean_paragraphs) >= 2:
            break
    text = " ".join(clean_paragraphs)
    return text if text else None


def _titles_from_seed(url: str, per_seed_limit: int) -> Tuple[str, str, List[str]]:
    domain, title, lang_prefix = _extract_fandom_info(url)
    if not domain or not title:
        return "", "", []

    if title.startswith("Category:"):
        return domain, lang_prefix, _fetch_category_titles(domain, title, limit=per_seed_limit, lang_prefix=lang_prefix)
    return domain, lang_prefix, [title]


def collect_facts_from_fandom_page(page_url: str, game: Optional[str] = None, max_facts: int = 200) -> List[Dict[str, str]]:
    domain, title, lang_prefix = _extract_fandom_info(page_url)
    if not domain or not title:
        return []

    api_url = _api_url(domain, lang_prefix)
    parse_params = {
        "action": "parse",
        "page": title,
        "prop": "text",
        "format": "json",
        "origin": "*",
    }
    data = _request_json(api_url, parse_params)
    html = data.get("parse", {}).get("text", {}).get("*")
    if not isinstance(html, str) or not html.strip():
        return []

    soup = BeautifulSoup(html, "html.parser")
    for junk in soup.select(
        "table, aside, .toc, .navbox, .infobox, .portable-infobox, .pi-item, .reference, .thumb, script, style"
    ):
        junk.decompose()
    root = soup.select_one(".mw-parser-output") or soup
    current_section = ""
    facts: List[Dict[str, str]] = []
    seen = set()
    game_name = (game or infer_game_name_from_url(page_url)).strip() or "Unknown Game"
    page_title = _humanize_slug(title)

    skip_sections = {"см. также", "примечания", "ссылки", "история", "галерея"}

    for node in root.find_all(["h2", "h3", "p", "li"]):
        if len(facts) >= max_facts:
            break

        if node.name in {"h2", "h3"}:
            heading = _normalize_text(node.get_text(" ", strip=True)).replace("[править]", "").strip(" :")
            heading_lc = heading.lower()
            if heading and heading_lc not in skip_sections:
                current_section = heading
            else:
                current_section = ""
            continue

        raw_text = _normalize_text(node.get_text(" ", strip=True))
        if not raw_text:
            continue
        if any(prefix in raw_text for prefix in ("Category:", "Template:", "File:", "Image:")):
            continue
        if len(raw_text.split()) < 7:
            continue

        sentence = _extract_candidate_sentence(raw_text, page_title)
        if not sentence:
            continue
        if _is_unusable_sentence(sentence):
            continue

        fact_text = sentence

        key = fact_text.lower()
        if key in seen:
            continue
        seen.add(key)

        facts.append(
            {
                "GAME": game_name,
                "FACT": fact_text,
            }
        )
    return facts


def collect_fandom_facts(
    seed_urls: Optional[List[str]] = None,
    per_seed_limit: int = 60,
    max_facts: int = 600,
) -> List[Dict[str, str]]:
    seeds = seed_urls or DEFAULT_SEED_URLS
    facts: List[Dict[str, str]] = []
    seen_facts = set()

    for seed in seeds:
        if not _is_fandom_url(seed):
            continue
        try:
            domain, lang_prefix, titles = _titles_from_seed(seed, per_seed_limit)
        except Exception:
            continue
        if not domain or not titles:
            continue
        random.shuffle(titles)

        for title in titles:
            if len(facts) >= max_facts:
                return facts
            if _is_bad_title(title):
                continue

            try:
                extract = _fetch_extract(domain, title, lang_prefix=lang_prefix)
            except Exception:
                continue
            if not extract:
                continue

            fact = _build_fact(title, extract)
            if not fact:
                continue

            key = fact["fact"].lower()
            if key in seen_facts:
                continue
            seen_facts.add(key)
            facts.append(fact)

    return facts


def save_facts_json(facts: List[Dict[str, str]], path: Optional[Path] = None) -> Path:
    destination = path or facts_json_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as f:
        json.dump(facts, f, ensure_ascii=False, indent=2)
    return destination


def load_facts_json(path: Optional[Path] = None) -> List[Dict[str, str]]:
    source = path or facts_json_path()
    if not source.exists():
        return []
    try:
        with source.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            result: List[Dict[str, str]] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                fact = item.get("FACT") or item.get("fact")
                game = item.get("GAME") or item.get("game") or item.get("title")
                if isinstance(fact, str) and fact.strip():
                    result.append({"GAME": str(game or "Unknown Game"), "FACT": fact.strip()})
            return result
    except Exception:
        return []
    return []


def fetch_random_fandom_fact() -> Dict[str, str]:
    facts = load_facts_json()
    if not facts:
        raise RuntimeError("Facts file is empty. Run Fandom facts parser first.")

    item = random.choice(facts)
    game = str(item.get("GAME", "")).strip() or "Unknown Game"
    fact = str(item.get("FACT", "")).strip()
    if not fact:
        raise RuntimeError("Invalid fact in facts file")
    return {"text": f"{game}: {fact}", "game_title": game, "source": "fandom"}
