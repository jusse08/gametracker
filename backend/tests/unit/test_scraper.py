from app.integrations import scraper


class DummyResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None


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
        scraper.requests,
        "get",
        lambda *args, **kwargs: DummyResponse(text=html),
    )

    items = scraper.parse_wiki_missions("https://example.com/wiki/test-page")
    assert items == [
        {"title": "Prologue", "category": "Main missions"},
        {"title": "Final Battle", "category": "Main missions"},
        {"title": "Collect 10 herbs", "category": "Side content"},
    ]
