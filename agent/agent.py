import time
import psutil
import requests
from datetime import datetime
import threading
import os
import subprocess
import ctypes
from ctypes import wintypes

# Server URL
SERVER_URL = "http://localhost:8000"
APP_NAME = "GameTracker"
AGENT_TOKEN_FILENAME = "agent_token.bin"

# How often to check the config and how often to ping the server
CONFIG_POLL_INTERVAL_SECONDS = 300  # 5 minutes
PING_INTERVAL_SECONDS = 30          # 30 seconds
COMMAND_POLL_INTERVAL_SECONDS = 3   # 3 seconds


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _bytes_to_blob(data):
    if not data:
        return DATA_BLOB(0, None)
    buf = (ctypes.c_byte * len(data)).from_buffer_copy(data)
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))


def _blob_to_bytes(blob):
    if not blob.cbData or not blob.pbData:
        return b""
    return ctypes.string_at(blob.pbData, blob.cbData)


def get_storage_dir():
    if os.name == "nt":
        base = os.getenv("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(base, APP_NAME)
    return os.path.join(os.path.expanduser("~"), ".config", "gametracker")


def get_agent_token_path():
    return os.path.join(get_storage_dir(), AGENT_TOKEN_FILENAME)


def encrypt_for_current_user(raw_data):
    if os.name != "nt":
        return raw_data
    in_blob = _bytes_to_blob(raw_data)
    out_blob = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    CRYPTPROTECT_UI_FORBIDDEN = 0x01
    if not crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    ):
        raise OSError("CryptProtectData failed")
    try:
        return _blob_to_bytes(out_blob)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def decrypt_for_current_user(encrypted_data):
    if os.name != "nt":
        return encrypted_data
    in_blob = _bytes_to_blob(encrypted_data)
    out_blob = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    CRYPTPROTECT_UI_FORBIDDEN = 0x01
    if not crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    ):
        raise OSError("CryptUnprotectData failed")
    try:
        return _blob_to_bytes(out_blob)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def save_agent_token(token):
    try:
        os.makedirs(get_storage_dir(), exist_ok=True)
        token_bytes = token.strip().encode("utf-8")
        encrypted = encrypt_for_current_user(token_bytes)
        with open(get_agent_token_path(), "wb") as f:
            f.write(encrypted)
    except Exception as e:
        print(f"[{datetime.now()}] Warning: could not persist agent token: {e}")


def load_agent_token():
    env_token = os.getenv("GAMETRACKER_AGENT_TOKEN", "").strip()
    if env_token:
        return env_token

    token_path = get_agent_token_path()
    if os.path.exists(token_path):
        try:
            with open(token_path, "rb") as f:
                encrypted_data = f.read()
                decrypted_data = decrypt_for_current_user(encrypted_data)
                file_token = decrypted_data.decode("utf-8").strip()
                if file_token:
                    return file_token
        except Exception as e:
            print(f"[{datetime.now()}] Warning: could not read token file: {e}")

    return ""


def ensure_agent_token():
    token = load_agent_token()
    if token:
        return token

    print("Agent token not found.")
    print("Open site settings and copy Agent Token, then paste it here.")
    entered = input("Agent token: ").strip()
    if not entered:
        return ""

    save_agent_token(entered)
    return entered


def get_agent_headers(agent_token):
    return {"X-Agent-Token": agent_token}

