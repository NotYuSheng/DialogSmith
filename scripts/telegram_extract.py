import json

# CONFIGURATION
RESULT_PATH = "./data/result.json"       # Path to your exported result.json file
OUTPUT_PATH = "./data/chat_dataset.jsonl"
MESSAGE_CHAIN_THRESHOLD = 30             # Max seconds between chained messages from same sender
CONVERSATION_GAP_THRESHOLD = 3600        # Seconds of silence that starts a new conversation


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
        if messages:
            all_messages.append(messages)
    return all_messages  # List of message lists (per chat)


def get_text(msg):
    """Extract plain text from a message, handling both string and entity list formats."""
    text = msg.get("text", "")
    if isinstance(text, str):
        return text.strip()
    if isinstance(text, list):
        return "".join(
            t["text"] if isinstance(t, dict) else t
            for t in msg.get("text_entities", text)
        ).strip()
    return ""


def is_valid_message(msg):
    return msg.get("type") == "message" and bool(get_text(msg))


def collect_turn(messages, start_idx, sender, chain_threshold):
    """
    Collect all consecutive messages from `sender` starting at `start_idx`,
    chaining them if within `chain_threshold` seconds of the previous message
    in the chain.

    Returns (texts: list[str], next_idx: int, last_unixtime: int)
    """
    texts = []
    last_unixtime = None
    j = start_idx

    while j < len(messages):
        msg = messages[j]

        if not is_valid_message(msg):
            j += 1
            continue

        if msg.get("from") != sender:
            break

        unixtime = int(msg["date_unixtime"])

        if last_unixtime is not None and (unixtime - last_unixtime) > chain_threshold:
            break

        texts.append(get_text(msg))
        last_unixtime = unixtime
        j += 1

    return texts, j, last_unixtime


def split_into_conversations(messages, gap_threshold):
    """
    Split a flat message list into sub-lists representing distinct conversations,
    based on silence gaps between valid messages.
    """
    conversations = []
    current = []
    last_unixtime = None

    for msg in messages:
        if not is_valid_message(msg):
            continue

        unixtime = int(msg["date_unixtime"])

        if last_unixtime is not None and (unixtime - last_unixtime) > gap_threshold:
            if current:
                conversations.append(current)
            current = []

        current.append(msg)
        last_unixtime = unixtime

    if current:
        conversations.append(current)

    return conversations


def format_conversations(message_groups, your_name):
    """
    For each chat, split messages into conversations, then walk each conversation
    collecting alternating turns into multi-turn samples.

    Each sample is a list of {"role": ..., "text": ...} dicts.
    Consecutive messages from the same sender are concatenated into one turn.
    """
    samples = []

    for messages in message_groups:
        conversations = split_into_conversations(messages, CONVERSATION_GAP_THRESHOLD)

        for conversation in conversations:
            turns = []
            i = 0

            while i < len(conversation):
                msg = conversation[i]
                sender = msg.get("from")
                role = "assistant" if sender == your_name else "user"

                texts, next_i, _ = collect_turn(
                    conversation, i, sender, MESSAGE_CHAIN_THRESHOLD
                )

                if texts:
                    turn_text = "\n".join(texts)
                    # Merge with previous turn if same role (edge case: gap exceeded mid-block)
                    if turns and turns[-1]["role"] == role:
                        turns[-1]["text"] += "\n" + turn_text
                    else:
                        turns.append({"role": role, "text": turn_text})

                i = next_i

            # Only keep conversations that have at least one user + one assistant turn
            roles = [t["role"] for t in turns]
            if "user" in roles and "assistant" in roles:
                samples.append(turns)

    return samples


def save_dataset(samples, out_path):
    with open(out_path, "w", encoding="utf-8") as f:
        for sample in samples:
            json.dump({"conversations": sample}, f, ensure_ascii=False)
            f.write("\n")


if __name__ == "__main__":
    from validator import validate_samples

    print(f"Loading {RESULT_PATH}...")
    with open(RESULT_PATH, encoding="utf-8") as f:
        data = json.load(f)

    your_name = get_user_name(data)
    print(f"Detected user name: {your_name}")

    message_groups = load_all_messages_from_result(data)

    print("Formatting multi-turn conversations...")
    samples = format_conversations(message_groups, your_name)
    print(f"Extracted {len(samples)} conversation samples.")

    samples = validate_samples(samples)

    print(f"Saving {len(samples)} conversation samples to {OUTPUT_PATH}...")
    save_dataset(samples, OUTPUT_PATH)
    print("Done.")
