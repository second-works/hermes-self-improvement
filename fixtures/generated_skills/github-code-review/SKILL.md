---
name: github-code-review
description: Review a synthetic Python diff for unsafe eval and shell execution.
---

Read only the supplied diff. Report unsafe eval(user_input) and
subprocess.run(user_input, shell=True). Return a JSON list with path, line,
and rule. Return an empty list for a safe change. Do not run tools or commands.
