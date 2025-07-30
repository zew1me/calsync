import toml
from dynaconf import Dynaconf
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


def get_g_sync_token(filename="settings.toml"):
    try:
        settings = toml.load(filename)
        return settings.get("g_sync_token")
    except Exception:
        return None

def set_g_sync_token(token, filename="settings.toml"):
    update_settings_file({"g_sync_token": token}, filename=filename)

def get_apple_sync_token(filename="settings.toml"):
    try:
        settings = toml.load(filename)
        return settings.get("apple_sync_token")
    except Exception:
        return None

def set_apple_sync_token(token, filename="settings.toml"):
    update_settings_file({"apple_sync_token": token}, filename=filename)

import toml as _toml
def load_guid_map(filename="event_map.toml"):
    try:
        data = _toml.load(filename)
        return data.get("guid_map", {})
    except Exception:
        return {}

def save_guid_map(guid_map, filename="event_map.toml"):
    data = {"guid_map": guid_map}
    with open(filename, "w") as f:
        _toml.dump(data, f)

def set_last_sync(timestamp=None, filename="settings.toml"):
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    update_settings_file({"last_sync": timestamp}, filename=filename)

def get_last_sync(filename="settings.toml"):
    try:
        settings = toml.load(filename)
        return settings.get("last_sync")
    except Exception:
        return None
