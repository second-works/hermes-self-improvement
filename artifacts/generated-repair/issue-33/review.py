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

def invalid_input():
    print('{"error":"INVALID_INPUT"}')
    return 2


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("non-JSON constant")


def main():
    try:
        raw = sys.stdin.buffer.read(16385)
        if len(raw) > 16384:
            return invalid_input()
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                          parse_constant=reject_constant)
        if not isinstance(data, dict) or set(data) != {"path", "patch"}:
            return invalid_input()
        path, patch = data["path"], data["patch"]
        if (not isinstance(path, str)
                or re.fullmatch(r"case_[a-z0-9]{8,32}\.py", path) is None
                or not isinstance(patch, str) or not patch):
            return invalid_input()
    except (ValueError, UnicodeError, RecursionError):
        return invalid_input()
    print(analyze_diff(patch, path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
