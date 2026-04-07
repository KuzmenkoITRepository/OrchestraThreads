# Context memory

The backend keeps an in-memory rolling context buffer.

Each stored entry contains the thread id, entry type, compact text, optional metadata summary, and an event id.

Context memory is injected into prompt construction through the `Recent context:` system block.
