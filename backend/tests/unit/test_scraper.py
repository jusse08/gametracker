from app.integrations import scraper


class DummyResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None


class DummyClient:
    def __init__(self, text: str):
        self._text = text

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, *_args, **_kwargs):
        return DummyResponse(text=self._text)


def test_parse_wiki_missions_extracts_categories_and_deduplicates(monkeypatch):
    html = """
    <div id="mw-content-text">
      <h2>Main missions</h2>
      <ul>
        <li>Prologue</li>
        <li>Prologue</li>
        <li>Final Battle</li>
      </ul>
      <h2>Side content</h2>
      <ul>
        <li>Collect 10 herbs</li>
      </ul>
    </div>
    """

    monkeypatch.setattr(
        scraper.httpx,
        "Client",
        lambda *args, **kwargs: DummyClient(text=html),
    )

    items = scraper.parse_wiki_missions("https://example.com/wiki/test-page")
    assert items == [
        {"title": "Prologue", "category": "Main missions"},
        {"title": "Final Battle", "category": "Main missions"},
        {"title": "Collect 10 herbs", "category": "Side content"},
    ]
