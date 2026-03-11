import time
import psutil
import requests
from datetime import datetime
import threading
import sys
import os

# Server URL
SERVER_URL = "http://localhost:8000"

# How often to check the config and how often to ping the server
CONFIG_POLL_INTERVAL_SECONDS = 300  # 5 minutes
PING_INTERVAL_SECONDS = 30          # 30 seconds

def get_agent_config():
    """Fetch the map of {exe_name: game_id} from the central server."""
    try:
        response = requests.get(f"{SERVER_URL}/api/agent/config", timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[{datetime.now()}] Error fetching config: {e}")
        return None

def ping_server(game_id):
    """Send a ping to the server for the active game_id."""
    payload = {
        "game_id": game_id,
        "timestamp": datetime.utcnow().isoformat()
    }
    try:
        response = requests.post(f"{SERVER_URL}/api/sessions/ping", json=payload, timeout=5)
        response.raise_for_status()
        print(f"[{datetime.now()}] Successfully pinged for game_id={game_id}")
        return True
    except Exception as e:
        print(f"[{datetime.now()}] Error sending ping: {e}")
        return False

def check_processes(active_config):
    """Check running processes and ping server for active games."""
    if not active_config:
        return
    
    target_exes = {exe.lower(): game_id for exe, game_id in active_config.items()}
    active_games_found = set()
    
    for proc in psutil.process_iter(['name']):
        try:
            p_name = proc.info.get('name')
            if p_name and p_name.lower() in target_exes:
                active_games_found.add(target_exes[p_name.lower()])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    for game_id in active_games_found:
        ping_server(game_id)
    
    return len(active_games_found)

def run_agent(stop_event):
    """Main agent loop."""
    print(f"[{datetime.now()}] Starting GameTracker Agent...")
    
    active_config = {}
    last_config_check = 0
    
    while not stop_event.is_set():
        current_time = time.time()
        
        # Update config if needed
        if current_time - last_config_check > CONFIG_POLL_INTERVAL_SECONDS or not active_config:
            new_config = get_agent_config()
            if new_config is not None:
                active_config = new_config
                print(f"[{datetime.now()}] Config updated. Tracking {len(active_config)} executables.")
            last_config_check = current_time
        
        # Check processes
        if active_config:
            active_count = check_processes(active_config)
            if active_count > 0:
                print(f"[{datetime.now()}] Found {active_count} active game(s)")
        
        # Sleep
        for _ in range(PING_INTERVAL_SECONDS):
            if stop_event.is_set():
                break
            time.sleep(1)
    
    print(f"[{datetime.now()}] Agent stopped.")

def create_icon():
    """Create a simple icon for the tray."""
    from PIL import Image, ImageDraw
    
    # Create a 64x64 image
    img = Image.new('RGB', (64, 64), color='#10b981')
    draw = ImageDraw.Draw(img)
    
    # Draw a simple game controller shape
    draw.rectangle([8, 20, 56, 44], fill='#059669')
    draw.rectangle([16, 28, 24, 36], fill='#34d399')
    draw.rectangle([40, 28, 48, 36], fill='#34d399')
    
    return img

def on_clicked(icon, item):
    """Handle icon click."""
    if item == 'exit':
        icon.stop()
    elif item == 'config':
        # Open settings in browser
        import webbrowser
        webbrowser.open('http://localhost:5173/#settings')

def setup_tray():
    """Setup system tray icon."""
    try:
        import pystray
        from pystray import MenuItem as Item
        
        # Create menu
        menu = pystray.Menu(
            Item('Настройки', lambda icon: on_clicked(icon, 'config')),
            Item('Выход', lambda icon: on_clicked(icon, 'exit'))
        )
        
        # Create icon
        icon_image = create_icon()
        icon = pystray.Icon("GameTrackerAgent", icon_image, "GameTracker Agent", menu)
        
        return icon
    except Exception as e:
        print(f"Warning: Could not setup tray icon: {e}")
        print("Running in console mode...")
        return None

def main():
    """Main entry point."""
    stop_event = threading.Event()
    
    # Try to setup tray
    tray_icon = setup_tray()
    
    # Start agent in background thread
    agent_thread = threading.Thread(target=run_agent, args=(stop_event,), daemon=True)
    agent_thread.start()
    
    if tray_icon:
        # Run with tray icon
        tray_icon.run()
    else:
        # Run in console mode
        print("Agent is running. Press Ctrl+C to exit.")
        try:
            while not stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    
    # Stop agent
    stop_event.set()
    agent_thread.join(timeout=5)
    
    print("GameTracker Agent exited.")

if __name__ == "__main__":
    main()
