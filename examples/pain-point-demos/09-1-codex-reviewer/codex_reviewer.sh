#!/usr/bin/env bash
set -euo pipefail

# The review adapter runs inside the target repo, where PATH may include
# workspace/.ait/bin. Strip AIT wrappers so Codex acts only as the reviewer
# process and does not accidentally create a nested AIT attempt.
clean_path=""
IFS=":"
for path_entry in $PATH; do
  case "$path_entry" in
    */.ait/bin) continue ;;
  esac
  if [ -z "$clean_path" ]; then
    clean_path="$path_entry"
  else
    clean_path="$clean_path:$path_entry"
  fi
done
unset IFS
export PATH="$clean_path"

prompt='You are Codex acting as an adversarial code reviewer for AIT.

You will receive an AIT reviewer brief on stdin. Review only the target attempt described in the brief.

Return only a JSON object with this schema:
{
  "summary": "short review summary",
  "findings": [
    {
      "severity": "high",
      "blocking": true,
      "path": "one changed file path from the brief",
      "line": 1,
      "hunk_ref": "diff-hunk-1",
      "title": "short actionable title",
      "body": "specific risk grounded in the changed code and evidence",
      "evidence_ref": "diff-hunk-1",
      "suggested_test": "focused test or mitigation",
      "confidence": "medium"
    }
  ]
}

If the implementation adds divide(a, b) without zero-division handling, report a high-severity blocking finding.
If the brief shows no test evidence for the changed behavior, include that in the body or suggested_test.
Do not include markdown fences or prose outside the JSON object.'

codex exec --dangerously-bypass-approvals-and-sandbox "$prompt"
