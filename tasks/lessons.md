# MusicOrg Lessons Learned

**Purpose:** Capture patterns from corrections and mistakes to prevent recurrence.

---

## Session: 2026-02-28 — Improvement Research

### Lessons

*(No corrections yet — initial research phase)*

---

## Format for New Lessons

```markdown
### [Date] — [Brief Description]

**What happened:**
[Description of the mistake or correction]

**Root cause:**
[Why it happened]

**Rule to prevent recurrence:**
[Actionable rule or checklist item]

**Related files:**
[File paths or patterns]
```

---

## Active Rules

1. **Plan before implementing** — Any task with 3+ steps requires a written plan
2. **Verify before marking complete** — Run tests, check logs, demonstrate correctness
3. **Use subagents for research** — Keep main context clean for implementation
4. **Stop and re-plan when things go sideways** — Don't push through errors
5. **Demand elegance for non-trivial changes** — Ask "is there a better way?"

---

## Project-Specific Patterns

### MusicOrg Architecture
- Worker pattern uses `moveToThread()` with signal/slot cleanup
- Panels communicate via direct signal connections (no event bus)
- Settings managed via QSettings wrapper in `config/settings.py`
- Theme framework uses plugin loading with validation/sandboxing

### Common Gotchas
- Signal disconnection can raise `RuntimeError` — wrap in try/except
- SQLite with `check_same_thread=False` needs explicit locking for writes
- Path format strings need validation to prevent traversal
- Network calls need explicit timeouts
