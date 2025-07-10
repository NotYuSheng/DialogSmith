# DialogSmith – Fine-Tune Models on Your Telegram History

**DialogSmith** lets you fine-tune large language models (LLMs) like Qwen on your own Telegram conversations.
Built on top of [LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory), it automatically formats data into the ShareGPT format for supervised fine-tuning (SFT).

---

## Export Telegram Chat

1. Open **Telegram Desktop**.
2. Go to: `Settings > Advanced > Export Telegram Data`.
3. Select your personal chat or group to export.
4. Ensure **JSON** format is selected (not HTML).
5. Place the exported `result.json` file into:

```
DialogSmith/
├── data/
│   └── result.json  ← Place here
```

---

## Setup Instructions (Windows)

Run the automated setup script from **Command Prompt** (not PowerShell):

```cmd
setup.bat
```

This will:

* Create and activate a Python virtual environment
* Upgrade `pip`
* Clone the official [LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory) repository and install Python dependencies from `requirements.txt`
* Patch `dataset_info.json` to register your dataset (`chat_sharegpt`)
* Process your exported Telegram chat (`result.json`) into `chat_sharegpt.json`
* Place the converted dataset in the correct directory (`LLaMA-Factory/data`)

Once complete, you will see:

```
All steps completed successfully.
Please refer to the README.md for the next steps.
You will find instructions on how to launch training.
```

Make sure your `result.json` file is already located at:

```
./data/result.json
```

## Fine-Tune Your Model (LoRA)

The following example uses **Qwen1.5-1.8B-Chat**, but you can **replace it with any Hugging Face-compatible model**.

### Basic LoRA Fine-Tuning Command

```cmd
python LLaMA-Factory\src\train.py --stage sft --do_train ^
  --model_name_or_path Qwen/Qwen1.5-1.8B-Chat ^
  --dataset chat_sharegpt ^
  --dataset_dir .\LLaMA-Factory\data ^
  --template qwen ^
  --finetuning_type lora ^
  --lora_target Wqkv,o_proj,gate_proj,down_proj,up_proj ^
  --output_dir saves\Qwen1.5-1.8B-Chat-lora ^
  --overwrite_cache ^
  --per_device_train_batch_size 2 ^
  --gradient_accumulation_steps 4 ^
  --lr_scheduler_type cosine ^
  --logging_steps 10 ^
  --save_strategy steps ^
  --save_steps 100 ^
  --learning_rate 5e-5 ^
  --num_train_epochs 3.0 ^
  --plot_loss
```

---

### How to Customize for Your Model

Modify these flags to match your model:

| Option                 | Description                                              |
| ---------------------- | -------------------------------------------------------- |
| `--model_name_or_path` | Hugging Face model ID or local model path                |
| `--template`           | Prompt template type (e.g., `qwen`, `chatml`, `default`) |
| `--lora_target`        | LoRA target modules (refer to model’s architecture)      |
| `--output_dir`         | Destination to save the LoRA checkpoints                 |

If you're using a model like `mistralai/Mistral-7B-Instruct-v0.2`, you would change:

```cmd
--model_name_or_path mistralai/Mistral-7B-Instruct-v0.2 ^
--template chatml ^
--lora_target q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj ^
--output_dir saves\Mistral-7B-Instruct-lora ^
```

Refer to the [LLaMA-Factory model table](https://github.com/hiyouga/LLaMA-Factory#currently-supported-models) for recommended values.

---

### To Resume Training

Find your latest checkpoint under your `saves` folder, then add this flag:

```cmd
--resume_from_checkpoint saves\Qwen1.5-1.8B-Chat-lora\checkpoint-400
```

---

### Merge LoRA Adapter with Base Model

Edit the `export_lora.yaml` file to match your model:

```yaml
# export_lora.yaml
base_model: Qwen/Qwen1.5-1.8B-Chat
lora_model: saves/Qwen1.5-1.8B-Chat-lora
output_dir: merged/Qwen1.5-1.8B-Chat-merged
```

Then run:

```cmd
llamafactory-cli export export_lora.yaml
```

---

### Chat Inference with Fine-Tuned Model

Test your merged model in an interactive shell:

```cmd
llamafactory-cli chat ^
  --model_name_or_path merged/Qwen1.5-1.8B-Chat-merged ^
  --template qwen
```

Update `--template` to match the one used during training.

## Manually Activate the Virtual Environment

If you’ve already run `setup.bat`, the virtual environment is created automatically.
In future sessions, you can activate it manually before running any Python scripts:

### Activate on Windows (Command Prompt)

```cmd
venv\Scripts\activate
```

You should see the prompt change to show that the environment is active:

```
(venv) C:\Users\yourname\DialogSmith>
```

Once activated, you can run `python`, `pip`, or training commands as usual.
