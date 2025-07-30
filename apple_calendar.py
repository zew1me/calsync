# /// apple_calendar
# requires-python = ">=3.12"
# dependencies = ["python-caldav"]
# ///

from caldav import DAVClient

class AppleCalendar:
    def __init__(self, email, password, url, calendar_index=0):
        self.email = email
        self.password = password
        self.url = url
        self.client = DAVClient(url, username=email, password=password)
        self.principal = self.client.principal()
        self.calendars = self.principal.calendars()
        self.calendar = self.calendars[calendar_index]

    def get_events(self):
        return self.calendar.events()

    def changes(self, sync_token=None):
        coll = self.calendar.objects_by_sync_token(sync_token=sync_token, load_objects=True)
        new_token = getattr(coll, 'sync_token', None)
        added, changed, removed = [], [], []
        for obj in coll:
            status = getattr(obj, '_status', None)
            if status == 'deleted':
                removed.append(obj)
            elif status == 'changed':
                changed.append(obj)
            else:
                added.append(obj)
        return added, changed, removed, new_token

    def get_calendar_names(self):
        return [cal.name for cal in self.calendars]
