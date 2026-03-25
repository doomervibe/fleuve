# Fleuve built-in events (quick reference)

Domain workflows use a union of domain events **E** plus optional built-in types. The framework handles many of these in `Workflow._evolve_system` before `_evolve`.

| Event type | Typical emitter | Role |
|------------|-----------------|------|
| `EvSubscriptionAdded` / `EvSubscriptionRemoved` | Workflow `decide` | Cross-workflow subscription (`Sub`); updates state + DB |
| `EvExternalSubscriptionAdded` / `EvExternalSubscriptionRemoved` | Workflow `decide` | NATS topic subscription (`ExternalSub`) |
| `EvScheduleAdded` / `EvScheduleRemoved` | Workflow `decide` | Cron schedule row in state + `delay_schedule` |
| `EvDelay` (with `cron_expression`) | Workflow `decide` | Recurring schedule via `_evolve_system` → `Schedule` in state |
| `EvCancelSchedule` | Workflow `decide` | Remove schedule by `delay_id` |
| `EvDelayComplete` | System (`DelayScheduler`) | Fires stored `next_cmd` when delay elapses |
| `EvDirectMessage` | Domain / routing | Targeted message to another workflow |
| `EvActionCancel` | Workflow `decide` | Cancel in-flight actions |
| `EvSystemPause` / `EvSystemResume` / `EvSystemCancel` | External/API | Lifecycle |
| `EvContinueAsNew` | System / migration | Truncate event log; optional new workflow type |

**User land:** Implement `_evolve` for domain events only; rely on `_evolve_system` for the rows above unless you are debugging framework behavior.

When adding or renaming event types, grep `fleuve/model.py` and tests for existing patterns before inventing new shapes.
