import os
import sys
from rich.console import Console
from rich.panel import Panel
import questionary
from config import load_config, save_config
from log_analysis import analyze_log_file
from github_context import fetch_code_context

console = Console()

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

if __name__ == "__main__":
    main_menu() 