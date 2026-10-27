# AGENTS.md

Working notes for AI assistants and humans contributing to this repository.

## Language

- **Pull request and merge request descriptions: English.** Title and body.
- **Commit messages: English.** Conventional Commits (`feat:`, `fix:`, `docs:`,
  `chore:`, `test:`, `refactor:`, `ci:`), imperative mood, subject under ~72
  characters. Add a body when the *why* is not obvious from the diff.
- **Code, comments, docstrings and user-facing strings: English.** This includes
  `strings.json` and anything an end user sees in Home Assistant.
- **Conversation with the maintainer: Italian is fine.** That does not extend to
  anything written into the repository or into GitHub.

## Before pushing

```bash
python3 -m pytest tests/ -q      # 36 tests, all offline, no robot needed
```

Tests use minimal Home Assistant doubles in `tests/conftest.py`. Do not import a
real Home Assistant runtime to make a test pass: extend the doubles instead.

## Repository rules

- **Never commit secrets or device identifiers.** The Tuya local key, full device
  IDs, MAC addresses and IP addresses stay out of code, docs, tests, commit
  messages, PR bodies and screenshots. `.env`, `.env.*`, `*.swp`, `*.apk` and
  `*.xapk` are ignored — keep it that way.
- Mask device IDs in tool output (`bf23...esv5`), never print the local key.
- Do not commit the app XAPK or anything extracted from it.
- Do not merge a PR while CI is red. `pytest` and `hacs` must both pass.
- Merge style: merge commit (`gh pr merge --merge`), branch deleted after merge.

## Domain facts worth not re-deriving

- The Lefant M1 answers **Tuya LAN 3.3** (`55AA` framing, AES-ECB with the local
  key). It is *not* 3.5. `pytuya_client.py` speaks only 3.5 and is deprecated;
  the integration runs on `tuya_lan_adapter.py` (tinytuya).
- `iot_class` is `local_polling`: tinytuya is request/response, there is no push
  channel to listen on.
- Datapoint IDs in `const.py` are corroborated by the APK's `LaserDP` catalog and
  by `DP_QUERY` answers from physical units. Sensor `unique_id`s deliberately keep
  the ids the integration shipped with, so a DP correction does not recreate
  entities and lose history.
- **Commands (start, pause, dock, fan speed, locate, spot) are not validated on
  hardware.** Telemetry is. Do not describe the write path as working.
- The cleaning status enum is only partly observed: do not invent aliases. An
  unknown status falls back to `idle` on purpose.

## Adding hardware evidence

When a real device observation changes a mapping, the commit should say what was
observed, on which firmware, and how. `tools/probe_robot.py --dump-json` and
`--watch` are the tools; they read the key from `LEFANT_LOCAL_KEY` and never print
it.

## Artifacts

Research, design and solution documents live under `.rpiv/artifacts/`. They are
append-only history: add dated sections rather than rewriting past conclusions.
