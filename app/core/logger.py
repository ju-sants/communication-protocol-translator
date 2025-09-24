import sys
from loguru import logger
from app.config.settings import settings

# Remove o handler padrão para evitar logs duplicados
logger.remove()

# Adiciona um novo "sink" para o stdout com um formato mais rico e colorido
logger.add(
    sys.stdout,
    level=settings.LOG_LEVEL.upper(),
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
           "<level>{level: <8}</level> | "
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