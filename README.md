# Doppelganger – Fine-Tune Models on Your Chat History

**Doppelganger** lets you fine-tune large language models (LLMs) like Qwen on your own chat
conversations. Built on top of [LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory), it
formats your data into the ShareGPT format for supervised fine-tuning (SFT).

Ingestion is **source-agnostic**: a small adapter parses each platform's export into a normalized
message stream, and the rest of the pipeline (sessionizing, turn-merging, optional quality
validation, ShareGPT formatting) is shared. **Telegram** is supported today; other sources
(WhatsApp, etc.) are planned and slot in as drop-in adapters — see [issue #9](https://github.com/NotYuSheng/Doppelganger/issues/9).

## Purpose

Fine-tuning on chat data can capture aspects of your text style, including:

* Writing tone, vocabulary, and phrasing
* Typical response lengths and structure
* Repeated expressions or idioms
* Conversational flow and habits

However, this method **won’t replicate your deeper beliefs, private memories, or behavior outside the chat**. It reflects how you write — not necessarily how you think.

For stronger emulation, consider incorporating:

* Additional sources like emails or forum posts
* Clear prompt instructions during inference
* Domain-specific datasets (e.g., technical messages, inside jokes)

## Warning: Risk of Sensitive Data Exposure

Fine-tuning on real chat history may unintentionally encode:

* Personal identifiers (names, locations, contact info)
* Confidential conversations
* Sensitive or offensive content

> **Always review and sanitize your exported dataset (`result.json`) before training.**
> You are responsible for ensuring compliance with privacy laws and personal data protection.

### Keeping your data out of git

Your chat export and any generated datasets are ignored by `.gitignore`
(`result.json`, `*.json`, `*.jsonl`, `DataExport*/`, `*.session`, `.env`, plus Telegram
media/contacts such as `*.vcard`, `*.tgs`, `*.webp`, `*.ogg`/`*.oga`). Generic
media (`.jpg`, `.mp4`, …) lives inside `DataExport*/`, which is ignored
wholesale. As an extra safeguard, a pre-commit hook refuses to commit these
files even if they are force-added. Enable it once per clone:

```bash
git config core.hooksPath hooks
```

To deliberately commit a blocked file, bypass the hook with `git commit --no-verify`.

## Requirements

* **Python 3.11–3.13** (required by LLaMA-Factory 0.9.4)
* A CUDA-capable GPU for training, with a matching [PyTorch build](https://pytorch.org/get-started/locally/)
* `git`

## Export Your Telegram Chat

1. Open **Telegram Desktop**.
2. Go to: `Settings > Advanced > Export Telegram Data`.
3. Select your personal chat or group to export.
4. Ensure **JSON** format is selected (not HTML).
5. Place the exported `result.json` file into:

```
Doppelganger/
├── data/
│   └── result.json  ← Place here
```

## Setup

The setup scripts create a virtual environment, install pinned dependencies
(LLaMA-Factory **0.9.4**), and process your export into `data/chat_sharegpt.json`.

**Linux / macOS:**

```bash
./setup.sh
```

**Windows** (from **Command Prompt**, not PowerShell):

```cmd
setup.bat
```

Prefer to do it manually? The scripts are thin wrappers around:

```bash
python -m venv venv
# activate: source venv/bin/activate   (Windows: venv\Scripts\activate)
pip install -r requirements.txt
python -m ingest --source telegram
```

### Ingestion options

`python -m ingest` turns a raw export into a dataset. Useful flags:

| Flag                  | Default                   | Description                                            |
| --------------------- | ------------------------- | ------------------------------------------------------ |
| `--source`            | `telegram`                | Chat source to parse (more planned)                    |
| `--input`             | `./data/result.json`      | Path to the raw export                                 |
| `--format`            | `sharegpt`                | `sharegpt` (for training) or `jsonl` (intermediate)    |
| `--self-name`         | auto-detected             | Override which sender is "you"                         |
| `--conversation-gap`  | `3600`                    | Seconds of silence that start a new conversation       |
| `--message-chain`     | `30`                      | Max seconds between same-sender messages to merge      |

### Optional: LLM quality validation

Each extracted conversation can be scored for coherence and quality, dropping weak samples before
training. It is enabled automatically when `ANTHROPIC_API_KEY` is set. Copy `.env.example` to `.env`
and fill it in (the setup scripts do this for you):

```dotenv
DIALOGSMITH_LLM_VALIDATE=true
DIALOGSMITH_LLM_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_API_KEY=your_api_key_here
```

Set `DIALOGSMITH_LLM_VALIDATE=false` to skip validation entirely (no API calls).

## Fine-Tune Your Model (LoRA)

Training is configured by [`configs/train_lora.yaml`](configs/train_lora.yaml), which defaults to
**Qwen1.5-1.8B-Chat** and the `chat_sharegpt` dataset registered in
[`configs/dataset_info.json`](configs/dataset_info.json). Activate your venv, then run:

```bash
llamafactory-cli train configs/train_lora.yaml
```

### Customize for your model

Edit `configs/train_lora.yaml`:

| Field                  | Description                                              |
| ---------------------- | -------------------------------------------------------- |
| `model_name_or_path`   | Hugging Face model ID or local model path                |
| `template`             | Prompt template type (e.g., `qwen`, `chatml`, `default`) |
| `lora_target`          | LoRA target modules (`all` works across architectures)   |
| `output_dir`           | Destination to save the LoRA checkpoints                 |

For example, to use `mistralai/Mistral-7B-Instruct-v0.2`, set `model_name_or_path` accordingly and
`template: chatml`. Refer to the
[LLaMA-Factory model table](https://github.com/hiyouga/LLaMA-Factory#supported-models) for recommended values.

### Resume training

Uncomment and point `resume_from_checkpoint` in `configs/train_lora.yaml` at your latest checkpoint:

```yaml
resume_from_checkpoint: saves/Qwen1.5-1.8B-Chat-lora/checkpoint-400
```

### Merge the LoRA adapter with the base model

Edit [`configs/export_lora.yaml`](configs/export_lora.yaml) to match your model, then run:

```bash
llamafactory-cli export configs/export_lora.yaml
```

### Chat with your fine-tuned model

```bash
llamafactory-cli chat \
  --model_name_or_path merged/Qwen1.5-1.8B-Chat-merged \
  --template qwen
```

Update `--template` to match the one used during training.

## Activating the environment later

After running setup once, reactivate the venv in future sessions before running any commands:

```bash
source venv/bin/activate          # Linux / macOS
venv\Scripts\activate             # Windows (Command Prompt)
```

## Running the tests

The ingestion pipeline (parsing, sessionizing, turn-merging, ShareGPT formatting) is covered by a
fast unit suite — no GPU, network, or API key required:

```bash
python -m unittest discover -s tests -t .
```

It runs in well under a second and locks in the conversion behaviour, so you can verify a change
without running the full pipeline.

## Legacy workflow

The pre-refactor, Windows-only workflow (which cloned LLaMA-Factory at HEAD) is preserved at the
[`v0.1.0`](https://github.com/NotYuSheng/Doppelganger/releases/tag/v0.1.0) tag. The old
`scripts/telegram_extract.py` and `scripts/convert_to_sharegpt.py` still work as thin deprecated
wrappers around `python -m ingest`, but will be removed in a future release.
