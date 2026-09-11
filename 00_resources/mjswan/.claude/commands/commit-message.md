---
allowed-tools: Bash(git status:*), Bash(git diff:*)
description: Suggest a clear and simple commit message for the current changes
---

## Context

- Current git status: !`git status`
- Current git diff (staged and unstaged changes, excluding lockfiles): !`git diff HEAD -- ':!package-lock.json' ':!uv.lock'`

## Your task

Based on the above changes, output a concise and descriptive commit message following these rules:

1. Use the imperative mood (e.g. "Add", "Fix", "Update", "Remove")
2. Keep the subject line under 72 characters
3. Write in English
4. Avoid vague words like "change", "update files", or "fix stuff"
5. **Default to a single subject line.** Only add a body if the changes are genuinely large and span multiple unrelated concerns that cannot be summarized in one line.
6. If a body is needed, separate it from the subject with a blank line and use short bullet points.

Output only the commit message itself — no explanations, no extra text.

**Do NOT run `git commit` or any other write operation. Only read and suggest.**
