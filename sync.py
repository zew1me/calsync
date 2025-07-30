from settings_utils import (
    get_g_sync_token, set_g_sync_token,
    get_apple_sync_token, set_apple_sync_token,
    load_guid_map, save_guid_map
)
from apple_calendar import AppleCalendar
import logging
from datetime import datetime, timedelta
from dateutil import parser
from zoneinfo import ZoneInfo
from google_calendar import GoogleCalendar
from apple_calendar import AppleCalendar

class CalendarSync:
    def __init__(self, apple_calendar: AppleCalendar, google_calendar: GoogleCalendar, config):
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
    
    @staticmethod
    def to_rfc(dt) -> str | None: 
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo("UTC"))
            dt = dt.astimezone(ZoneInfo("UTC"))
            return dt.isoformat()
        return None    
    
    @staticmethod
    def transform_event(apple_event) -> dict:
        vobj = apple_event.vobject_instance
        vevent = getattr(vobj, 'vevent', None)
        if vevent is None:
            raise ValueError("No VEVENT found in vobject instance")

        def get_text(field):
            return str(getattr(vevent, field).value) if hasattr(vevent, field) else ""

        summary    = get_text('summary')
        description = get_text('description')
        location   = get_text('location')
        uid        = get_text('uid')
        seq        = int(getattr(vevent, 'sequence').value) if hasattr(vevent, 'sequence') else 0

        dtstart = getattr(vevent, 'dtstart').value if hasattr(vevent, 'dtstart') else None
        dtend   = getattr(vevent, 'dtend').value if hasattr(vevent, 'dtend') else None

        is_all_day = False
        if hasattr(vevent, 'dtstart') and getattr(vevent.dtstart, 'params', None):
            is_all_day = vevent.dtstart.params.get('VALUE') == 'DATE'

        def to_rfc3339(dt):
            if isinstance(dt, datetime):
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                return dt.astimezone(ZoneInfo("UTC")).isoformat()
            return None

        if is_all_day:
            start_date = dtstart.date() if isinstance(dtstart, datetime) else dtstart
            if start_date is not None:
                google_start = {"date": start_date.isoformat()}
            else:
                raise ValueError("start_date is None and cannot be converted to ISO format")

            if dtend:
                end_date = dtend.date() if isinstance(dtend, datetime) else dtend
            else:
                end_date = start_date
            if end_date is not None:
                google_end = {"date": (end_date + timedelta(days=1)).isoformat()}
            else:
                raise ValueError("end_date is None and cannot be incremented by timedelta")
        else:
            start_iso = to_rfc3339(dtstart)
            if start_iso is None:
                raise ValueError("start time is missing or invalid for timed event")
            if dtend:
                end_iso = to_rfc3339(dtend)
            else:
                end_iso = (datetime.fromisoformat(start_iso) + timedelta(hours=1)).isoformat()
            google_start = {"dateTime": start_iso, "timeZone": "UTC"}
            google_end   = {"dateTime": end_iso,   "timeZone": "UTC"}

        event = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": google_start,
            "end": google_end,
            "iCalUID": uid,
            "sequence": seq,
        }

        if hasattr(vevent, 'rrule'):
            r = vevent.rrule.value if hasattr(vevent.rrule, 'value') else vevent.rrule
            event["recurrence"] = ["RRULE:" + str(r)] if isinstance(r, (str,)) else ["RRULE:" + rr for rr in r]

        return event

    def google_sync(self):
        """Handles only Google sync and returns (google_events, new_g_sync_token)."""
        g_sync_token = get_g_sync_token("sync_state.toml")
        google_events = []
        new_g_sync_token = None
        try:
            if not g_sync_token:
                logging.debug("No Google sync token found, performing initial full sync.")
                next_page_token = None
                while True:
                    g_events = self.google_calendar.list_events(page_token=next_page_token)
                    google_events.extend(g_events.get('items', []))
                    next_page_token = g_events.get('nextPageToken')
                    if not next_page_token:
                        new_g_sync_token = g_events.get('nextSyncToken')
                        if not new_g_sync_token:
                            logging.error("No nextSyncToken returned after initial full sync.")
                        break
            else:
                logging.debug(f"Using Google sync token: {g_sync_token}")
                g_events = self.google_calendar.list_events(sync_token=g_sync_token)
                next_page_token = None
                first = True
                while True:
                    try:
                        if first:
                            first = False
                        else:
                            g_events = self.google_calendar.list_events(page_token=next_page_token)
                        google_events.extend(g_events.get('items', []))
                        logging.debug(f"Fetched {len(g_events.get('items', []))} Google events (incremental page).")
                        next_page_token = g_events.get('nextPageToken')
                        if not next_page_token:
                            new_g_sync_token = g_events.get('nextSyncToken')
                            if not new_g_sync_token:
                                logging.error("No nextSyncToken returned after incremental sync.")
                            break
                    except Exception as e:
                        logging.error(f"Error during Google incremental sync: {e}")
                        if hasattr(e, 'resp') and getattr(e.resp, 'status', None) == 410:
                            logging.warning("Google sync token expired, re-starting initial sync")
                            set_g_sync_token(None)
                            # Only re-run Google sync, not the whole sync
                            return self.google_sync()
                        else:
                            raise
        except Exception as e:
            logging.error(f"Error during Google sync: {e}")
            raise
        return google_events, new_g_sync_token

    def sync(self):
        logging.debug("Starting sync process.")
        # --- Google: Initial and incremental sync using syncToken ---
        google_events, new_g_sync_token = self.google_sync()
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

        # Persist sync token
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
                google_calendar.update_event(guid_map[guid], g_event_body)
            else:
                created = google_calendar.insert_event(g_event_body, guid)
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
                    google_calendar.delete_event(guid_map[guid])
