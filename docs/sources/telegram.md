# Source: Telegram

How Doppelganger parses a **Telegram** export into the normalized message stream
that the [shared pipeline](../data-pipeline.md) consumes. This is the only stage
that knows anything Telegram-specific; everything downstream (sessionizing,
scanning, redaction, ShareGPT formatting) is source-agnostic.

Adapter: [`ingest/adapters/telegram.py`](../../ingest/adapters/telegram.py).
Use it with `--source telegram` (the default).

## Exporting your data

In **Telegram Desktop**: `Settings > Advanced > Export Telegram Data`. Select
your chat(s), choose **JSON** format (not HTML), and export.

The export unzips to a dated folder:

```
DataExport_2025-07-09/
└── result.json        ← this is the file the adapter reads
```

Point the pipeline at it one of two ways:

```bash
# a) move/copy it to the default location
cp DataExport_2025-07-09/result.json data/result.json
python -m ingest --source telegram

# b) or pass the path directly
python -m ingest --source telegram --input DataExport_2025-07-09/result.json
```

> `setup.sh` expects `data/result.json`; it will stop with a "not found" error
> until the file is there.

## What the adapter does

- **Detects who "you" are.** Read from the export's `personal_information`
  (first + last name), or overridden with `--self-name "Your Name"`. If it can't
  be determined, the adapter raises rather than guessing — pass `--self-name`.
  Every message is tagged `sender_is_self` so the shared pipeline knows which
  turns are yours (the ones the model learns to generate).
- **Filters non-messages.** `service` events (pins, joins, calls) and
  empty/invalid entries are skipped.
- **Joins rich-text fragments.** Telegram stores formatted messages as a list of
  entity objects (`text_entities`); the adapter concatenates them back into a
  single plain-text string.
- **Reads reply + group metadata.** `reply_to_message_id` (used downstream to
  stitch reply-linked conversations) and per-sender identity (used for
  `--multi-speaker` group handling) are preserved.

## Output

A flat list of `NormalizedMessage`
([`ingest/message.py`](../../ingest/message.py)):

```python
NormalizedMessage(
    chat_id,         # which chat the message belongs to
    timestamp,       # unix seconds
    sender_id,       # sender display name / id
    sender_is_self,  # True if this is you
    text,            # plain-text content
    message_id,      # for reply resolution
    reply_to_id,     # the message this replies to, if any
)
```

From here the [shared pipeline](../data-pipeline.md) takes over.

## Telegram-relevant flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--source` | `telegram` | Selects this adapter |
| `--input` | `./data/result.json` | Path to the Telegram `result.json` |
| `--self-name` | auto | Override "which sender is you" when auto-detection fails or is wrong |
| `--multi-speaker` | off | In group chats, keep + label each non-self sender (`Bob: ...`) instead of collapsing the other side into one speaker |

All other flags (`--conversation-gap`, `--message-chain`, `--redact`, …) belong
to the shared pipeline — see [data-pipeline.md](../data-pipeline.md).
