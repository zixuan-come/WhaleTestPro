"""Project-scoped Feishu configuration; credentials never leave the server."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.core.config import settings
from app.core.notifier import NotificationDeliveryError, send_feishu, validate_feishu_webhook
from app.models.project import Project
from app.models.project_notification import ProjectNotification


def _cipher(project_id):
    key = hashlib.sha256(f"WhaleTestPro/project-notification/v1/{project_id}/{settings.SECRET_KEY}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _encrypt(project_id, value):
    return _cipher(project_id).encrypt(value.encode()).decode()


def _decrypt(project_id, value):
    try:
        return _cipher(project_id).decrypt(value.encode()).decode()
    except (InvalidToken, ValueError, UnicodeError):
        raise NotificationDeliveryError("通知凭据无法读取，请管理员重新保存配置") from None


def status(db, project_id, can_manage=False):
    row = db.get(ProjectNotification, project_id)
    return {"enabled": bool(row and row.feishu_enabled), "configured": bool(row and row.webhook_ciphertext),
            "signing_configured": bool(row and row.signing_secret_ciphertext), "can_manage": can_manage}


def save(db, project_id, data):
    webhook = data.webhook_url.get_secret_value().strip() if data.webhook_url else ""
    secret = data.signing_secret.get_secret_value().strip() if data.signing_secret else ""
    if (data.clear_webhook and webhook) or (data.clear_signing_secret and secret):
        raise HTTPException(422, "不能同时清除和替换同一项配置")
    if webhook:
        try:
            validate_feishu_webhook(webhook)
        except ValueError:
            raise HTTPException(422, "请输入有效的飞书自定义机器人 HTTPS Webhook 地址") from None
    if len(secret) > 512 or any(ord(char) < 32 for char in secret):
        raise HTTPException(422, "签名密钥格式不正确")
    # Serialize the first save against other saves and project deletion.
    if db.query(Project).filter_by(id=project_id).with_for_update().first() is None:
        raise HTTPException(404, "项目不存在")
    row = db.get(ProjectNotification, project_id)
    if data.enabled and not (webhook or (row and row.webhook_ciphertext and not data.clear_webhook)):
        raise HTTPException(422, "启用飞书通知前请先填写 Webhook 地址")
    if secret and not (webhook or (row and row.webhook_ciphertext and not data.clear_webhook)):
        raise HTTPException(422, "请先填写 Webhook 地址")
    if row is None:
        row = ProjectNotification(project_id=project_id)
        db.add(row)
    row.feishu_enabled = data.enabled
    if webhook:
        row.webhook_ciphertext = _encrypt(project_id, webhook)
    elif data.clear_webhook:
        row.webhook_ciphertext = None
        row.signing_secret_ciphertext = None
    if secret:
        row.signing_secret_ciphertext = _encrypt(project_id, secret)
    elif data.clear_signing_secret:
        row.signing_secret_ciphertext = None
    db.commit()
    return status(db, project_id, True)


def _credentials(db, project_id, require_enabled=True):
    row = db.query(ProjectNotification).filter_by(project_id=project_id).populate_existing().first()
    if not row or not row.webhook_ciphertext:
        raise NotificationDeliveryError("本项目尚未配置飞书通知，请联系项目管理员")
    if require_enabled and not row.feishu_enabled:
        raise NotificationDeliveryError("本项目的飞书通知已停用")
    return (_decrypt(project_id, row.webhook_ciphertext),
            _decrypt(project_id, row.signing_secret_ciphertext) if row.signing_secret_ciphertext else None)


def send_test(db, project_id):
    try:
        webhook, secret = _credentials(db, project_id, require_enabled=False)
        project = db.get(Project, project_id)
        send_feishu(webhook, f"WhaleTestPro 测试通知\n项目：{project.name}\n通知配置验证成功。", secret)
    except NotificationDeliveryError as exc:
        raise HTTPException(400, str(exc)) from None


def notify_regression(db, project_id, summary):
    """Delivery failure never changes test verdicts or loses a report."""
    try:
        webhook, secret = _credentials(db, project_id)
        project = db.get(Project, project_id)
        content = (f"WhaleTestPro 回归结果\n项目：{project.name}\n"
                   f"通过：{summary['passed_count']}/{summary['total']}\n"
                   f"通过率：{summary['pass_rate']:.0%}\n接口覆盖率：{summary['interface_coverage']:.0%}")
        send_feishu(webhook, content, secret)
    except NotificationDeliveryError as exc:
        summary["notification_warning"] = f"测试已执行完成，但通知未发送：{exc}"
    except Exception:
        summary["notification_warning"] = "测试已执行完成，但飞书通知发送失败，请管理员检查通知配置"
