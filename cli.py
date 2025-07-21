import typer
from settings_utils import update_settings_file, set_last_sync
from dynaconf import Dynaconf
from pyicloud import PyiCloudService
from google_calendar import GoogleCalendar
from sync import CalendarSync

config = Dynaconf(settings_files=['settings.toml'])

app = typer.Typer()

def apple_sign_in(apple_email, apple_password):
    """Sign in to Apple and handle 2FA/FIDO2 if required. Returns authenticated PyiCloudService instance."""
    apple_api = PyiCloudService(apple_email, apple_password)
    if apple_api.requires_2fa:
        typer.echo("Two-factor authentication is required.")
        # Security‑key flow
        if getattr(apple_api, "security_key_names", None):
            keys = apple_api.security_key_names
            typer.echo(f"Security key authentication configured: {', '.join(keys)}")
            devices = apple_api.fido2_devices
            for i, dev in enumerate(devices, start=1):
                typer.echo(f"{i}: {dev}")
            choice = typer.prompt("Select a security key by number", type=int)
            selected = devices[choice - 1]
            typer.echo("Please insert/activate your security key and touch it when prompted...")
            apple_api.confirm_security_key(selected)
            typer.echo("✅ Security key confirmed.")
        else:
            # Fallback to code-based 2FA
            code = typer.prompt("Enter the 6‑digit 2FA code from your trusted device")
            if not apple_api.validate_2fa_code(code):
                raise typer.Exit("❌ Failed to verify 2FA code. Exiting.")
            typer.echo("✅ 2FA code validation succeeded.")
        # Trust the session
        if not apple_api.is_trusted_session:
            typer.echo("🔁 Marking this session as trusted...")
            if apple_api.trust_session():
                typer.echo("✅ Session is now trusted.")
            else:
                typer.echo("⚠️ Could not mark the session as trusted—future logins may require 2FA.")
    return apple_api


@app.command()
def configure():
    """Configure Apple and Google Calendars."""
    apple_email = typer.prompt("Enter your Apple ID email")
    apple_password = typer.prompt("Enter your Apple app-specific password", hide_input=True)
    google_credentials = typer.prompt("Enter path to Google credentials JSON")

    apple_api = apple_sign_in(apple_email, apple_password)
    google_calendar = GoogleCalendar(google_credentials)

    apple_calendars = apple_api.calendar.get_calendars()
    google_calendars = google_calendar.list_calendars()

    typer.echo("Select an Apple Calendar:")
    for idx, cal in enumerate(apple_calendars):
        typer.echo(f"{idx}: {cal['title']}")
    apple_calendar_id = typer.prompt("Enter the number of the Apple Calendar")

    typer.echo("Select a Google Calendar:")
    for idx, cal in enumerate(google_calendars):
        typer.echo(f"{idx}: {cal['summary']}")
    google_calendar_id = typer.prompt("Enter the number of the Google Calendar")

    update_settings_file({
        "apple_email": apple_email,
        "apple_password": apple_password,
        "google_credentials": google_credentials,
        "apple_calendar_id": apple_calendars[int(apple_calendar_id)]['guid'],
        "google_calendar_id": google_calendars[int(google_calendar_id)]['id']
    })

@app.command()
def sync():
    typer.echo(config.to_dict())
    """Sync Apple Calendar to Google Calendar."""
    apple_api = apple_sign_in(config.apple_email, config.apple_password)
    google_calendar = GoogleCalendar(config.google_credentials)
    sync = CalendarSync(apple_api, google_calendar, config)
    sync.sync()
    # After successful sync, update last_sync timestamp
    set_last_sync()

if __name__ == "__main__":
    app()
