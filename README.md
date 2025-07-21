# CalSync

CalSync is a command-line tool to sync events between Apple Calendar (iCloud) and Google Calendar. It supports delta syncs and allows configuration of calendars via a simple CLI interface.

## Features

- Sync events from a specific Apple Calendar to a Google Calendar.
- Delta syncs using cached `last sync` timestamps.
- CLI for configuration and syncing.
- Supports multiple credential types using `dynaconf`.

## Requirements

- Python 3.12 or higher
- Apple ID with an app-specific password
- Google API credentials JSON file

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

1. Run the configuration command to set up Apple and Google Calendars:
   ```bash
   python cli.py configure
   ```

   - Enter your Apple ID email and app-specific password.
   - Provide the path to your Google API credentials JSON file.
   - Select the Apple and Google calendars to sync.

2. The configuration will be saved in a local `settings.toml` file managed by `dynaconf`.

## Usage

To sync events from Apple Calendar to Google Calendar, run:
```bash
python cli.py sync
```

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