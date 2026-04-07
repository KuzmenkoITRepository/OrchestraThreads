# CODE STYLE COOKBOOK FOR AGENTS

This file is the shortest acceptable context for any agent that writes Python in this repo.

Read this before editing code. Follow it before asking for extra context. The goal is simple: write code that passes `ruff`, `wemake-python-styleguide`, and `mypy --strict` on the first try.

Primary external source: `https://wemake-python-styleguide.readthedocs.io/llms.txt`

Secondary source for this cookbook: OpenCode session history via `opencode-sessions`, using real agent failures across the `OrchestraThreads*` worktrees.

## Most common agent mistakes in this repo family

This guide is tuned to the errors agents actually repeat most often here.

Top repeated failures from session history:

1. `WPS221` — line with high Jones Complexity
2. `WPS202` — too many module members
3. `WPS300` — local folder import
4. `WPS414` — incorrect unpacking target
5. `WPS229` — `try` body too long
6. `WPS214` — too many methods on a class
7. `WPS210` — too many local variables
8. `WPS231` — too much cognitive complexity
9. `WPS201` — too many imports in a module
10. `WPS211` — too many arguments

Main pattern behind these failures:

**Agents try to finish too much inside one file, one class, one function, one line, or one `try` block.**

## Non-negotiable rules

- Never bypass linters or type checks.
- Never use `# noqa` without a specific rule code and inline justification.
- Never use `# type: ignore` without a specific reason.
- Never use `--no-verify`.
- Never change lint thresholds to make your code pass.
- Fix root causes by simplifying code.

## Repo reality

- Format/lint/typecheck pipeline:
  - `make format`
  - `make lint`
  - `make typecheck`
  - `make check`
- Line length: `100`
- Python: `3.11`
- `mypy --strict` is mandatory.
- `flake8` complexity threshold in this repo: `max-complexity = 10`
- Existing repo guidance already forbids suppression-first fixes. This file explains how to avoid needing them.

## Default coding shape

When writing a new function, target this shape by default:

- 1 responsibility
- 0-2 loops
- 0-3 condition branches
- 0-5 local variables
- 0-5 parameters
- shallow nesting
- early returns for invalid cases
- typed inputs and typed outputs

If your draft exceeds this shape, split it before you finish writing it.

## Pre-flight against the most common failures

Before you finish a file, check these in order:

1. Is this file turning into a god module with too many imports or top-level members?
2. Is this class absorbing too many responsibilities?
3. Does any function have too many locals, branches, or arguments?
4. Did any line become too dense because I compressed too much logic into one expression?
5. Did I wrap too much code inside one `try` block?
6. Did I use package-correct imports for sibling modules?
7. Did I introduce clever unpacking instead of explicit variable access?

## Complexity cookbook

### 1. Keep functions small enough to reason about

Use phases, not monoliths.

Preferred split:

1. validate inputs
2. transform data
3. persist / send / return

Bad:

```python
def handle_event(event: Event, store: Store, sender: Sender) -> Result:
    # validation + branching + transformation + persistence + response building
    ...
```

Good:

```python
def handle_event(event: Event, store: Store, sender: Sender) -> Result:
    _validate_event(event)
    payload = _build_payload(event)
    saved = store.save(payload)
    return _build_result(saved, sender)
```

This is the primary defense against `WPS210`, `WPS211`, and `WPS231`.

### 2. Prefer guard clauses over nested `if`

Deep nesting is the fastest path to WPS complexity violations.

Bad:

```python
def process(job: Job) -> None:
    if job.enabled:
        if job.payload:
            if job.payload.is_valid():
                run_job(job)
```

Good:

```python
def process(job: Job) -> None:
    if not job.enabled:
        return
    if not job.payload:
        return
    if not job.payload.is_valid():
        return
    run_job(job)
```

Rule of thumb: if you are about to indent for the third time, extract or return early.

This is also one of the easiest ways to prevent `WPS221`.

### 3. Treat local-variable count as a design signal

WSP penalizes too many locals because too many named intermediates usually means too many responsibilities.

If locals start piling up:

- extract a helper
- group related values into a `dataclass` or `TypedDict`
- replace step-by-step accumulation with one typed object
- compute close to use
- return values directly instead of storing everything in temporary variables

Bad:

```python
def build_agent_state(raw: RawState) -> AgentState:
    user_id = raw.user_id
    thread_id = raw.thread_id
    status = _normalize_status(raw.status)
    retries = _normalize_retries(raw.retries)
    updated_at = _normalize_time(raw.updated_at)
    metadata = _build_metadata(raw)
    return AgentState(
        user_id=user_id,
        thread_id=thread_id,
        status=status,
        retries=retries,
        updated_at=updated_at,
        metadata=metadata,
    )
```

Good:

```python
def build_agent_state(raw: RawState) -> AgentState:
    return AgentState(
        user_id=raw.user_id,
        thread_id=raw.thread_id,
        status=_normalize_status(raw.status),
        retries=_normalize_retries(raw.retries),
        updated_at=_normalize_time(raw.updated_at),
        metadata=_build_metadata(raw),
    )
```

