import sys
import json
import re

def is_dynamic_eval(line):
    return re.search(r"eval\(.*\)", line) is not None

def is_shell_execution(line):
    # Matches subprocess.run, call, Popen, check_call, check_output with shell=True
    pattern = r"subprocess\.(run|call|Popen|check_call|check_output)\s*\((?:.*?)\s*shell=True.*?\)"
    return re.search(pattern, line)

def analyze_diff(diff_content, path):
    findings = []
    # Regex to capture hunk headers like @@ -L,C +L,C @@
    hunk_header_pattern = re.compile(r"@@ -\d+,\d+ \+(\d+),\d+ @@")

    # Track line numbers within the added lines
    current_line_num = 0

    for line in diff_content.splitlines():
        if line.startswith('---') or line.startswith('+++'):
            continue

        hunk_match = hunk_header_pattern.search(line)
        if hunk_match:
            # The first group is the starting line number of the new file (+ lines)
            current_line_num = int(hunk_match.group(1))

        elif line.startswith(' '):
            current_line_num += 1
        elif line.startswith('+'):
            content = line[1:].strip()

            # Ignore Python comments
            if content.startswith('#'):
                current_line_num += 1
                continue

            is_eval = is_dynamic_eval(content)
            is_shell = is_shell_execution(content)

            if is_eval:
                findings.append({
                    "path": path,
                    "line": current_line_num,
                    "rule": "dynamic-eval"
                })
            if is_shell:
                findings.append({
                    "path": path,
                    "line": current_line_num,
                    "rule": "shell-execution"
                })

            # Increment line counter for added lines
            current_line_num += 1

    return json.dumps({"findings": findings, "cpu_seconds": 0})

def main():
    # Read JSON from stdin
    try:
        input_data = sys.stdin.read().strip()
        if not input_data:
            return

        data = json.loads(input_data)
        path = data.get("path")
        patch = data.get("patch")

        if not path or not patch:
            # Malformed input
            return

        result_json = analyze_diff(patch, path)
        print(result_json)

    except json.JSONDecodeError:
        # Error parsing input
        pass
    except Exception:
        # Catch all other errors during execution
        pass

if __name__ == "__main__":
    main()
