# Llogfather Log Analysis CLI

A modern Python CLI for analyzing log files, inspired by LlamalyticsHub.

## Features
- Interactive CLI with modern UI (Rich, Questionary)
- Analyze log files for errors, exceptions, and patterns
- Optionally use a GitHub API token to fetch code context for deeper analysis
- Save analysis reports to a configurable output directory
- Simple config management for GitHub token

## Setup
1. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```
2. (Optional) Set your GitHub API token via the CLI for private repo access.

## Usage
Run the CLI:
```sh
python cli.py
```

### Main Menu Options
- Analyze Log File: Select a log file, optionally provide a GitHub repo for context, and generate a markdown report.
- Configure GitHub Token: Save your GitHub API token for future use.
- View Config: View current configuration (e.g., saved token).
- Exit: Quit the CLI.

## Example Workflow
1. Choose "Analyze Log File" from the menu.
2. Select your log file.
3. (Optional) Enter a GitHub repo (user/repo) for code context.
4. Choose an output directory for the report.
5. View the generated markdown report in the output directory.

## Configuration
- The CLI stores your GitHub token in a local `config.json` file.
- You can update or remove this token at any time via the menu.

## License
MIT
