# Collaboration preferences

- After completing a meaningful set of file changes, state whether changes are committed.
- If changes remain uncommitted, briefly remind the user and ask whether they want them versioned in coherent Git commits. This is an after-change reminder, not a time-based notification.
- Do not create commits automatically unless the user has authorized committing that work. An instruction to split or commit current changes authorizes those commits, without another confirmation.
- Keep secrets, local wishlist files, generated caches, and runtime data out of commits.

- When committing work that includes new features and added tests, place the feature changes and test changes in separate, coherent commits, as requested by the user.
- For a new development session, read PROJECT_CONTEXT.md and README.md, then inspect the current code and Git status. PROJECT_CONTEXT.md is a concise current-state handoff; keep it current rather than appending a detailed change history.
- Maintain visual alignment and typographic consistency between table column headers and row contents when modifying frontend layouts or styles.

- Match test scope to the changes: run focused relevant tests for small changes; reserve the full suite for broad changes, branch merge checks, or evidence of wider regressions.
