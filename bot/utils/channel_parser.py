import re


def parse_channel_input(text: str) -> int | str:
    """Parse channel link/username into chat_id or public username."""
    text = text.strip()

    private_link = re.search(r"(?:https?://)?t\.me/c/(\d+)", text)
    if private_link:
        return int(f"-100{private_link.group(1)}")

    public_link = re.search(r"(?:https?://)?t\.me/([a-zA-Z0-9_]+)", text)
    if public_link and public_link.group(1) != "c":
        return public_link.group(1)

    if text.lstrip("-").isdigit():
        val = int(text)
        if val > 0:
            return int(f"-100{val}")
        return val

    return text.lstrip("@")
