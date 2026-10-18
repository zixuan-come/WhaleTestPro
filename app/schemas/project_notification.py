from pydantic import BaseModel, ConfigDict, SecretStr


class NotificationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    webhook_url: SecretStr | None = None
    signing_secret: SecretStr | None = None
    clear_webhook: bool = False
    clear_signing_secret: bool = False


class NotificationStatus(BaseModel):
    enabled: bool
    configured: bool
    signing_configured: bool
    can_manage: bool
