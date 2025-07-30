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
    def __init__(self, credentials_path, token_path="token.json"):
        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        creds = None
        # Try to load cached credentials
        if os.path.exists(token_path):
            logging.debug(f"Loading Google credentials from {token_path}")
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        # If no valid creds, do OAuth flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logging.debug("Refreshing expired Google credentials.")
                creds.refresh(Request())
            else:
                logging.debug(f"Running OAuth flow for Google credentials from {credentials_path}")
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
            logging.debug(f"Saved new Google credentials to {token_path}")
        self.creds = creds
        self.service = build('calendar', 'v3', credentials=self.creds)

    def list_calendars(self):
        logging.debug("Listing Google calendars.")
        calendars = self.service.calendarList().list().execute()
        logging.info(f"Fetched {len(calendars['items'])} Google Calendars.")
        return calendars['items']

    def insert_event(self, calendar_id, event, apple_guid):
        logging.debug(f"Inserting event into Google calendar {calendar_id} with Apple GUID {apple_guid}")
        # Insert the event
        created_event = self.service.events().insert(calendarId=calendar_id, body=event).execute()
        logging.info(f"Event created: {created_event['id']}")

        # If a GUID is provided, find and delete duplicate events with the same GUID
        if apple_guid:
            logging.debug(f"Checking for duplicate Google events with Apple GUID {apple_guid}")
            events = self.service.events().list(calendarId=calendar_id, q=apple_guid).execute()
            for existing_event in events.get('items', []):
                # Skip the event that was just created
                if existing_event['id'] != created_event['id']:
                    self.service.events().delete(calendarId=calendar_id, eventId=existing_event['id']).execute()
                    logging.info(f"Deleted duplicate event: {existing_event['id']}")

        return created_event
