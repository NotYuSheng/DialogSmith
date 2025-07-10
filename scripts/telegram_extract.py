import json

# CONFIGURATION
RESULT_PATH = "./data/result.json"      # Path to your exported result.json file
OUTPUT_PATH = "./data/chat_dataset.jsonl"
TIME_GAP_THRESHOLD = 30                # Seconds between chained messages

def get_user_name(data):
    personal_info = data.get("personal_information", {})
    first = personal_info.get("first_name", "")
    last = personal_info.get("last_name", "")
    return f"{first} {last}".strip()

def load_all_messages_from_result(data):
    all_messages = []
    chat_list = data.get("chats", {}).get("list", [])

    for chat in chat_list:
        messages = chat.get("messages", [])
        if not messages:
            continue
        all_messages.append(messages)

    return all_messages  # List of message lists (per chat)

def format_conversations(message_groups, your_name):
    samples = []

    for messages in message_groups:
        i = 0
        while i < len(messages) - 1:
            msg = messages[i]

            if msg.get("type") != "message" or not msg.get("text"):
                i += 1
                continue

            sender = msg.get("from")
            if sender == your_name:
                i += 1
                continue  # Only process messages from others as prompts

            # Format the prompt
            if isinstance(msg["text"], str):
                prompt = f"{sender}: {msg['text']}"
            else:
                prompt = f"{sender}: {''.join([t['text'] for t in msg.get('text_entities', [])])}"

            # Gather your consecutive responses
            response = []
            j = i + 1
            while j < len(messages):
                next_msg = messages[j]
                if next_msg.get("type") != "message" or not next_msg.get("text"):
                    j += 1
                    continue

                if next_msg.get("from") != your_name:
                    break

                time_diff = int(next_msg["date_unixtime"]) - int(messages[j - 1]["date_unixtime"])
                if time_diff > TIME_GAP_THRESHOLD:
                    break

                text = next_msg["text"]
                if isinstance(text, str):
                    response.append(text)
                elif isinstance(text, list):
                    response.append(''.join([t["text"] for t in next_msg.get("text_entities", [])]))

                j += 1

            if response:
                samples.append({
                    "prompt": prompt.strip(),
                    "response": "\n".join(response).strip()
                })

            i = j  # Move pointer forward

    return samples

def save_dataset(samples, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        for sample in samples:
            json.dump(sample, f, ensure_ascii=False)
            f.write("\n")

if __name__ == "__main__":
    print(f"Loading {RESULT_PATH}...")
    with open(RESULT_PATH, encoding="utf-8") as f:
        data = json.load(f)

    your_name = get_user_name(data)
    print(f"Detected user name: {your_name}")

    message_groups = load_all_messages_from_result(data)

    print("Formatting prompt-response pairs...")
    samples = format_conversations(message_groups, your_name)

    print(f"Saving {len(samples)} samples to {OUTPUT_PATH}...")
    save_dataset(samples, OUTPUT_PATH)
    print("Done.")
