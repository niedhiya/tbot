import time
import os
import requests

TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

def get_updates(offset=None):
    url = f"{URL}/getUpdates"
    params = {"timeout": 100, "offset": offset}
    response = requests.get(url, params=params)
    return response.json()

def send_message(chat_id, text):
    url = f"{URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

def main():
    offset = None
    while True:
        updates = get_updates(offset)
        if "result" in updates:
            for update in updates["result"]:
                message = update.get("message")
                if message:
                    chat_id = message["chat"]["id"]
                    text = message.get("text", "")
                    send_message(chat_id, f"Echo: {text}")
                    offset = update["update_id"] + 1
        time.sleep(1)

if __name__ == '__main__':
    main()