If you need many local names just to assemble one result, split the phases or build the result inline.

### 4. Keep loop count low

Multiple loops in one function often mean hidden subroutines.

Prefer:

- one loop per function
- comprehensions for simple mapping/filtering
- helper generators for multi-step iteration
- dispatch tables instead of loop + branching chains

Bad:

```python
def collect_active_threads(groups: list[Group]) -> list[str]:
    result = []
    for group in groups:
        for thread in group.threads:
            if thread.is_active:
                result.append(thread.thread_id)
    return result
```

Good:

```python
def collect_active_threads(groups: list[Group]) -> list[str]:
    return [
        thread.thread_id
        for group in groups
        for thread in group.threads
        if thread.is_active
    ]
```

But do not force giant comprehensions. If the comprehension becomes hard to read, extract a helper.

This matters because agents often “fix” loops by writing one dense line and then hit `WPS221` instead.

### 5. Keep branch count low

If a function has many `if`/`elif` branches:

- use `match`
- use a dispatch map
- split per case into helpers
- move validation rules into dedicated predicates

Bad:

```python
def route_event(kind: str, event: Event) -> Result:
    if kind == "created":
        return _handle_created(event)
    if kind == "updated":
        return _handle_updated(event)
    if kind == "deleted":
        return _handle_deleted(event)
    if kind == "archived":
        return _handle_archived(event)
    raise ValueError(kind)
```

Better:

```python
HANDLERS: dict[str, EventHandler] = {
    "created": _handle_created,
    "updated": _handle_updated,
    "deleted": _handle_deleted,
    "archived": _handle_archived,
}


def route_event(kind: str, event: Event) -> Result:
    try:
        handler = HANDLERS[kind]
    except KeyError as error:
        raise ValueError(kind) from error
    return handler(event)
```

Dispatch maps reduce branching and help avoid `WPS221` on branch-heavy lines.

### 6. Reduce parameter count with typed objects

If a function wants many parameters, the API is usually wrong.

Prefer:

- `dataclass` for cohesive runtime data
- `TypedDict` for structured mappings
- small value objects for repeated parameter groups

Bad:

```python
def create_thread(
    user_id: str,
    account_id: str,
    title: str,
    priority: int,
    tags: list[str],
    created_at: datetime,
) -> Thread:
    ...
```

Good:

```python
@dataclass(frozen=True)
class ThreadDraft:
    user_id: str
    account_id: str
    title: str
    priority: int
    tags: list[str]
    created_at: datetime


def create_thread(draft: ThreadDraft) -> Thread:
    ...
```

This is the default fix for `WPS211`.

### 7. Keep helpers purposeful

Allowed split:

- `_validate_*`
- `_build_*`
- `_load_*`
- `_serialize_*`
- `_parse_*`
- `_select_*`

Avoid catch-all names like:

- `utils.py`
- `helpers.py`
- `misc.py`
- `common.py`

Each extracted unit must have one operational purpose.

### 8. Keep modules small and purposeful

Real session history shows repeated agent failures on `WPS201` and `WPS202`.

Default module shape:

- one coherent responsibility
- limited imports
- limited top-level members
- one public theme per file

When a file starts pulling imports from many unrelated subsystems, stop and split it.

Typical safe splits:

- runtime orchestration vs config parsing
- HTTP/API calls vs response parsing
- dataclasses/types vs business logic
- process launch vs status formatting

Bad module smell:

- constants + types + parsing + IO + orchestration in one file
- many top-level helpers because they are “sort of related”
- imports from every nearby sibling module

Do not create `utils.py` as an escape hatch. Split by operational role.

### 9. Keep classes thin

Real session history shows repeated `WPS214` failures from overgrown runtime classes.

Default rule:

- if one class owns config, process launch, parsing, retries, status formatting, cleanup, and validation, it is too big

Prefer:

- thin orchestrator class
- helper modules for stateless logic
- separate collaborators for separate behaviors

Class smell:

- 8+ methods
- many private helpers that do unrelated work
- one class acting as runtime, parser, config manager, and serializer at the same time

### 10. Keep `try` blocks tiny

Real session history shows repeated `WPS229` failures and related `WPS501` mistakes.

Rule:

- `try` should wrap only the one operation expected to fail
- move preparation above `try`
- move post-processing after `try`
- do not mix unrelated work inside one `try`

Bad:

```python
def load_config(path: Path) -> Config:
    try:
        raw_text = path.read_text()
        parsed = json.loads(raw_text)
        return build_config(parsed)
    except OSError as error:
        raise ConfigError(path) from error
```

Good:

```python
def load_config(path: Path) -> Config:
    try:
        raw_text = path.read_text()
    except OSError as error:
        raise ConfigError(path) from error
    parsed = json.loads(raw_text)
    return build_config(parsed)
```

### 11. Keep lines simple, not clever

`WPS221` was the most repeated real failure in session history.

Agents trigger it with:

- long boolean chains
- nested inline conditions
- giant comprehensions with multiple transformations
- dense chained calls with fallback logic
- one-line parsing pipelines with too many operators

