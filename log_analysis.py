import re
from collections import Counter, defaultdict
from datetime import datetime
import requests

def parse_log_levels_and_timestamps(lines):
    log_level_pattern = re.compile(r"\\b(INFO|ERROR|WARNING|DEBUG|CRITICAL)\\b", re.IGNORECASE)
    timestamp_pattern = re.compile(r"(\\d{4}-\\d{2}-\\d{2}[ T]\\d{2}:\\d{2}:\\d{2})")
    levels = []
    timestamps = []
    for line in lines:
        lvl = log_level_pattern.search(line)
        if lvl:
            levels.append(lvl.group(1).upper())
        ts = timestamp_pattern.search(line)
        if ts:
            try:
                timestamps.append(datetime.fromisoformat(ts.group(1).replace(' ', 'T')))
            except Exception:
                pass
    return levels, timestamps

def parse_python_stack_traces(lines):
    stack_traces = []
    current_trace = []
    in_trace = False
    for line in lines:
        if line.strip().startswith('Traceback (most recent call last):'):
            if current_trace:
                stack_traces.append(list(current_trace))
                current_trace = []
            in_trace = True
            current_trace.append(line)
        elif in_trace and (line.startswith('  File') or line.strip().startswith('File')):
            current_trace.append(line)
        elif in_trace and (line.strip() == '' or re.match(r'\w*Error:|Exception:', line.strip())):
            current_trace.append(line)
            stack_traces.append(list(current_trace))
            current_trace = []
            in_trace = False
        elif in_trace:
            current_trace.append(line)
    if current_trace:
        stack_traces.append(list(current_trace))
    return stack_traces

def parse_java_stack_traces(lines):
    stack_traces = []
    current_trace = []
    in_trace = False
    for line in lines:
        if re.match(r'^([a-zA-Z0-9_$.]+Exception|Error):', line.strip()):
            if current_trace:
                stack_traces.append(list(current_trace))
                current_trace = []
            in_trace = True
            current_trace.append(line)
        elif in_trace and re.match(r'^\\s*at ', line):
            current_trace.append(line)
        elif in_trace and line.strip() == '':
            stack_traces.append(list(current_trace))
            current_trace = []
            in_trace = False
        elif in_trace:
            current_trace.append(line)
    if current_trace:
        stack_traces.append(list(current_trace))
    return stack_traces

def parse_nodejs_stack_traces(lines):
    stack_traces = []
    current_trace = []
    in_trace = False
    for line in lines:
        if re.match(r'^(\w*Error|Exception):', line.strip()):
            if current_trace:
                stack_traces.append(list(current_trace))
                current_trace = []
            in_trace = True
            current_trace.append(line)
        elif in_trace and re.match(r'^\\s*at ', line):
            current_trace.append(line)
        elif in_trace and line.strip() == '':
            stack_traces.append(list(current_trace))
            current_trace = []
            in_trace = False
        elif in_trace:
            current_trace.append(line)
    if current_trace:
        stack_traces.append(list(current_trace))
    return stack_traces

def extract_stack_trace_info(trace, language):
    entries = []
    if language == 'python':
        for line in trace:
            m = re.match(r'\s*File "([^"]+)", line (\d+), in (.+)', line)
            if m:
                entries.append({
                    'file': m.group(1),
                    'line': int(m.group(2)),
                    'func': m.group(3)
                })
    elif language == 'java':
        for line in trace:
            m = re.match(r'\s*at ([\w.$]+)\(([^:]+):(\d+)\)', line)
            if m:
                entries.append({
                    'file': m.group(2),
                    'line': int(m.group(3)),
                    'func': m.group(1)
                })
    elif language == 'nodejs':
        for line in trace:
            m = re.match(r'\s*at (?:([\w.< anonymous >]+) )?\(?([^:]+):(\d+):(\d+)\)?', line)
            if m:
                entries.append({
                    'file': m.group(2),
                    'line': int(m.group(3)),
                    'func': m.group(1) or ''
                })
    return entries

def get_code_snippet(file_content, line, context=5):
    lines = file_content.splitlines()
    start = max(0, line - context - 1)
    end = min(len(lines), line + context)
    snippet = lines[start:end]
    return '\n'.join(f"{i+1}: {l}" for i, l in enumerate(snippet, start=start))

def summarize_relationship_with_llm(log_findings, report_context, llm_url="http://localhost:5000/generate/text", api_key=None):
    prompt = f"Given the following service log findings and a cached code review report, summarize any relationships, root causes, or actionable insights that connect the two.\n\nService Log Findings:\n{log_findings}\n\nCached Report:\n{report_context[:2000]}"  # Truncate for prompt size
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-KEY"] = api_key
    try:
        resp = requests.post(llm_url, json={"prompt": prompt}, headers=headers, timeout=60)
        if resp.status_code == 200:
            return resp.json().get("response", "(No summary returned)")
        else:
            return f"(LLM error: {resp.status_code} {resp.text})"
    except Exception as e:
        return f"(LLM request failed: {e})"

