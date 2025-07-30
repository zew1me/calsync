import toml
from dateutil import parser
from datetime import datetime, timezone

def update_settings_file(new_settings, filename="settings.toml"):
    # Load existing settings
    try:
        settings = toml.load(filename)
    except FileNotFoundError:
        settings = {}
    # Update with new settings
    settings.update(new_settings)
    # Write back to file
    with open(filename, "w") as f:
        toml.dump(settings, f)


def get_g_sync_token(filename="sync_state.toml"):
    try:
        data = toml.load(filename)
        return data.get("g_sync_token")
    except Exception:
        return None

def set_g_sync_token(token, filename="sync_state.toml"):
    try:
        data = toml.load(filename)
    except Exception:
        data = {}
    data["g_sync_token"] = token
    with open(filename, "w") as f:
        toml.dump(data, f)

def get_apple_sync_token(filename="sync_state.toml"):
    try:
        data = toml.load(filename)
        return data.get("apple_sync_token")
    except Exception:
        return None

def set_apple_sync_token(token, filename="sync_state.toml"):
    try:
        data = toml.load(filename)
    except Exception:
        data = {}
    data["apple_sync_token"] = token
    with open(filename, "w") as f:
        toml.dump(data, f)

def load_guid_map(filename="event_map.toml"):
    data = toml.load(filename)
    return data.get("guid_map", {})

def save_guid_map(guid_map, filename="event_map.toml"):
    data = {"guid_map": guid_map}
    with open(filename, "w") as f:
        toml.dump(data, f)