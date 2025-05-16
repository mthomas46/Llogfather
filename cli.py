import os
import sys
from rich.console import Console
from rich.panel import Panel
import questionary
from config import load_config, save_config
from log_analysis import analyze_log_file
from github_context import fetch_code_context, fetch_file_content, cache_github_files
import requests
import threading
import time
import shutil
import re

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
                "Cache GitHub Files",
                "Manage Cached GitHub Files",
                "Jira Issue Management",
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
        elif choice == "Cache GitHub Files":
            cache_github_files_menu()
        elif choice == "Manage Cached GitHub Files":
            manage_cached_github_files_menu()
        elif choice == "Jira Issue Management":
            jira_issue_management_menu()
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
    # Optionally use cached report as context
    cache_dir = "cached_reports"
    report_context = None
    if os.path.isdir(cache_dir):
        cached_reports = [f for f in os.listdir(cache_dir) if f.endswith('.md')]
        if cached_reports:
            use_report = questionary.confirm("Use a cached report as context for log analysis?", default=False).ask()
            if use_report:
                report_name = questionary.select("Select cached report:", choices=cached_reports).ask()
                with open(os.path.join(cache_dir, report_name), "r", encoding="utf-8") as f:
                    report_context = f.read()
    # Optionally use cached code files as context
    cached_code_dir = "cached_github_files"
    code_files_context = []
    if os.path.isdir(cached_code_dir):
        repos = [d for d in os.listdir(cached_code_dir) if os.path.isdir(os.path.join(cached_code_dir, d))]
        if repos:
            use_code = questionary.confirm("Use cached code files as context?", default=False).ask()
            if use_code:
                repo_choice = questionary.select("Select cached repo:", choices=repos).ask()
                repo_path = os.path.join(cached_code_dir, repo_choice)
                refs = [d for d in os.listdir(repo_path) if os.path.isdir(os.path.join(repo_path, d))]
                ref_choice = questionary.select("Select branch/PR:", choices=refs).ask()
                ref_path = os.path.join(repo_path, ref_choice)
                files = [f for f in os.listdir(ref_path) if os.path.isfile(os.path.join(ref_path, f))]
                file_choices = questionary.checkbox("Select code files to use as context:", choices=files).ask()
                for fname in file_choices:
                    with open(os.path.join(ref_path, fname), "r", encoding="utf-8") as f:
                        code_files_context.append({"filename": fname, "content": f.read()})
    llm_api_key = config.get("llamalyticshub_api_key")
    report = analyze_log_file(log_file, code_context, report_context, llm_api_key=llm_api_key, code_files_context=code_files_context)
    report_path = os.path.join(output_dir, f"log_report_{os.path.basename(log_file)}.md")
    with open(report_path, "w") as f:
        f.write(report)
    console.print(f"[green]Report saved to {report_path}[/green]")

    # --- Create a report of suggested Jira tickets ---
    ticket_report_path = os.path.join(output_dir, f"suggested_tickets_{os.path.basename(log_file)}.md")
    patch_sections = re.findall(r"### Patch Suggestion for: (.*?)\n(.*?)(?=\n### Patch Suggestion for:|\Z)", report, re.DOTALL)
    if patch_sections:
        with open(ticket_report_path, "w") as tf:
            tf.write(f"# Suggested Jira Tickets for {os.path.basename(log_file)}\n\n")
            for idx, (error_summary, patch) in enumerate(patch_sections, 1):
                tf.write(f"## Ticket {idx}\n")
                tf.write(f"**Summary:** {error_summary.strip()[:100]}\n\n")
                tf.write(f"**Description:**\n\n{patch.strip()[:2000]}\n\n")
        console.print(f"[yellow]Suggested Jira tickets report saved to {ticket_report_path}[/yellow]")
    else:
        console.print("[yellow]No patch suggestions found for Jira ticket report.[/yellow]")

    # --- Prompt user for next action ---
    next_action = questionary.select(
        "What would you like to do next?",
        choices=[
            "Just create the ticket report",
            "Create tickets in Jira",
            "Both",
            "Nothing"
        ]
    ).ask()

    jira_url = get_config_value("JIRASSICPACK_URL", "http://localhost:5050")
    if next_action in ["Create tickets in Jira", "Both"] and patch_sections:
        project = questionary.text("Jira project key for ticket creation (or leave blank to skip):").ask()
        if project:
            # Let user select which tickets to create
            ticket_choices = [f"{error_summary.strip()[:100]}" for error_summary, _ in patch_sections]
            selected = questionary.checkbox(
                "Select which tickets to create in Jira:", choices=ticket_choices
            ).ask()
            for (error_summary, patch), label in zip(patch_sections, ticket_choices):
                if label in selected:
                    summary = error_summary.strip()[:100]
                    description = patch.strip()[:2000]
                    issuetype = questionary.text("Issue type (default: Task):", default="Task").ask()
                    payload = {
                        "project": project,
                        "summary": summary,
                        "description": description,
                        "issuetype": issuetype
                    }
                    resp = requests.post(f"{jira_url}/jira/ticket", json=payload)
                    console.print(f"[yellow]Jira ticket creation response:[/yellow] {resp.json()}")
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

