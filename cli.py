import os
import sys
from rich.console import Console
from rich.panel import Panel
import questionary
from config import load_config, save_config
from log_analysis import analyze_log_file
from github_context import fetch_code_context
import requests

console = Console()

LLAMALYTICSHUB_URL = os.environ.get("LLAMALYTICSHUB_URL", "http://localhost:5000")

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
            resp = requests.get(f"{url}/reports/{report_name}", headers=headers)
            if resp.status_code == 200:
                console.print(resp.text)
            else:
                console.print(resp.json())
        elif choice == "/logs":
            resp = requests.get(f"{url}/logs", headers=headers)
            if resp.status_code == 200:
                console.print(resp.text)
            else:
                console.print(resp.json())
        input("Press Enter to return to endpoint menu...")

if __name__ == "__main__":
    main_menu() 