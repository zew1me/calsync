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

# Fix: import Calendar from icalendar for transform_event

class CalendarSync:
    def __init__(self, apple_calendar, google_calendar, config):
        self.apple_calendar = apple_calendar
        self.google_calendar = google_calendar
        self.config = config
        self.local_tzinfo = ZoneInfo("UTC")
        self.guid_map = load_guid_map()
        logging.debug(f"Initialized CalendarSync")

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
        # --- Google: Initial and incremental sync using syncToken ---
        g_sync_token = get_g_sync_token("sync_state.toml")
        gcal_id = self.config['google_calendar_id']
        service = self.google_calendar.service
        google_events = []
        new_g_sync_token = None
        try:
            if not g_sync_token:
                logging.debug("No Google sync token found, performing initial full sync.")
                request_kwargs = dict(calendarId=gcal_id, singleEvents=True, maxResults=2500, showDeleted=True)
                g_events = service.events().list(**request_kwargs).execute()
                google_events.extend(g_events.get('items', []))
                logging.debug(f"Fetched {len(g_events.get('items', []))} Google events (initial full sync).")
                new_g_sync_token = g_events.get('nextSyncToken')
                if not new_g_sync_token:
                    logging.warning("No nextSyncToken returned after initial full sync.")
            else:
                logging.debug(f"Using Google sync token: {g_sync_token}")
                next_sync_token = g_sync_token
                while next_sync_token:
                    try:
                        g_events = service.events().list(calendarId=gcal_id, syncToken=next_sync_token, showDeleted=True).execute()
                        google_events.extend(g_events.get('items', []))
                        logging.debug(f"Fetched {len(g_events.get('items', []))} Google events (incremental).")
                        new_g_sync_token = g_events.get('nextSyncToken')
                        next_page_token = g_events.get('nextPageToken')
                        if next_page_token:
                            # There are more pages, continue with nextPageToken
                            logging.debug(f"Fetching next page of Google events with nextPageToken: {next_page_token}")
                            # Note: nextPageToken is used with the same syncToken
                            g_events = service.events().list(calendarId=gcal_id, syncToken=next_sync_token, showDeleted=True, pageToken=next_page_token).execute()
                            google_events.extend(g_events.get('items', []))
                            logging.debug(f"Fetched {len(g_events.get('items', []))} Google events (next page).")
                            new_g_sync_token = g_events.get('nextSyncToken')
                        if new_g_sync_token:
                            next_sync_token = None  # End loop
                        else:
                            next_sync_token = None  # End loop if no new sync token
                    except Exception as e:
                        # If token expired (410), do full sync
                        logging.error(f"Error during Google incremental sync: {e}")
                        if hasattr(e, 'resp') and getattr(e.resp, 'status', None) == 410:
                            logging.warning("Google sync token expired, performing initial sync with timeMin.")
                            now = datetime.now(timezone.utc).isoformat()
                            g_events = service.events().list(calendarId=gcal_id, singleEvents=True, maxResults=2500, timeMin=now, showDeleted=True).execute()
                            google_events.extend(g_events.get('items', []))
                            new_g_sync_token = g_events.get('nextSyncToken')
                            if not new_g_sync_token:
                                logging.warning("No nextSyncToken returned after token reset.")
                            next_sync_token = None
                        else:
                            raise
        except Exception as e:
            logging.error(f"Error during Google sync: {e}")
            raise

        logging.debug(f"Total Google events fetched: {len(google_events)}")

        # --- Apple: CalDAV incremental sync using sync-token, with batching ---
        apple_token = get_apple_sync_token()
        logging.debug(f"Starting Apple sync with token: {apple_token}")
        apple_cal = self.apple_calendar
        while True:
            try:
                added, changed, removed, new_apple_token = apple_cal.changes(sync_token=apple_token)
                logging.debug(f"Apple batch: added={len(added)}, changed={len(changed)}, removed={len(removed)}")
            except Exception as e:
                logging.error("Apple sync error", exc_info=e)
                if 'invalid-sync-token' in str(e):
                    logging.warning("Apple sync token invalid, performing full sync.")
                    apple_token = None
                    continue
                raise

            guid_map = self.guid_map
            self._process_apple_batch(added, changed, removed, guid_map)
            save_guid_map(guid_map)

            # If no new token or no changes, we're done
            if not new_apple_token or (not added and not changed and not removed):
                break
            apple_token = new_apple_token

        # Persist final sync token
        if apple_token:
            set_apple_sync_token(apple_token, "sync_state.toml")
            logging.debug(f"Saved Apple sync token: {apple_token}")

        # Only set Google sync token after successful Apple mapping
        if new_g_sync_token:
            set_g_sync_token(new_g_sync_token, "sync_state.toml")
            logging.debug(f"Updated Google sync token: {new_g_sync_token}")
        logging.debug("Sync process complete.")

    def _process_apple_batch(self, added, changed, removed, guid_map):
        google_calendar = self.google_calendar
        for apple_event in added + changed:
            v = apple_event.vobject_instance
            comp = getattr(v, 'vevent', None)
            if comp and hasattr(comp, 'uid'):
                guid = comp.uid.value
            else:
                logging.info("Skipping non-VEVENT")
                continue
            logging.debug(f"Processing Apple GUID: {guid}")
            g_event_body = self.transform_event(apple_event)
            if guid in guid_map:
                logging.debug(f"Updating Google event {guid_map[guid]} for GUID {guid}")
                if hasattr(google_calendar, 'update_event'):
                    google_calendar.update_event(guid_map[guid], g_event_body)
                else:
                    google_calendar.service.events().update(calendarId=google_calendar.calendar_id, eventId=guid_map[guid], body=g_event_body).execute()
            else:
                created = google_calendar.insert_event(google_calendar.calendar_id, g_event_body, guid)
                guid_map[guid] = created['id']
                logging.debug(f"Inserted Google event {created['id']} for new GUID {guid}")

        for apple_event in removed:
            v = apple_event.vobject_instance
            comp = getattr(v, 'vevent', None)
            guid = getattr(comp, 'uid', None)
            if guid:
                guid = guid.value
                if guid in guid_map:
                    logging.debug(f"Deleting Google event {guid_map[guid]} for removed GUID {guid}")
                    if hasattr(google_calendar, 'delete_event'):
                        google_calendar.delete_event(guid_map[guid])
                    else:
                        google_calendar.service.events().delete(calendarId=google_calendar.calendar_id, eventId=guid_map[guid]).execute()
                    del guid_map[guid]


