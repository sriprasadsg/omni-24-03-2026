# reviewer

**STATUS: FAILED**

Exit code: 1

## stdout
Autocompact is thrashing: the context refilled to the limit within 3 turns of the previous compact, 3 times in a row. A file being read or a tool output is likely too large for the context window. Try reading in smaller chunks, or use /clear to start fresh.

## stderr
Permission allow rule (../.claude/settings.json): Write(.planning/*) is not matched by file permission checks — only Edit(path) rules are. Use Edit(.planning/*) instead (Edit rules cover all file-editing tools).
Permission allow rule (../.claude/settings.json): Write(STATE.md) is not matched by file permission checks — only Edit(path) rules are. Use Edit(STATE.md) instead (Edit rules cover all file-editing tools).
