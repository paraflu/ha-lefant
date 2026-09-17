# v1 implementation addendum

Supersedes only the scope exclusions noted below in the original
`2026-09-16_23-26-51_lefant-m1-home-assistant-integration.md` design.

## Scope reconciliation

Commit `f4f500b` shipped fan speed, locate, cleaning time/area sensors, battery
sensor and spot cleaning despite v1's exclusions. No prior artifact records why
these were added; this is retrospective scope acceptance, not evidence of an
original decision. Retain them to avoid removing existing entity/service APIs.
They are experimental convenience controls/telemetry using the existing LAN
transport, not new cloud functionality or a claim of verified hardware support.

Building (retained): vacuum fan speed/locate/spot, battery/time/area sensors and
raw DP attributes alongside start/pause/stop/return and battery state.
Not Building remains: maps, room/zone selection, schedules, maintenance counters,
cloud authentication, automatic Local Key extraction, and multi-model DP discovery.

## Evidence and coverage

Research Decision Log **M1-DP-1**, issue #1, is authoritative for uncertainty.
DP14 fan speed, DP24 locate, DP18 minutes and DP19 square metres are retained
implementation assumptions, NOT verified M1 capabilities. Spot mode is likewise
unconfirmed. `tests/test_entities.py` exercises actual entity read/write mapping,
invalid fan-speed rejection, telemetry units and absent sensor values using HA
API doubles. `tests/test_state_mapping.py` covers activity mapping. README lists
these capabilities with the experimental warning. Unit tests do not validate HA
runtime compatibility, firmware semantics or the physical robot.

## Command reconciliation contract

Source: this addendum (software robustness policy, not Tuya acknowledgement spec).
An optimistic command must be confirmed by a later STATUS containing matching
values for every pending DP. Unrelated pushes and CONTROL responses do not count.
After 7 seconds without confirmation, warn and query the current connection.
Apply returned device values, discard unconfirmed optimistic values missing from
the reply, and retain the last observed values for those missing keys. Never
re-query a disconnected/replaced client. Stop/disconnect cancels reconciliation.
New commands during a query keep their own pending state and timer. Query failure
rolls back that command's optimism and warns; it does not claim hardware success.
