import requests

def send_feishu(webhook_url, content):
    requests.post(webhook_url, json={
        "msg_type": "text",
        "content": {"text": content}
    })

