from settings_utils import (
    get_g_sync_token, set_g_sync_token,
    get_apple_sync_token, set_apple_sync_token,
    load_guid_map, save_guid_map
)
from apple_calendar import AppleCalendar
import logging
from datetime import datetime, timezone, timedelta
from dateutil import parser
from zoneinfo import ZoneInfo


class CalendarSync:
    def __init__(self, apple_calendar, google_calendar, config):
        self.apple_calendar = apple_calendar
        self.google_calendar = google_calendar
        self.config = config
        self.local_tzinfo = ZoneInfo("UTC")
        self.guid_map = load_guid_map()
        logging.debug(f"Initialized CalendarSync with config: {config}")

    @staticmethod
    def make_aware_utc(dt, source_tz=None):
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                if source_tz:
                    dt = dt.replace(tzinfo=ZoneInfo(source_tz))
                else:
                    dt = dt.replace(tzinfo=ZoneInfo("UTC"))
            return dt.astimezone(ZoneInfo("UTC"))
        if isinstance(dt, str):
            return parser.isoparse(dt).astimezone(ZoneInfo("UTC"))
        raise ValueError(f"Unsupported date format: {dt!r}")

    def sync(self):
        logging.debug("Starting sync process.")
        # --- Google: Incremental sync using syncToken ---
        g_sync_token = get_g_sync_token("sync_state.toml")
        gcal_id = self.config['google_calendar_id']
        service = self.google_calendar.service
        google_events = []
        try:
            if g_sync_token:
                logging.debug(f"Using Google sync token: {g_sync_token}")
                g_events = service.events().list(calendarId=gcal_id, syncToken=g_sync_token).execute()
            else:
                logging.debug("No Google sync token found, performing full sync.")
                g_events = service.events().list(calendarId=gcal_id, singleEvents=True, maxResults=2500, timeMin='1970-01-01T00:00:00Z').execute()
            google_events = g_events.get('items', [])
            logging.debug(f"Fetched {len(google_events)} Google events.")
            new_g_sync_token = g_events.get('nextSyncToken')
            if new_g_sync_token:
                set_g_sync_token(new_g_sync_token, "sync_state.toml")
                logging.debug(f"Updated Google sync token: {new_g_sync_token}")
        except Exception as e:
            # If token expired (410), do full sync
            logging.error(f"Error during Google sync: {e}")
            if hasattr(e, 'resp') and getattr(e.resp, 'status', None) == 410:
                logging.warning("Google sync token expired, performing full sync.")
                g_events = service.events().list(calendarId=gcal_id, singleEvents=True, maxResults=2500, timeMin='1970-01-01T00:00:00Z').execute()
                google_events = g_events.get('items', [])
                set_g_sync_token(g_events.get('nextSyncToken'), "sync_state.toml")
                logging.debug(f"Reset Google sync token: {g_events.get('nextSyncToken')}")
            else:
                raise

        # --- Apple: CalDAV incremental sync using sync-token ---
        apple_sync_token = get_apple_sync_token()
        logging.debug(f"Using Apple sync token: {apple_sync_token}")
        apple_cal = self.apple_calendar
        try:
            if apple_sync_token:
                added, changed, removed, new_token = apple_cal.changes(sync_token=apple_sync_token)
            else:
                added, changed, removed, new_token = apple_cal.changes(sync_token=None)
            set_apple_sync_token(new_token, "sync_state.toml")
            logging.debug(f"Apple changes: added={len(added)}, changed={len(changed)}, removed={len(removed)}, new_token={new_token}")
        except Exception as e:
            # If token invalid, do full sync
            logging.error(f"Error during Apple sync: {e}")
            if 'invalid-sync-token' in str(e):
                logging.warning("Apple sync token invalid, performing full sync.")
                added, changed, removed, new_token = apple_cal.changes(sync_token=None)
                set_apple_sync_token(new_token, "sync_state.toml")
                logging.debug(f"Apple changes after full sync: added={len(added)}, changed={len(changed)}, removed={len(removed)}, new_token={new_token}")
            else:
                raise

        # --- Map Apple GUIDs to Google Event IDs ---
        guid_map = self.guid_map
        # Add/update events
        for apple_event in added + changed:
            apple_guid = apple_event.vobject_instance.uid.value
            logging.debug(f"Processing Apple event GUID: {apple_guid}")
            # Transform Apple event to Google event format (implement as needed)
            google_event = self.transform_event(apple_event)
            # Insert or update in Google Calendar
            if apple_guid in guid_map:
                # Update existing event
                event_id = guid_map[apple_guid]
                logging.debug(f"Updating Google event {event_id} for Apple GUID {apple_guid}")
                self.google_calendar.service.events().update(calendarId=gcal_id, eventId=event_id, body=google_event).execute()
            else:
                created = self.google_calendar.service.events().insert(calendarId=gcal_id, body=google_event).execute()
                guid_map[apple_guid] = created['id']
                logging.debug(f"Inserted new Google event {created['id']} for Apple GUID {apple_guid}")
        # Remove deleted events
        for apple_event in removed:
            apple_guid = apple_event.vobject_instance.uid.value
            if apple_guid in guid_map:
                event_id = guid_map[apple_guid]
                logging.debug(f"Deleting Google event {event_id} for removed Apple GUID {apple_guid}")
                self.google_calendar.service.events().delete(calendarId=gcal_id, eventId=event_id).execute()
                del guid_map[apple_guid]
        save_guid_map(guid_map)
        logging.debug("Sync process complete.")


