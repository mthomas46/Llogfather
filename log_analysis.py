import re
from collections import Counter, defaultdict
from datetime import datetime

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

def analyze_log_file(log_file_path, code_context=None):
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
    error_lines = [l for l in lines if 'error' in l.lower() or 'exception' in l.lower()]
    error_types = [re.findall(r'(\w+Error|Exception)', l) for l in error_lines]
    error_types_flat = [item for sublist in error_types for item in sublist]
    error_counter = Counter(error_types_flat)
    report.append(f"\n## Error Summary\n- Total lines: {len(lines)}\n- Error/Exception lines: {len(error_lines)}\n")
    if error_counter:
        report.append("### Top Error Types\n")
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
    if code_context:
        report.append("\n## Code Context (from GitHub)\n")
        if isinstance(code_context, dict):
            if 'readme' in code_context and code_context['readme']:
                report.append("### README.md\n\n" + code_context['readme'][:1000] + ('...' if len(code_context['readme']) > 1000 else ''))
            if 'files' in code_context:
                report.append(f"\n### Files in repo: {len(code_context['files'])}")
    return '\n'.join(report) 