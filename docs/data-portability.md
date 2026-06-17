# Data Portability

Ze lets you export all your personal data, restore it to another instance, and
permanently delete everything. All three operations are in **Settings → Your data**.

---

## Export

Click **Export your data**. Ze downloads a ZIP archive named
`ze-export-<timestamp>.zip` to your browser.

The archive contains one JSON file per data domain — memories, goals, contacts,
messages, reminders, costs, and more. A `manifest.json` at the root records the
export timestamp and the schema revision set, which is used to validate the archive
at import time.

Nothing is omitted or summarised. Every stored row is included verbatim.

---

## Import

Import restores a previously exported archive into a Ze instance.

**Two requirements must be satisfied before an import will succeed:**

1. **Schema match** — the archive's `manifest.json` must list the same Alembic
   revision set as the target instance. If the archive was exported from a different
   Ze version, the import will be rejected with a clear error. To fix a mismatch:
   - If the archive is older: upgrade the source Ze instance, re-export, then import.
   - If the archive is newer: upgrade the target Ze instance (`make migrate`), then retry.

2. **Empty instance** — the target Ze instance must hold no user data. If any domain
   table has existing rows, the import is rejected. Delete all data first (see below),
   then import.

To import:

1. Click **Import data** and select your `.zip` export file.
2. Ze validates the archive, then restores all importable domains inside a single
   transaction. If anything fails, the transaction is rolled back and the instance is
   left untouched.
3. On success, Ze reports how many domains and rows were restored.

### What is not imported

LangGraph checkpoint blobs are exported for completeness but are not re-inserted on
import. A restored instance starts with no in-flight conversation graphs — this is the
correct state after a restore.

---

## Delete all data

Permanently erases every row Ze holds across all domains. This resets Ze to a
completely blank state.

**This cannot be undone.** Export your data first if you want a copy.

To delete:

1. Click **Delete all data**.
2. A modal lists exactly what will be erased.
3. Click **Export your data first** inside the modal if you want a copy before proceeding.
4. Type `DELETE` (case-sensitive) in the confirmation field.
5. Click **Delete everything**.

On success, Ze clears its local configuration and reloads to the setup screen.

---

## Typical workflows

### Moving Ze to a new server

1. On the old instance: **Export your data**.
2. Spin up and migrate the new instance (`make migrate`).
3. On the new instance: **Import data**, select the archive.
4. Verify the data looks correct.
5. Optionally: **Delete all data** on the old instance, then shut it down.

### Wiping and starting fresh

1. Optionally: **Export your data** if you want a backup.
2. **Delete all data**.
3. Ze resets to the onboarding screen.

### Restoring from a backup

1. Ensure the running instance is at the same schema version as the archive
   (`make migrate` if needed).
2. If the instance already has data: **Delete all data** first.
3. **Import data**, select the archive.

---

## Archive format reference

```
ze-export-<ISO8601>.zip
├── manifest.json          # { exported_at, schema_revisions, domains }
├── memory.facts.json      # list of row objects
├── memory.episodes.json
├── contacts.persons.json
├── goals.goals.json
├── ...
└── graph.checkpoints.json # exported but not imported
```

- All timestamps are ISO 8601 strings (UTC).
- Float array columns (embedding vectors) are JSON arrays of numbers.
- `BYTEA` columns are base64-encoded strings.
- Column names are raw database column names (snake_case).
