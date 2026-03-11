import requests

def run_test():
    try:
        game_res = requests.post("http://127.0.0.1:8000/api/games", json={"title": "Verification Game", "status": "playing", "source": "manual", "tracking_mode": "manual"})
        game_id = game_res.json().get("id")

        if game_id:
            print(f"Created game ID: {game_id}")
            wiki = requests.post(f"http://127.0.0.1:8000/api/games/{game_id}/import/wiki", json={"url": "https://en.wikipedia.org/wiki/Super_Mario_Bros."})
            print(f"Imported {len(wiki.json())} wiki checklist items.")
            
            steam = requests.post(f"http://127.0.0.1:8000/api/games/{game_id}/sync/steam")
            print(f"Synced {len(steam.json())} achievements.")
        else:
            print("Failed to create game.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_test()
