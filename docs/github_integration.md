# GitHub Integration — v0 Design Note

## Purpose

The GitHub adapter gives super-bot read/write access to issues so it can:
- Fetch open issues to inject as context into a prompt.
- Create new issues (e.g. auto-generate a task from a model response).
- Add comments to existing issues (e.g. post a model's analysis).

## Authentication

super-bot uses a **Personal Access Token (PAT)** stored in the `GITHUB_TOKEN` environment
variable.  Load it from `.env` (never commit the real token).

Required PAT scopes: `repo` (for private repos) or `public_repo` (for public-only access).

## Adapter API

```python
from superbot.adapters.github import GitHubAdapter

gh = GitHubAdapter(token=os.environ["GITHUB_TOKEN"],
                   default_repo="Thinker-74/super-bot")
```

| Method | Signature | Returns |
|--------|-----------|---------|
| `list_issues` | `(repo=None, state="open")` | `list[dict]` — number, title, state, url, body |
| `get_issue` | `(number, repo=None)` | `dict` — + comments list |
| `create_issue` | `(title, body="", repo=None)` | `dict` — number, title, url |
| `add_comment` | `(issue_number, body, repo=None)` | `dict` — id, url |

All methods accept an optional `repo` slug override; they fall back to `default_repo`.

## Example Flows

### Flow 1 — Summarise open issues

```
User: "summarise all open issues"
  → GitHubAdapter.list_issues()           # fetch open issues
  → build prompt with issue titles/bodies
  → OllamaAdapter.generate(model, prompt) # summarise
  → print summary
```

### Flow 2 — Analyse an issue and post a comment

```
User: "analyse issue #12 and suggest a fix" --repo Thinker-74/super-bot
  → GitHubAdapter.get_issue(12)           # fetch issue + comments
  → build prompt with full issue body
  → OllamaAdapter.generate(model, prompt) # analyse
  → GitHubAdapter.add_comment(12, response)
  → print confirmation
```

### Flow 3 — Create a task issue from a model response

```
User: "generate a refactoring plan for router.py and track it"
  → OllamaAdapter.generate(model, prompt) # generate plan
  → GitHubAdapter.create_issue(title, body=plan)
  → print new issue URL
```

## v0 Limitations

- No file reading (GitHub Contents API) — planned for v1.
- No label or milestone support.
- No pagination handling for repos with > 30 issues (PyGithub default page size).
- PAT only — no GitHub App auth.

## Security Notes

- `GITHUB_TOKEN` must never appear in logs.  The logger (`state/logger.py`) does not
  record environment variables or tokens.
- For write operations (`create_issue`, `add_comment`), the adapter will raise a
  `GithubException` if the token lacks sufficient scope — fail loudly.
