import os
import sys
from rich.console import Console
from rich.panel import Panel
import questionary
from config import load_config, save_config
from log_analysis import analyze_log_file
from github_context import fetch_code_context
import requests
import threading
import time

console = Console()

LLAMALYTICSHUB_URL = os.environ.get("LLAMALYTICSHUB_URL", "http://localhost:5000")

log_watcher_thread = None
log_watcher_stop = threading.Event()

def print_banner():
    console.print(Panel("Llogfather Log Analysis CLI", style="bold magenta"))

def main_menu():
    while True:
        print_banner()
        choice = questionary.select(
            "Main Menu:",
            choices=[
                "Analyze Log File",
                "Configure GitHub Token",
                "View Config",
                "Call LlamalyticsHub API Endpoints",
                "Start Log Watcher",
                "Exit"
            ]
        ).ask()
        if choice == "Analyze Log File":
            analyze_log_file_flow()
        elif choice == "Configure GitHub Token":
            configure_github_token()
        elif choice == "View Config":
            config = load_config()
            console.print(config)
            input("Press Enter to return to menu...")
        elif choice == "Call LlamalyticsHub API Endpoints":
            call_llamalyticshub_menu()
        elif choice == "Start Log Watcher":
            start_log_watcher_menu()
        elif choice == "Exit":
            sys.exit(0)

def analyze_log_file_flow():
    log_file = questionary.path("Select log file to analyze:").ask()
    config = load_config()
    github_token = config.get("github_token")
    repo = questionary.text("GitHub repo (user/repo) for context (optional):").ask()
    output_dir = questionary.path("Output directory for report:", default="reports").ask()
    os.makedirs(output_dir, exist_ok=True)
    code_context = None
    if github_token and repo:
        code_context = fetch_code_context(repo, github_token)
    report = analyze_log_file(log_file, code_context)
    report_path = os.path.join(output_dir, f"log_report_{os.path.basename(log_file)}.md")
    with open(report_path, "w") as f:
        f.write(report)
    console.print(f"[green]Report saved to {report_path}[/green]")
    input("Press Enter to return to menu...")

def configure_github_token():
    token = questionary.text("Enter your GitHub API token:").ask()
    config = load_config()
    config["github_token"] = token
    save_config(config)
    console.print("[green]GitHub token saved.[/green]")
    input("Press Enter to return to menu...")

def call_llamalyticshub_menu():
    endpoints = [
        ("/help", "GET"),
        ("/generate/text", "POST"),
        ("/generate/file", "POST"),
        ("/generate/github-pr", "POST"),
        ("/health", "GET"),
        ("/reports", "GET"),
        ("/reports/<report_name>", "GET"),
        ("/logs", "GET"),
    ]
    cache_dir = "cached_reports"
    os.makedirs(cache_dir, exist_ok=True)
    while True:
        choice = questionary.select(
            "LlamalyticsHub API Endpoints:",
            choices=[e[0] for e in endpoints] + ["Back"]
        ).ask()
        if choice == "Back":
            break
        config = load_config()
        api_key = config.get("llamalyticshub_api_key", "changeme")
        headers = {"X-API-KEY": api_key}
        url = LLAMALYTICSHUB_URL.rstrip("/")
        if choice == "/help":
            resp = requests.get(f"{url}/help", headers=headers)
            console.print(resp.json())
        elif choice == "/generate/text":
            prompt = questionary.text("Prompt to analyze:").ask()
            resp = requests.post(f"{url}/generate/text", json={"prompt": prompt}, headers=headers)
            console.print(resp.json())
        elif choice == "/generate/file":
            file_path = questionary.path("Path to file to analyze:").ask()
            with open(file_path, "rb") as f:
                files = {"file": f}
                resp = requests.post(f"{url}/generate/file", files=files, headers=headers)
            console.print(resp.json())
        elif choice == "/generate/github-pr":
            repo = questionary.text("GitHub repo (user/repo):").ask()
            pr_number = questionary.text("PR number:").ask()
            token = questionary.text("GitHub token (leave blank to use config):").ask()
            prompt = questionary.text("Prompt (optional):").ask()
            payload = {"repo": repo, "pr_number": int(pr_number)}
            if token:
                payload["token"] = token
            if prompt:
                payload["prompt"] = prompt
            resp = requests.post(f"{url}/generate/github-pr", json=payload, headers=headers)
            console.print(resp.json())
        elif choice == "/health":
            resp = requests.get(f"{url}/health", headers=headers)
            console.print(resp.json())
        elif choice == "/reports":
            resp = requests.get(f"{url}/reports", headers=headers)
            reports = resp.json().get("reports", [])
            console.print(reports)
        elif choice == "/reports/<report_name>":
            report_name = questionary.text("Report filename (e.g. my_report.md):").ask()
            cache_path = os.path.join(cache_dir, report_name)
            use_cache = False
            if os.path.exists(cache_path):
                use_cache = questionary.confirm(f"Cached report found. Use cached version?", default=True).ask()
            if use_cache:
                with open(cache_path, "r", encoding="utf-8") as f:
                    content = f.read()
                console.print(content)
            else:
                resp = requests.get(f"{url}/reports/{report_name}", headers=headers)
                if resp.status_code == 200:
                    content = resp.text
                    with open(cache_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    console.print(content)
                else:
                    console.print(resp.json())
        elif choice == "/logs":
            resp = requests.get(f"{url}/logs", headers=headers)
            if resp.status_code == 200:
                console.print(resp.text)
            else:
                console.print(resp.json())
        input("Press Enter to return to endpoint menu...")

def start_log_watcher():
    """
    Polls /logs endpoint every 10 seconds, extracts new errors/warnings, and appends to log_watcher.md.
    """
    config = load_config()
    api_key = config.get("llamalyticshub_api_key", "changeme")
    headers = {"X-API-KEY": api_key}
    url = LLAMALYTICSHUB_URL.rstrip("/") + "/logs"
    last_seen = set()
    log_file = "log_watcher.md"
    console.print(f"[yellow]Log watcher started. Polling {url} every 10 seconds. Press Enter in the main menu to stop.[/yellow]")
    with open(log_file, "a") as f:
        f.write(f"# Log Watcher Report\n\n")
    while not log_watcher_stop.is_set():
        try:
            resp = requests.get(url, headers=headers)
            if resp.status_code == 200:
                lines = resp.text.splitlines()
                new_entries = []
                for line in lines:
                    if ("error" in line.lower() or "warning" in line.lower()) and line not in last_seen:
                        new_entries.append(line)
                        last_seen.add(line)
                if new_entries:
                    with open(log_file, "a") as f:
                        for entry in new_entries:
                            f.write(entry + "\n")
            else:
                console.print(f"[red]Failed to fetch logs: {resp.status_code}[/red]")
        except Exception as e:
            console.print(f"[red]Exception in log watcher: {e}[/red]")
        time.sleep(10)
    console.print("[yellow]Log watcher stopped.[/yellow]")

def start_log_watcher_menu():
    global log_watcher_thread, log_watcher_stop
    if log_watcher_thread and log_watcher_thread.is_alive():
        console.print("[yellow]Log watcher is already running.[/yellow]")
        return
    log_watcher_stop.clear()
    log_watcher_thread = threading.Thread(target=start_log_watcher, daemon=True)
    log_watcher_thread.start()
    input("Press Enter to stop log watcher and return to menu...")
    log_watcher_stop.set()
    log_watcher_thread.join()

if __name__ == "__main__":
    main_menu() 