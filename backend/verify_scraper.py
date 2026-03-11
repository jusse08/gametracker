from scraper import parse_wiki_missions

def test_scraper():
    urls = [
        # Fandom Category
        "https://cyberpunk.fandom.com/wiki/Category:Cyberpunk_2077_Quests",
        # Fandom List Page
        "https://cyberpunk.fandom.com/wiki/Cyberpunk_2077_Main_Jobs",
        # Another Wiki (Witcher)
        "https://witcher.fandom.com/wiki/The_Witcher_3_main_quests",
    ]

    for url in urls:
        print(f"\nTesting URL: {url}")
        items = parse_wiki_missions(url)
        print(f"Found {len(items)} items.")
        if items:
            print("First 5 items:")
            for item in items[:5]:
                print(f" - {item}")
        else:
            print("FAILED to find any items.")

if __name__ == "__main__":
    test_scraper()
