
import typer
from settings_utils import update_settings_file
from dynaconf import Dynaconf, Validator
import logging.config
from google_calendar import GoogleCalendar
from apple_calendar import AppleCalendar
from sync import CalendarSync
import toml

config = Dynaconf(
    settings_files=['settings.toml'],
    validators=[Validator("apple_caldav_url", default="https://caldav.icloud.com")]
)
config.validators.validate()
if hasattr(config, "logging") and config.logging:
    logging.config.dictConfig(config.logging)

app = typer.Typer()


@app.command()
def configure():
    """Configure Apple (CalDAV) and Google Calendars."""
    existing = {
        "apple_email": getattr(config, "apple_email", None),
        "apple_password": getattr(config, "apple_password", None),
        "apple_caldav_url": getattr(config, "apple_caldav_url", None),
        "apple_calendar_index": getattr(config, "apple_calendar_index", None),
        "google_credentials": getattr(config, "google_credentials", None),
        "google_calendar_id": getattr(config, "google_calendar_id", None),
    } 
    # Apple
    apple_email = typer.prompt(f"Enter your Apple ID email [{existing['apple_email']}]", default=existing['apple_email'])
    # Only indicate if password is set, don't show it
    pw_set = bool(existing['apple_password'])
    pw_prompt = "Apple app-specific password (CalDAV) [set]" if pw_set else "Apple app-specific password (CalDAV) [not set]"
    apple_password = typer.prompt(f"Enter your {pw_prompt}", hide_input=True, default=None if not pw_set else "")
    if apple_password == "":
        apple_password = existing['apple_password']
    apple_caldav_url = typer.prompt(f"Enter your Apple CalDAV URL [{existing['apple_caldav_url']}]", default=existing['apple_caldav_url'])
    # Apple calendar selection
    apple_cal = AppleCalendar(apple_email, apple_password, apple_caldav_url)
    apple_calendars = apple_cal.get_calendar_names()
    typer.echo("Select an Apple Calendar:")
    for idx, cal in enumerate(apple_calendars):
        typer.echo(f"{idx}: {cal}")
    default_apple_idx = existing.get('apple_calendar_index')
    if default_apple_idx is None:
        # Force prompt if not set
        apple_calendar_index = typer.prompt("Enter the number of the Apple Calendar (required)")
    else:
        apple_calendar_index = typer.prompt(f"Enter the number of the Apple Calendar [{default_apple_idx}]", default=str(default_apple_idx))

    # Google
    google_credentials = typer.prompt(f"Enter path to Google credentials JSON [{existing.get('google_credentials','')}]", default=existing.get('google_credentials',''))
    google_calendars = GoogleCalendar.list_calendars(google_credentials)
    
    typer.echo("Select a Google Calendar:")
    for idx, cal in enumerate(google_calendars):
        typer.echo(f"{idx}: {cal['summary']}")
    # Try to match existing google_calendar_id to index
    default_google_idx = None
    for idx, cal in enumerate(google_calendars):
        if cal['id'] == existing.get('google_calendar_id'):
            default_google_idx = str(idx)
            break
    if existing.get('google_calendar_id') is None or default_google_idx is None:
        # Force prompt if not set
        google_calendar_id = typer.prompt("Enter the number of the Google Calendar (required)")
    else:
        google_calendar_id = typer.prompt(f"Enter the number of the Google Calendar [{default_google_idx}]", default=default_google_idx)

    update_settings_file({
        "apple_email": apple_email,
        "apple_password": apple_password,
        "apple_caldav_url": apple_caldav_url,
        "apple_calendar_index": int(apple_calendar_index),
        "google_credentials": google_credentials,
        "google_calendar_id": google_calendars[int(google_calendar_id)]['id']
    })

@app.command()
def sync():
    """Sync Apple Calendar to Google Calendar."""
    typer.echo("Starting calendar sync...")

    google_calendar = GoogleCalendar(config.google_credentials, config.google_calendar_id)
    apple_calendar = AppleCalendar(
        config.apple_email,
        config.apple_password,
        config.apple_caldav_url,
        calendar_index=config.apple_calendar_index
    )
    sync = CalendarSync(apple_calendar, google_calendar, config)
    sync.sync()
    
if __name__ == "__main__":
    app()
