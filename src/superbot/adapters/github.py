"""GitHub adapter — read/create issues and add comments via PyGithub."""
from __future__ import annotations

from github import Github, GithubException


class GitHubAdapter:
    """Wrapper around PyGithub for super-bot's GitHub operations.

    Args:
        token: GitHub Personal Access Token (PAT).
        default_repo: Fallback repo slug (e.g. ``Thinker-74/super-bot``).
    """

    def __init__(self, token: str, default_repo: str) -> None:
        self._client = Github(token)
        self._default_repo = default_repo

    def _repo(self, repo: str | None):
        return self._client.get_repo(repo or self._default_repo)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def list_issues(self, repo: str | None = None, state: str = "open") -> list[dict]:
        """Return a list of issues as plain dicts.

        Args:
            repo: Repo slug override.  Uses default_repo if *None*.
            state: ``"open"``, ``"closed"``, or ``"all"``.
        """
        issues = self._repo(repo).get_issues(state=state)
        return [
            {
                "number": i.number,
                "title": i.title,
                "state": i.state,
                "url": i.html_url,
                "body": i.body,
            }
            for i in issues
        ]

    def get_issue(self, number: int, repo: str | None = None) -> dict:
        """Fetch a single issue by number.

        Returns:
            Dict with ``number``, ``title``, ``state``, ``url``, ``body``,
            ``comments``.
        """
        issue = self._repo(repo).get_issue(number)
        comments = [
            {"author": c.user.login, "body": c.body}
            for c in issue.get_comments()
        ]
        return {
            "number": issue.number,
            "title": issue.title,
            "state": issue.state,
            "url": issue.html_url,
            "body": issue.body,
            "comments": comments,
        }

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def create_issue(
        self,
        title: str,
        body: str = "",
        repo: str | None = None,
    ) -> dict:
        """Create a new issue.

        Returns:
            Dict with ``number``, ``title``, ``url``.
        """
        issue = self._repo(repo).create_issue(title=title, body=body)
        return {"number": issue.number, "title": issue.title, "url": issue.html_url}

    def add_comment(
        self,
        issue_number: int,
        body: str,
        repo: str | None = None,
    ) -> dict:
        """Add a comment to an existing issue.

        Returns:
            Dict with ``id`` and ``url`` of the new comment.
        """
        issue = self._repo(repo).get_issue(issue_number)
        comment = issue.create_comment(body)
        return {"id": comment.id, "url": comment.html_url}
