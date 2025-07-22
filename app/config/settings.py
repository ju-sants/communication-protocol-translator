from pydantic_settings import BaseSettings
from typing import Dict

class Settings(BaseSettings):
    JT808_LISTENER_PORT: int = 65432
    MAIN_SERVER_HOST: str = '127.0.0.1'
    MAIN_SERVER_PORT: int = 12345

    JT808_TO_SUNTECH_ALERT_MAP: Dict[int, int] = {
        0: 42,  # Bit 0 (SOS) -> Alert 42 (Panic Button)
        1: 1,   # Bit 1 (Over-speed) -> Alert 1 (Over Speed)
        5: 3,   # Bit 5 (GNSS Antenna not connected) -> Alert 3 (GPS Antenna Disconnected)
        8: 41,  # Bit 8 (Main power cut off) -> Alert 41 (Power Disconnected)
        27: 33, # Bit 27 (Illegal fire) -> Alert 33 (Ignition On)
    }

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()