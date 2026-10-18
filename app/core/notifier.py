import base64
import hashlib
import hmac
import re
import time
from urllib.parse import urlsplit

import requests


class NotificationDeliveryError(RuntimeError):
    pass


def validate_feishu_webhook(value):
    if len(value) > 512 or any(char.isspace() or ord(char) < 32 for char in value):
        raise ValueError("Invalid Feishu Webhook")
    url = urlsplit(value)
    if (url.scheme != "https" or url.netloc.lower() != "open.feishu.cn" or url.query or url.fragment
            or not re.fullmatch(r"/open-apis/bot/v2/hook/[A-Za-z0-9_-]{16,128}", url.path)):
        raise ValueError("Invalid Feishu Webhook")
    return value


def send_feishu(webhook_url, content, signing_secret=None):
    try:
        validate_feishu_webhook(webhook_url)
    except ValueError:
        raise NotificationDeliveryError("Webhook 地址无效，请管理员重新配置") from None
    payload = {"msg_type": "text", "content": {"text": content}}
    if signing_secret:
        timestamp = str(int(time.time()))
        key = f"{timestamp}\n{signing_secret}".encode()
        payload.update(timestamp=timestamp, sign=base64.b64encode(hmac.new(key, digestmod=hashlib.sha256).digest()).decode())
    try:
        response = requests.post(webhook_url, json=payload, timeout=(3, 5), allow_redirects=False)
        if not 200 <= response.status_code < 300:
            raise NotificationDeliveryError("飞书服务请求失败，请稍后重试")
        result = response.json()
        if not isinstance(result, dict):
            raise NotificationDeliveryError("飞书返回格式异常，请稍后重试")
        code = result.get("code", result.get("StatusCode"))
        if type(code) is not int or code != 0:
            messages = {19024: "飞书关键词校验失败，请在机器人中允许关键词 WhaleTestPro",
                        19021: "飞书签名校验失败，请检查签名密钥和服务器时间",
                        19022: "飞书 IP 白名单校验失败，请检查服务器出口 IP",
                        11232: "飞书通知频率受限，请稍后重试"}
            message = messages.get(code) if type(code) is int else None
            raise NotificationDeliveryError(message or "飞书未接受消息，请检查机器人和安全设置")
    except (requests.RequestException, ValueError):
        raise NotificationDeliveryError("无法连接飞书或响应异常，请稍后重试") from None

