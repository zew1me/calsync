from settings_utils import (
    set_last_sync, get_last_sync,
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
        # --- Google: Incremental sync using syncToken ---
        g_sync_token = get_g_sync_token()
        gcal_id = self.config['google_calendar_id']
        service = self.google_calendar.service
        google_events = []
        try:
            if g_sync_token:
                g_events = service.events().list(calendarId=gcal_id, syncToken=g_sync_token).execute()
            else:
                g_events = service.events().list(calendarId=gcal_id, singleEvents=True, maxResults=2500, timeMin='1970-01-01T00:00:00Z').execute()
            google_events = g_events.get('items', [])
            new_g_sync_token = g_events.get('nextSyncToken')
            if new_g_sync_token:
                set_g_sync_token(new_g_sync_token)
        except Exception as e:
            # If token expired (410), do full sync
            if hasattr(e, 'resp') and getattr(e.resp, 'status', None) == 410:
                g_events = service.events().list(calendarId=gcal_id, singleEvents=True, maxResults=2500, timeMin='1970-01-01T00:00:00Z').execute()
                google_events = g_events.get('items', [])
                set_g_sync_token(g_events.get('nextSyncToken'))
            else:
                raise

        # --- Apple: CalDAV incremental sync using sync-token ---
        apple_sync_token = get_apple_sync_token()
        apple_cal = self.apple_calendar
        try:
            if apple_sync_token:
                added, changed, removed, new_token = apple_cal.changes(sync_token=apple_sync_token)
            else:
                added, changed, removed, new_token = apple_cal.changes(sync_token=None)
            set_apple_sync_token(new_token)
        except Exception as e:
            # If token invalid, do full sync
            if 'invalid-sync-token' in str(e):
                added, changed, removed, new_token = apple_cal.changes(sync_token=None)
                set_apple_sync_token(new_token)
            else:
                raise

        # --- Map Apple GUIDs to Google Event IDs ---
        guid_map = self.guid_map
        # Add/update events
        for apple_event in added + changed:
            apple_guid = apple_event.vobject_instance.uid.value
            # Transform Apple event to Google event format (implement as needed)
            google_event = self.transform_event(apple_event)
            # Insert or update in Google Calendar
            if apple_guid in guid_map:
                # Update existing event
                event_id = guid_map[apple_guid]
                self.google_calendar.service.events().update(calendarId=gcal_id, eventId=event_id, body=google_event).execute()
            else:
                created = self.google_calendar.service.events().insert(calendarId=gcal_id, body=google_event).execute()
                guid_map[apple_guid] = created['id']
        # Remove deleted events
        for apple_event in removed:
            apple_guid = apple_event.vobject_instance.uid.value
            if apple_guid in guid_map:
                event_id = guid_map[apple_guid]
                self.google_calendar.service.events().delete(calendarId=gcal_id, eventId=event_id).execute()
                del guid_map[apple_guid]
        save_guid_map(guid_map)

    def transform_event(self, apple_event):
        # Example transformation: must be implemented to map CalDAV event to Google event
        # Handle all-day, timed, and timezone-aware events
        vevent = apple_event.vobject_instance.vevent
        summary = str(vevent.summary.value) if hasattr(vevent, 'summary') else ""
        start = vevent.dtstart.value
        end = vevent.dtend.value if hasattr(vevent, 'dtend') else None
        if isinstance(start, datetime):
            if start.tzinfo is None:
                start = start.replace(tzinfo=ZoneInfo("UTC"))
            start = start.astimezone(ZoneInfo("UTC"))
        if end and isinstance(end, datetime):
            if end.tzinfo is None:
                end = end.replace(tzinfo=ZoneInfo("UTC"))
            end = end.astimezone(ZoneInfo("UTC"))
        # All-day event
        if hasattr(vevent.dtstart, 'params') and vevent.dtstart.params.get('VALUE') == ['DATE']:
            # Google expects end date to be exclusive for all-day events
            dt_start = start if isinstance(start, datetime) else datetime.strptime(str(start), "%Y-%m-%d")
            if end:
                dt_end = end if isinstance(end, datetime) else datetime.strptime(str(end), "%Y-%m-%d")
            else:
                dt_end = dt_start
            return {
                "summary": summary,
                "start": {"date": dt_start.date().isoformat()},
                "end": {"date": (dt_end.date() + timedelta(days=1)).isoformat()},
            }
        # Timed event
        return {
            "summary": summary,
            "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end.isoformat(), "timeZone": "UTC"} if end else None,
        }