def transform_event(self, apple_event):
    """
    Convert a python-caldav CalendarObjectResource into a Google Calendar event dict using only vobject.
    Supports all-day, timed, timezones, description, location, recurrence.
    """
    vobj = apple_event.vobject_instance
    vevent = getattr(vobj, 'vevent', None)
    if vevent is None:
        raise ValueError("No VEVENT found in vobject instance")

    def get_text(field):
        return str(getattr(vevent, field).value) if hasattr(vevent, field) else ""

    summary = get_text('summary')
    description = get_text('description')
    location = get_text('location')
    uid = get_text('uid')
    seq = int(getattr(vevent, 'sequence').value) if hasattr(vevent, 'sequence') else 0

    dtstart = getattr(vevent, 'dtstart').value if hasattr(vevent, 'dtstart') else None
    dtend = getattr(vevent, 'dtend').value if hasattr(vevent, 'dtend') else None

    # Determine if all-day event
    is_all_day = False
    if hasattr(vevent, 'dtstart') and hasattr(vevent.dtstart, 'params'):
        is_all_day = vevent.dtstart.params.get('VALUE') == 'DATE'

    def to_utc(dt):
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo("UTC"))
            return dt.astimezone(ZoneInfo("UTC"))
        return dt

    if is_all_day:
        start_date = dtstart if not isinstance(dtstart, datetime) else dtstart.date()
        if dtend:
            end_date = dtend if not isinstance(dtend, datetime) else dtend.date()
        else:
            end_date = start_date
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
    if hasattr(vevent, 'rrule'):
        rrule_val = vevent.rrule.value if hasattr(vevent.rrule, 'value') else vevent.rrule
        if isinstance(rrule_val, list):
            event["recurrence"] = ["RRULE:" + r for r in rrule_val]
        else:
            event["recurrence"] = ["RRULE:" + str(rrule_val)]

    return event