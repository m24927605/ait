# Quickstart: Reconcile Local Artifacts

## Scenario 1: Ignored local env file is not silently lost

1. Create a repo whose `.gitignore` ignores `.env.local`.
2. Create an AIT intent and attempt.
3. In the attempt worktree, create and commit `app.py`.
4. In the attempt worktree, create `.env.local`.
5. Run `ait attempt land <attempt-id> --to feature/local-artifact`.
6. Confirm AIT reports `.env.local` in `local_artifacts`.
7. Confirm the attempt worktree is retained if `.env.local` is pending.

## Scenario 2: Generated directories are skipped

1. In an attempt worktree, create `.venv/` and `node_modules/`.
2. Commit a tracked file.
3. Run land.
4. Confirm generated directories are not copied back to the original repo.

## Scenario 3: Safe editor settings can be copied

1. In an attempt worktree, create `.vscode/settings.json` with non-secret text.
2. Commit a tracked file.
3. Run land.
4. Confirm `.vscode/settings.json` is copied when the original repo has no
   conflicting destination.

## Scenario 4: Destination conflict blocks overwrite

1. Create `.vscode/settings.json` in the original repo with different content.
2. Create a different `.vscode/settings.json` in the attempt worktree.
3. Commit a tracked file and run land.
4. Confirm AIT does not overwrite the original file and retains the worktree.
