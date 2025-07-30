# /// google_calendar
# requires-python = ">=3.12"
# dependencies = ["google-api-python-client", "google-auth-oauthlib"]
# ///
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import os
import logging

class GoogleCalendar:
    @staticmethod
    def _load_credentials(credentials_path, token_path="token.json"):
        """
        Load and return Google API credentials, handling refresh and OAuth flow as needed.
        """
        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        creds = None
        if os.path.exists(token_path):
            logging.debug(f"Loading Google credentials from {token_path}")
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logging.debug("Refreshing expired Google credentials.")
                creds.refresh(Request())
            else:
                logging.debug(f"Running OAuth flow for Google credentials from {credentials_path}")
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
            logging.debug(f"Saved new Google credentials to {token_path}")
        return creds
    
    def __init__(self, credentials_path, calendar_id, token_path="token.json"):
        self.creds = self._load_credentials(credentials_path, token_path)
        self.service = build('calendar', 'v3', credentials=self.creds)
        self.calendar_id = calendar_id

    @staticmethod
    def list_calendars(credentials_path, token_path="token.json"):
        """
        List all Google calendars for the authenticated user.
        """
        creds = GoogleCalendar._load_credentials(credentials_path, token_path)
        service = build('calendar', 'v3', credentials=creds)
        logging.debug("Listing Google calendars.")
        calendars = service.calendarList().list().execute()
        logging.info(f"Fetched {len(calendars['items'])} Google Calendars.")
        return calendars['items']

    def insert_event(self, event, apple_guid):
        logging.debug(f"Inserting event into Google calendar {self.calendar_id} with Apple GUID {apple_guid}")
        # Insert the event
        created_event = self.service.events().insert(calendarId=self.calendar_id, body=event).execute()
        logging.info(f"Event created: {created_event['id']}")

        # If a GUID is provided, find and delete duplicate events with the same GUID
        if apple_guid:
            logging.debug(f"Checking for duplicate Google events with Apple GUID {apple_guid}")
            events = self.service.events().list(calendarId=self.calendar_id, q=apple_guid).execute()
            for existing_event in events.get('items', []):
                # Skip the event that was just created
                if existing_event['id'] != created_event['id']:
                    self.service.events().delete(calendarId=self.calendar_id, eventId=existing_event['id']).execute()
                    logging.info(f"Deleted duplicate event: {existing_event['id']}")

        return created_event
    
    def update_event(self, event_id, event_body):
        """
        Update an existing Google Calendar event by event ID.
        """
        logging.debug(f"Updating Google event {event_id}")
        updated_event = self.service.events().update(calendarId=self.calendar_id, eventId=event_id, body=event_body).execute()
        logging.info(f"Event updated: {updated_event['id']}")
        return updated_event    

    def delete_event(self, event_id):
        logging.debug(f"Deleting Google event {event_id}")
        self.service.events().delete(calendarId=self.calendar_id, eventId=event_id).execute()
        logging.info(f"Event deleted: {event_id}")


    def list_events(self, single_events=True, max_results=2500, show_deleted=True, page_token=None, sync_token=None):
        """
        List events in the Google Calendar within the specified time range.
        """
        logging.debug(f"Listing Google events with single_events={single_events}, max_results={max_results}, show_deleted={show_deleted}, page_token={page_token}")
        list_kwargs = {
            'calendarId': self.calendar_id,
            'singleEvents': single_events,
            'maxResults': max_results,
            'showDeleted': show_deleted
        }
        if page_token:
            list_kwargs['pageToken'] = page_token
        
        if sync_token:
            list_kwargs['syncToken'] = sync_token
            logging.debug(f"Using sync token: {sync_token}")

        events = self.service.events().list(**list_kwargs).execute()
        
        logging.info(f"Fetched {len(events.get('items', []))} Google events.")
        return events