Fix it by splitting the decision, not by suppressing the warning.

Bad:

```python
is_ready = item and item.enabled and item.payload and item.payload.status in READY_STATES and not item.is_expired(now)
```

Good:

```python
def _has_ready_payload(item: Item, now: datetime) -> bool:
    return bool(
        item.payload
        and item.payload.status in READY_STATES
        and not item.is_expired(now)
    )


def is_ready(item: Item | None, now: datetime) -> bool:
    return bool(item and item.enabled and _has_ready_payload(item, now))
```

### 12. Use package-correct imports

`WPS300` appeared repeatedly in agent-written runtime/template code.

Rules:

- use the import style already used by the package
- prefer the package-correct sibling import form instead of ad hoc local-folder imports
- do not centralize imports “for convenience” if that bloats the module

If imports keep growing, split the file instead of adding more imports.

### 13. Avoid clever unpacking

`WPS414` showed up repeatedly in generated code.

Rules:

- unpack only when the structure is obvious
- avoid placeholder-heavy unpacking
- if you need one field, access one field
- favor explicit names over compact tuple tricks

Prefer direct field access over destructuring that hides intent.

### 14. Type for strict mypy from the start

Always:

- annotate every function
- annotate return types explicitly
- prefer `X | None` over implicit optional behavior
- use `TypedDict` instead of `dict[str, Any]`
- use type aliases for repeated complex shapes
- keep container types concrete

Bad:

```python
def make_payload(data):
    return {"id": data.id, "meta": data.meta}
```

Good:

```python
class Payload(TypedDict):
    id: str
    meta: Metadata


def make_payload(data: EventData) -> Payload:
    return {"id": data.id, "meta": data.meta}
```

### 15. Prefer explicit constants over magic numbers

Bad:

```python
if retries > 3:
    ...
```

Good:

```python
MAX_RETRIES = 3


if retries > MAX_RETRIES:
    ...
```

### 16. Edit implementation files, not facades

In this repo, facade files often re-export real implementations. Do not add complexity to the facade if the real logic belongs in `*_impl.py` or `*_runtime.py`.

## Fast pre-flight checklist for agents

Before you finish a change, ask:

1. Did I keep each function to one job?
2. Can I remove one more level of nesting with a guard clause?
3. Do I have too many local variables because I am mixing phases?
4. Can one loop become a comprehension or a helper?
5. Did I bundle repeated arguments into a typed object?
6. Did I keep the module small enough to avoid `WPS201` and `WPS202`?
7. Did I keep classes small enough to avoid `WPS214`?
8. Did I keep `try` blocks to one risky call?
9. Did I avoid `Any`, blanket `noqa`, and blanket ignores?
10. Did I preserve existing module boundaries instead of creating a dumping ground?

If any answer is “no”, refactor before running checks.

## Minimal authoring workflow

1. Read `AGENTS.md` and this file.
2. Find an existing nearby pattern.
3. Write the smallest typed implementation.
4. Split early when imports, members, methods, locals, loops, or branches start to grow.
5. Run `make format`.
6. Run `make lint`.
7. Run `make typecheck`.
8. Run targeted tests if behavior changed.

## Copy-paste prompt for subagents

Use this block when delegating Python code changes to a subagent.

```text
Before writing code, read `AGENTS.md` and `CODE-STYLE.md`.

Your goal is to produce code that passes `ruff`, `wemake-python-styleguide`, and `mypy --strict` on the first try.

Hard rules:
- do not bypass linters or hooks
- do not use blanket `# noqa`
- do not use `# type: ignore` without explicit justification
- do not change lint thresholds or config to make code pass
- fix root causes by simplifying code

Code shape requirements:
- keep modules small and single-purpose
- keep classes thin
- keep functions small and single-purpose
- split early when imports, module members, methods, locals, loops, branches, or nesting start to grow
- use guard clauses instead of deep nesting
- keep `try` blocks tiny: wrap only the risky operation
- use typed objects (`dataclass`, `TypedDict`) instead of long argument lists or loose dicts
- use package-correct imports for sibling modules
- avoid clever unpacking and dense one-line logic

Common failures to avoid explicitly:
- `WPS221` high Jones Complexity
- `WPS202` too many module members
- `WPS300` local folder import
- `WPS414` incorrect unpacking target
- `WPS229` try body too long
- `WPS214` too many methods
- `WPS210` too many local variables
- `WPS231` too much cognitive complexity
- `WPS201` too many imports
- `WPS211` too many arguments

Preferred implementation strategy:
1. Match existing nearby patterns.
2. Write the smallest typed version first.
3. If a file grows, split by operational role, not into generic helpers.
4. If a class grows, move stateless logic into helper modules.
5. If a function grows, split by phase: validate -> transform -> persist/return.
6. If a line gets dense, split the decision into helpers.

Do not create `utils.py` / `helpers.py` dumping grounds.
Do not hide problems with suppressions.
If the code is only valid after a bypass, it is not done.
```

## One-line policy

If code only passes after suppression, threshold changes, or hook bypasses, it is not done.
