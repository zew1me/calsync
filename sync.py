from settings_utils import set_last_sync, get_last_sync
import logging
from datetime import datetime, timezone, timedelta
from dateutil import parser
import zoneinfo

class CalendarSync:
    def __init__(self, apple_api, google_calendar, config):
        self.apple_api = apple_api
        self.google_calendar = google_calendar
        self.config = config

        # Safely detect a ZoneInfo object for local timezone
        tzinfo = datetime.now(timezone.utc).astimezone().tzinfo
        # Attempt fallback if not ZoneInfo
        if isinstance(tzinfo, zoneinfo.ZoneInfo):
            self.local_tzinfo = tzinfo
        else:
            tz_name = getattr(tzinfo, 'zone', None) or 'UTC'
            self.local_tzinfo = zoneinfo.ZoneInfo(tz_name)
        self.local_tzname = self.local_tzinfo.key

    @staticmethod
    def apple_date_to_dt(dt):
        import tzlocal
        if isinstance(dt, datetime):
            return dt
        if isinstance(dt, (int, float)):
            # Treat as Unix timestamp (seconds since epoch)
            local_tz = tzlocal.get_localzone()
            return datetime.fromtimestamp(dt, tz=local_tz)
        if isinstance(dt, str):
            return parser.isoparse(dt)
        if isinstance(dt, list):
                # Apple date format: [YYYYMMDD, year, month, day, hour, minute, second_or_ms]
                return datetime(dt[1], dt[2], dt[3], dt[4], dt[5], int(dt[6] / 1000))
        raise ValueError(f"Unsupported date format: {dt!r}")

    def sync(self):
        last_sync_dt = get_last_sync()

        all_events = self.apple_api.calendar.get_events(as_objs=False)
        apple_events = []

        for ev in all_events:
            if ev.get('pGuid') != self.config['apple_calendar_id']:
                continue
            try:
                ev_dt = self.apple_date_to_dt(ev['startDate'])
            except ValueError as e:
                logging.warning("Skipping event %r – bad date %r", ev.get('title'), ev['startDate'])
                logging.debug("Error details: %s", e)
                continue

            # Make aware in UTC
            ev_dt = ev_dt.replace(tzinfo=timezone.utc)

            if ev_dt >= last_sync_dt:
                apple_events.append(ev)

        for event in apple_events:
            google_event = self.transform_event(event)
            self.google_calendar.insert_event(self.config['google_calendar_id'], google_event, event.get('guid') or None)

        set_last_sync()
        logging.info("Sync completed.")

    def transform_event(self, apple_event):
        is_all_day = apple_event.get('allDay', False)

        dt_start = self.apple_date_to_dt(apple_event['startDate'])
        dt_end = self.apple_date_to_dt(apple_event['endDate'])

        if is_all_day:
            # For all-day, use date and increment end date by 1
            return {
                "summary": apple_event.get('title', '').strip(),
                "start": {"date": dt_start.date().isoformat()},
                "end": {"date": (dt_end.date() + timedelta(days=1)).isoformat()},
            }
        else:
            dt_start = dt_start.replace(tzinfo=timezone.utc).astimezone(self.local_tzinfo)
            dt_end   = dt_end.replace(tzinfo=timezone.utc).astimezone(self.local_tzinfo)
            return {
                "summary": apple_event.get('title', '').strip(),
                "start": {
                    "dateTime": dt_start.isoformat(),
                    "timeZone": self.local_tzname
                },
                "end": {
                    "dateTime": dt_end.isoformat(),
                    "timeZone": self.local_tzname
                },
                "description": f"This was copied from an Apple calendar event.\nEvent GUID: {apple_event.get('guid', 'N/A')}"
            }