def suggest_patch_with_llm(error_line, code_files_context, llm_url="http://localhost:5000/generate/text", api_key=None):
    # Use the LLM to suggest a patch for the error/warning, using code files as context
    code_context_str = "\n\n".join(f"File: {f['filename']}\n{f['content'][:1000]}" for f in code_files_context)
    prompt = f"Given the following error or warning from a service log, and the following code files, suggest a code patch or fix for the issue.\n\nError/Warning:\n{error_line}\n\nCode Files:\n{code_context_str}"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-KEY"] = api_key
    try:
        resp = requests.post(llm_url, json={"prompt": prompt}, headers=headers, timeout=90)
        if resp.status_code == 200:
            return resp.json().get("response", "(No patch suggestion returned)")
        else:
            return f"(LLM error: {resp.status_code} {resp.text})"
    except Exception as e:
        return f"(LLM request failed: {e})"

def analyze_log_file(log_file_path, code_context=None, report_context=None, llm_api_key=None, code_files_context=None):
    """
    Analyze the log file and return a markdown report as a string.
    Optionally use code_context for deeper analysis.
    """
    report = [f"# Log Analysis Report for `{log_file_path}`\n"]
    try:
        with open(log_file_path, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        return f"# Error\nCould not read log file: {e}"
    # Log level and timestamp analysis
    levels, timestamps = parse_log_levels_and_timestamps(lines)
    level_counter = Counter(levels)
    report.append(f"## Log Levels\n" + '\n'.join(f"- {lvl}: {cnt}" for lvl, cnt in level_counter.most_common()))
    if timestamps:
        by_hour = defaultdict(int)
        for ts in timestamps:
            by_hour[ts.replace(minute=0, second=0, microsecond=0)] += 1
        report.append("\n## Log Frequency by Hour\n" + '\n'.join(f"- {hour}: {cnt}" for hour, cnt in sorted(by_hour.items())))
    # Error summary
    error_lines = [l for l in lines if 'error' in l.lower() or 'warning' in l.lower() or 'exception' in l.lower()]
    error_types = [re.findall(r'(\w+Error|Exception|Warning)', l) for l in error_lines]
    error_types_flat = [item for sublist in error_types for item in sublist]
    error_counter = Counter(error_types_flat)
    report.append(f"\n## Error Summary\n- Total lines: {len(lines)}\n- Error/Warning/Exception lines: {len(error_lines)}\n")
    if error_counter:
        report.append("### Top Error/Warning Types\n")
        for err, count in error_counter.most_common(10):
            report.append(f"- {err}: {count}")
    # Stack trace analysis
    stack_traces = {
        'python': parse_python_stack_traces(lines),
        'java': parse_java_stack_traces(lines),
        'nodejs': parse_nodejs_stack_traces(lines)
    }
    for lang, traces in stack_traces.items():
        if traces:
            report.append(f"\n## {lang.capitalize()} Stack Traces Found: {len(traces)}\n")
            for idx, trace in enumerate(traces, 1):
                report.append(f"### Stack Trace {idx}\n```")
                report.extend(trace)
                report.append("```")
                entries = extract_stack_trace_info(trace, lang)
                if entries and code_context:
                    for entry in entries:
                        file_content = None
                        if callable(getattr(code_context, 'fetch_file_content', None)):
                            file_content = code_context.fetch_file_content(entry['file'])
                        elif isinstance(code_context, dict) and 'files' in code_context:
                            for f in code_context['files']:
                                if f.get('filename', '').endswith(entry['file']):
                                    file_content = f.get('content')
                                    break
                        if file_content:
                            snippet = get_code_snippet(file_content, entry['line'])
                            report.append(f"#### Code Snippet for {entry['file']} line {entry['line']}\n```")
                            report.append(snippet)
                            report.append("```")
    # If report_context is provided, include it and relate to log findings
    if report_context:
        report.append("\n## Related Cached Report Context\n")
        report.append("---\n**Cached Report Excerpt:**\n\n" + report_context[:1000] + ("..." if len(report_context) > 1000 else ""))
        # Simple heuristic: check if any error types from logs appear in the report context
        related = []
        for err in error_counter:
            if err in report_context:
                related.append(err)
        if related:
            report.append(f"\n**The following error types from the logs were also mentioned in the cached report:**\n- " + ", ".join(related))
        else:
            report.append("\nNo direct overlap found between log errors and cached report.")
        # LLM summary section
        log_findings_summary = '\n'.join(report)
        llm_summary = summarize_relationship_with_llm(log_findings_summary, report_context, api_key=llm_api_key)
        report.append("\n## LLM Summary: Relationship Between Logs and Cached Report\n")
        report.append(llm_summary)
    # LLM patch suggestions for errors/warnings
    if code_files_context:
        report.append("\n## LLM Patch Suggestions for Errors/Warnings\n")
        for err_line in error_lines:
            patch = suggest_patch_with_llm(err_line, code_files_context, api_key=llm_api_key)
            report.append(f"### Patch Suggestion for: {err_line.strip()}\n{patch}\n")
    if code_context:
        report.append("\n## Code Context (from GitHub)\n")
        if isinstance(code_context, dict):
            if 'readme' in code_context and code_context['readme']:
                report.append("### README.md\n\n" + code_context['readme'][:1000] + ('...' if len(code_context['readme']) > 1000 else ''))
            if 'files' in code_context:
                report.append(f"\n### Files in repo: {len(code_context['files'])}")
    return '\n'.join(report) 