def transform_event(self, apple_event):
    """
    Convert a python-caldav CalendarObjectResource into a Google Calendar event dict.
    Supports all-day, timed, timezones, description, location, recurrence.
    """
    # parse raw iCalendar text
    raw = apple_event.data
    cal = Calendar.from_ical(raw)
    ve = next(comp for comp in cal.walk() if comp.name == "VEVENT")

    summary = str(ve.get("SUMMARY", ""))
    description = str(ve.get("DESCRIPTION", ""))
    location = str(ve.get("LOCATION", ""))

    uid = str(ve.get("UID"))
    seq = int(ve.get("SEQUENCE", 0))

    dtstart = ve.get("DTSTART").dt
    dtend = ve.get("DTEND").dt if ve.get("DTEND") else None

    is_all_day = hasattr(ve["DTSTART"], 'params') and ve["DTSTART"].params.get('VALUE') == 'DATE'

    def to_utc(dt):
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo("UTC"))
            return dt.astimezone(ZoneInfo("UTC"))
        return dt

    if is_all_day:
        # convert to date
        start_date = dtstart if not isinstance(dtstart, datetime) else dtstart.date()
        if dtend:
            end_date = dtend if not isinstance(dtend, datetime) else dtend.date()
        else:
            end_date = start_date
        # end exclusive
        google_start = {"date": start_date.isoformat()}
        google_end = {"date": (end_date + timedelta(days=1)).isoformat()}
    else:
        start_utc = to_utc(dtstart)
        end_utc = to_utc(dtend) if dtend else (start_utc + timedelta(hours=1))
        google_start = {"dateTime": start_utc.isoformat(), "timeZone": "UTC"}
        google_end = {"dateTime": end_utc.isoformat(), "timeZone": "UTC"}

    event = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": google_start,
        "end": google_end,
        "iCalUID": uid,
        "sequence": seq,
    }

    # Optional: handle recurrence
    if ve.get("RRULE"):
        event["recurrence"] = [ve.get("RRULE").to_ical().decode()]

    # Optional: attendees
    if ve.get("ATTENDEE"):
        atts = ve.get("ATTENDEE")
        attendees = []
        for att in ([atts] if not isinstance(atts, list) else atts):
            email = att.to_ical().decode().split(':')[-1]
            attendees.append({"email": email})
        event["attendees"] = attendees

    return event