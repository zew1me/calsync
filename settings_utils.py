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

def get_last_sync(filename="settings.toml"):
    settings = Dynaconf(settings_files=[filename])
    if 'last_sync' in settings:
        return parser.isoparse(settings['last_sync'])
    return None

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
