import sys
import threading
from loguru import logger
from app.config.settings import settings

log_context = threading.local()

def context_patcher(record):
    record["extra"]["device_id"] = getattr(log_context, 'device_id', 'N/A')

# Remove o handler padrão para evitar logs duplicados
logger.remove()

# Isso garante que todos os logs que passarem por aqui terão o patch aplicado.
logger.patch(context_patcher)

# Adiciona um novo "sink" para o stdout com o formato modificado
logger.add(
    sys.stdout,
    level=settings.LOG_LEVEL.upper(),
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
           "<level>{level: <8}</level> | "
           "<yellow>[{extra[device_id]: <15}]</yellow> | "
           "<cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>",
    colorize=True,
    backtrace=True,
    diagnose=True
)

def get_logger(name: str):
    """
    Retorna uma instância do logger Loguru com o nome do módulo associado.
    """
    return logger.bind(name=name)

def set_log_context(device_id: str | None):
    if device_id:
        log_context.device_id = device_id
    elif hasattr(log_context, 'device_id'):
        del log_context.device_id