from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mqtt_broker: str = "mosquitto"
    mqtt_port: int = 1883
    mqtt_topic: str = "inspections/line1/detections"

    database_url: str = "postgresql+asyncpg://inspector:inspector_pass@postgres:5432/inspections"

    alert_defect_rate_threshold: int = 5
    alert_webhook_url: str = ""


settings = Settings()
