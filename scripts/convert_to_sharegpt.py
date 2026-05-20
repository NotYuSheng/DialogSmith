import json

input_path = "./data/chat_dataset.jsonl"
output_path = "./data/chat_sharegpt.json"

ROLE_MAP = {
    "user": "human",
    "assistant": "gpt",
}

output_data = []

with open(input_path, "r", encoding="utf-8") as infile:
    for line in infile:
        sample = json.loads(line)
        turns = sample.get("conversations", [])

        if not turns:
            continue

        conversations = []
        for turn in turns:
            role = ROLE_MAP.get(turn.get("role", ""), turn.get("role", ""))
            text = turn.get("text", "").strip()
            if role and text:
                conversations.append({"from": role, "value": text})

        # Must have at least one human and one gpt turn
        roles_present = {t["from"] for t in conversations}
        if "human" not in roles_present or "gpt" not in roles_present:
            continue

        output_data.append({"conversations": conversations})

with open(output_path, "w", encoding="utf-8") as outfile:
    json.dump(output_data, outfile, indent=2, ensure_ascii=False)

print(f"Converted {len(output_data)} valid conversation samples to ShareGPT format.")