def get_agent_config(agent_token):
    """Fetch tracking config from server."""
    try:
        response = requests.get(
            f"{SERVER_URL}/api/agent/config",
            headers=get_agent_headers(agent_token),
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("items", [])
    except Exception as e:
        print(f"[{datetime.now()}] Error fetching config: {e}")
        return None

def ping_server(game_id, exe_name, agent_token):
    """Send a ping to the server for the active game_id."""
    payload = {
        "game_id": game_id,
        "exe_name": exe_name,
        "timestamp": datetime.utcnow().isoformat()
    }
    try:
        response = requests.post(
            f"{SERVER_URL}/api/sessions/ping",
            json=payload,
            headers=get_agent_headers(agent_token),
            timeout=5,
        )
        response.raise_for_status()
        print(f"[{datetime.now()}] Successfully pinged for game_id={game_id}")
        return True
    except Exception as e:
        print(f"[{datetime.now()}] Error sending ping: {e}")
        return False

def get_pending_commands(agent_token):
    try:
        response = requests.get(
            f"{SERVER_URL}/api/agent/commands",
            headers=get_agent_headers(agent_token),
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("items", [])
    except Exception as e:
        print(f"[{datetime.now()}] Error fetching commands: {e}")
        return []


def ack_command(game_id, request_id, success, agent_token, error=None):
    payload = {
        "game_id": game_id,
        "request_id": request_id,
        "success": success,
        "error": error,
    }
    try:
        response = requests.post(
            f"{SERVER_URL}/api/agent/commands/ack",
            json=payload,
            headers=get_agent_headers(agent_token),
            timeout=5,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"[{datetime.now()}] Error ack command: {e}")
        return False


def launch_game(launch_path):
    try:
        if os.name == "nt":
            os.startfile(launch_path)
        else:
            subprocess.Popen([launch_path])
        return True, None
    except Exception as e:
        return False, str(e)


def process_pending_commands(agent_token):
    commands = get_pending_commands(agent_token)
    for command in commands:
        game_id = command.get("game_id")
        request_id = command.get("request_id")
        launch_path = command.get("launch_path")

        if not game_id or not request_id or not launch_path:
            continue

        success, error = launch_game(launch_path)
        if success:
            print(f"[{datetime.now()}] Launch command executed for game_id={game_id}")
        else:
            print(f"[{datetime.now()}] Launch command failed for game_id={game_id}: {error}")
        ack_command(game_id, request_id, success, agent_token, error=error)


def check_processes(active_config, agent_token):
    """Check running processes and ping server for active games."""
    if not active_config:
        return
    
    target_exes = {}
    for item in active_config:
        exe_name = (item.get("exe_name") or "").strip().lower()
        game_id = item.get("game_id")
        if not exe_name or not game_id:
            continue
        if exe_name not in target_exes:
            target_exes[exe_name] = set()
        target_exes[exe_name].add(game_id)

    active_games_found = set()
    
    for proc in psutil.process_iter(['name']):
        try:
            p_name = proc.info.get('name')
            if p_name and p_name.lower() in target_exes:
                for game_id in target_exes[p_name.lower()]:
                    active_games_found.add((game_id, p_name))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    for game_id, exe_name in active_games_found:
        ping_server(game_id, exe_name, agent_token)
    
    return len(active_games_found)

def run_agent(stop_event):
    """Main agent loop."""
    print(f"[{datetime.now()}] Starting GameTracker Agent...")
    
    agent_token = ensure_agent_token()
    if not agent_token:
        print(f"[{datetime.now()}] Agent token is missing. Exiting.")
        return

    active_config = []
    last_config_check = 0
    last_process_check = 0
    last_command_check = 0
    
    while not stop_event.is_set():
        current_time = time.time()
        
        # Update config if needed
        if current_time - last_config_check > CONFIG_POLL_INTERVAL_SECONDS or not active_config:
            new_config = get_agent_config(agent_token)
            if new_config is not None:
                active_config = new_config
                print(f"[{datetime.now()}] Config updated. Tracking {len(active_config)} executables.")
            last_config_check = current_time
        
        # Check processes (for session pings)
        if current_time - last_process_check > PING_INTERVAL_SECONDS and active_config:
            active_count = check_processes(active_config, agent_token)
            if active_count > 0:
                print(f"[{datetime.now()}] Found {active_count} active game(s)")
            last_process_check = current_time

        # Process remote launch commands
        if current_time - last_command_check > COMMAND_POLL_INTERVAL_SECONDS:
            process_pending_commands(agent_token)
            last_command_check = current_time
        
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
