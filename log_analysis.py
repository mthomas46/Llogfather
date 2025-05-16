def analyze_log_file(log_file_path, code_context=None):
    """
    Analyze the log file and return a markdown report as a string.
    Optionally use code_context for deeper analysis.
    """
    from collections import Counter
    import re
    report = [f"# Log Analysis Report for `{log_file_path}`\n"]
    try:
        with open(log_file_path, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        return f"# Error\nCould not read log file: {e}"
    error_lines = [l for l in lines if 'error' in l.lower() or 'exception' in l.lower()]
    error_types = [re.findall(r'(\w+Error|Exception)', l) for l in error_lines]
    error_types_flat = [item for sublist in error_types for item in sublist]
    error_counter = Counter(error_types_flat)
    report.append(f"## Summary\n- Total lines: {len(lines)}\n- Error/Exception lines: {len(error_lines)}\n")
    if error_counter:
        report.append("## Top Error Types\n")
        for err, count in error_counter.most_common(10):
            report.append(f"- {err}: {count}")
    if code_context:
        report.append("\n## Code Context (from GitHub)\n")
        report.append(str(code_context)[:1000] + '...')
    return '\n'.join(report) 