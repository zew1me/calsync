# CalSync

CalSync is a command-line tool to sync events from Apple Calendar (iCloud, via CalDAV) to Google Calendar. It uses protocol-native incremental sync tokens for fast, reliable, and idempotent synchronization. Configuration and usage are managed via a simple CLI interface.

## Features

- Sync events from a specific Apple Calendar (via CalDAV) to a Google Calendar.
- Fast, incremental syncs using native sync tokens (Google `nextSyncToken`, Apple CalDAV `sync-token`).
- Robust handling of all-day, timed, and timezone-aware events.
- Idempotent event mapping using a persistent GUID map.
- CLI for configuration and syncing.
- No 2FA or interactive login required for Apple Calendar (uses app-specific password).

## Requirements

- Python 3.12 or higher
- Apple ID with an app-specific password (see [Apple Support](https://support.apple.com/en-us/HT204397))
- Google API credentials JSON file (OAuth2)
- CalDAV access enabled for your Apple account

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/zew1me/calsync.git
   cd calsync
   ```

2. Install dependencies using `uv`:
   ```bash
   uv sync
   ```

## Configuration

1. Run the configuration command to set up Apple (CalDAV) and Google Calendars:
   ```bash
   uv run python cli.py configure
   ```
   - Enter your Apple ID email and **app-specific password** (not your main password).
   - Enter your Apple CalDAV URL (default: `https://caldav.icloud.com`).
   - Provide the path to your Google API credentials JSON file.
   - Select the Google calendar to sync to.

2. The configuration will be saved in a local `settings.toml` file.

## Usage

To sync events from Apple Calendar to Google Calendar, run:
```bash
uv run python cli.py sync
```
The tool will use incremental sync tokens for both Google and Apple, and will only do a full resync if a token expires or is invalidated by the server.

## Development

### Adding Dependencies

Use `uv` to manage dependencies:
- Add a new dependency:
  ```bash
  uv add <package-name>
  ```
- Remove a dependency:
  ```bash
  uv remove <package-name>
  ```

### Running Tests

Run tests using:
```bash
uv run pytest
```

## License

This project is licensed under the MIT License.