def fetch_code_context(repo, github_token):
    """
    Fetch code context from GitHub: README and file list.
    Returns a dict with 'readme' and 'files'.
    """
    import requests
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