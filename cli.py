
import typer
from settings_utils import update_settings_file
from dynaconf import Dynaconf
from google_calendar import GoogleCalendar
from apple_calendar import AppleCalendar
from sync import CalendarSync

config = Dynaconf(settings_files=['settings.toml'])

app = typer.Typer()


@app.command()
def configure():
    """Configure Apple (CalDAV) and Google Calendars."""
    apple_email = typer.prompt("Enter your Apple ID email")
    apple_password = typer.prompt("Enter your Apple app-specific password (CalDAV)", hide_input=True)
    apple_caldav_url = typer.prompt("Enter your Apple CalDAV URL", default="https://caldav.icloud.com")
    google_credentials = typer.prompt("Enter path to Google credentials JSON")
    google_calendar = GoogleCalendar(google_credentials)
    google_calendars = google_calendar.list_calendars()
    typer.echo("Select a Google Calendar:")
    for idx, cal in enumerate(google_calendars):
        typer.echo(f"{idx}: {cal['summary']}")
    google_calendar_id = typer.prompt("Enter the number of the Google Calendar")
    update_settings_file({
        "apple_email": apple_email,
        "apple_password": apple_password,
        "apple_caldav_url": apple_caldav_url,
        "google_credentials": google_credentials,
        "google_calendar_id": google_calendars[int(google_calendar_id)]['id']
    })

@app.command()
def sync():
    """Sync Apple Calendar to Google Calendar."""
    google_calendar = GoogleCalendar(config.google_credentials)
    apple_calendar = AppleCalendar(
        config.apple_email,
        config.apple_password,
        config.apple_caldav_url,
        calendar_index=0
    )
    sync = CalendarSync(apple_calendar, google_calendar, config)
    sync.sync()
    
if __name__ == "__main__":
    app()