def cache_github_files_menu():
    repo = questionary.text("GitHub repo (user/repo):").ask()
    config = load_config()
    github_token = config.get("github_token")
    branch_or_pr = questionary.select(
        "Cache files from branch or PR?",
        choices=["Branch", "PR"]
    ).ask()
    branch = pr_number = None
    if branch_or_pr == "Branch":
        branch = questionary.text("Branch name (default: main):", default="main").ask()
    else:
        pr_number = questionary.text("PR number:").ask()
    # Fetch file list for selection
    code_context = fetch_code_context(repo, github_token)
    file_choices = code_context.get("files", [])
    if not file_choices:
        file_paths = questionary.text("Enter file paths to cache (comma-separated):").ask().split(",")
        file_paths = [f.strip() for f in file_paths if f.strip()]
    else:
        file_paths = questionary.checkbox("Select files to cache:", choices=file_choices).ask()
    cache_github_files(repo, github_token, file_paths, branch=branch, pr_number=pr_number)
    input("Press Enter to return to menu...")

def manage_cached_github_files_menu():
    cache_root = "cached_github_files"
    if not os.path.isdir(cache_root):
        console.print("[yellow]No cached GitHub files found.[/yellow]")
        input("Press Enter to return to menu...")
        return
    # List repos
    repos = [d for d in os.listdir(cache_root) if os.path.isdir(os.path.join(cache_root, d))]
    if not repos:
        console.print("[yellow]No cached GitHub repos found.[/yellow]")
        input("Press Enter to return to menu...")
        return
    repo = questionary.select("Select cached repo:", choices=repos + ["Back"]).ask()
    if repo == "Back":
        return
    repo_path = os.path.join(cache_root, repo)
    # List branches/PRs
    refs = [d for d in os.listdir(repo_path) if os.path.isdir(os.path.join(repo_path, d))]
    ref = questionary.select("Select branch/PR:", choices=refs + ["Back"]).ask()
    if ref == "Back":
        return
    ref_path = os.path.join(repo_path, ref)
    # List files
    files = [f for f in os.listdir(ref_path) if os.path.isfile(os.path.join(ref_path, f))]
    if not files:
        console.print("[yellow]No cached files found for this repo/branch/PR.[/yellow]")
        input("Press Enter to return to menu...")
        return
    while True:
        action = questionary.select(
            "Manage Cached Files:",
            choices=["View file", "Delete file", "Delete all for this branch/PR", "Back"]
        ).ask()
        if action == "Back":
            break
        elif action == "View file":
            file_choice = questionary.select("Select file to view:", choices=files).ask()
            with open(os.path.join(ref_path, file_choice), "r", encoding="utf-8") as f:
                content = f.read()
            console.print(f"[bold]{file_choice}[/bold]\n" + content)
            input("Press Enter to continue...")
        elif action == "Delete file":
            file_choice = questionary.select("Select file to delete:", choices=files).ask()
            os.remove(os.path.join(ref_path, file_choice))
            files.remove(file_choice)
            console.print(f"[red]Deleted {file_choice}.[/red]")
            if not files:
                console.print("[yellow]No cached files left for this branch/PR.[/yellow]")
                break
        elif action == "Delete all for this branch/PR":
            shutil.rmtree(ref_path)
            console.print(f"[red]Deleted all cached files for {repo}/{ref}.[/red]")
            break
    input("Press Enter to return to menu...")

def jira_issue_management_menu():
    jira_url = get_config_value("JIRASSICPACK_URL", "http://localhost:5050")
    while True:
        action = questionary.select(
            "Jira Issue Management:",
            choices=[
                "Create Issue",
                "Update Issue",
                "Get Issue",
                "Search Issues",
                "Back"
            ]
        ).ask()
        if action == "Back":
            break
        elif action == "Create Issue":
            project = questionary.text("Project key (e.g. ABC):").ask()
            summary = questionary.text("Summary:").ask()
            description = questionary.text("Description:").ask()
            issuetype = questionary.text("Issue type (default: Task):", default="Task").ask()
            payload = {
                "project": project,
                "summary": summary,
                "description": description,
                "issuetype": issuetype
            }
            resp = requests.post(f"{jira_url}/jira/ticket", json=payload)
            console.print(resp.json())
        elif action == "Update Issue":
            issue_id = questionary.text("Issue ID (e.g. ABC-123):").ask()
            field_key = questionary.text("Field to update (e.g. summary):").ask()
            field_value = questionary.text("New value:").ask()
            payload = {"fields": {field_key: field_value}}
            resp = requests.put(f"{jira_url}/jira/ticket/{issue_id}", json=payload)
            console.print(resp.json())
        elif action == "Get Issue":
            issue_id = questionary.text("Issue ID (e.g. ABC-123):").ask()
            resp = requests.get(f"{jira_url}/jira/ticket/{issue_id}")
            console.print(resp.json())
        elif action == "Search Issues":
            jql = questionary.text("JQL query (e.g. project=ABC AND status=Open):").ask()
            resp = requests.get(f"{jira_url}/jira/search", params={"jql": jql})
            console.print(resp.json())
        input("Press Enter to return to Jira menu...")

if __name__ == "__main__":
    main_menu() 