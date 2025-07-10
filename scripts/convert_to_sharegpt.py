import json

input_path = "./data/chat_dataset.jsonl"
output_path = "./data/chat_sharegpt.json"

output_data = []

with open(input_path, "r", encoding="utf-8") as infile:
    for line in infile:
        sample = json.loads(line)
        prompt = sample.get("prompt", "").strip()
        response = sample.get("response", "").strip()

        if not prompt or not response:
            continue  # Skip blank entries

        output_data.append({
            "conversations": [
                {"from": "user", "value": prompt},
                {"from": "assistant", "value": response}
            ]
        })

with open(output_path, "w", encoding="utf-8") as outfile:
    json.dump(output_data, outfile, indent=2, ensure_ascii=False)

print(f"Converted {len(output_data)} valid samples to ShareGPT format.")
