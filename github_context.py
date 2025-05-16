import os
import requests

def fetch_code_context(repo, github_token):
    """
    Fetch code context from GitHub: README and file list.
    Returns a dict with 'readme' and 'files'.
    """
    headers = {"Authorization": f"token {github_token}"}
    api_url = f"https://api.github.com/repos/{repo}"
    result = {}
    # Fetch README
    readme_resp = requests.get(f"{api_url}/readme", headers=headers, params={"accept": "application/vnd.github.v3.raw"})
    if readme_resp.status_code == 200:
        result["readme"] = readme_resp.text
    else:
        result["readme"] = None
    # Fetch file list (root only for now)
    files_resp = requests.get(f"{api_url}/contents", headers=headers)
    if files_resp.status_code == 200:
        result["files"] = [f["name"] for f in files_resp.json() if f["type"] == "file"]
    else:
        result["files"] = []
    return result

def fetch_file_content(repo, github_token, file_path, ref=None):
    """
    Fetch the content of a specific file from GitHub.
    """
    headers = {"Authorization": f"token {github_token}"}
    api_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    params = {}
    if ref:
        params["ref"] = ref
    resp = requests.get(api_url, headers=headers, params=params)
    if resp.status_code == 200:
        import base64
        content = resp.json().get("content", "")
        if content:
            return base64.b64decode(content).decode("utf-8")
    return None

def cache_github_files(repo, github_token, file_paths, branch=None, pr_number=None):
    """
    Cache files from a GitHub repo for a specific branch or PR.
    Files are saved in cached_github_files/<repo>/<branch_or_pr>/
    """
    base_dir = os.path.join("cached_github_files", repo.replace('/', '__'))
    ref_label = f"pr_{pr_number}" if pr_number else (branch or "main")
    target_dir = os.path.join(base_dir, ref_label)
    os.makedirs(target_dir, exist_ok=True)
    for file_path in file_paths:
        content = fetch_file_content(repo, github_token, file_path, ref=branch)
        if content is not None:
            local_path = os.path.join(target_dir, os.path.basename(file_path))
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            print(f"[WARN] Could not fetch {file_path} from {repo} ({ref_label})")
    print(f"Cached files in {target_dir}") 