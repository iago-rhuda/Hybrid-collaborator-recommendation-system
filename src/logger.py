import logging
import sys

def get_logger(name: str) -> logging.Logger:
    """
    Creates and configures a robust logger for the project.
    """
    logger = logging.getLogger(name)
    
    if not logger.hasHandlers():
        logger.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # File handler (optional, logs to a file in the project root)
        file_handler = logging.FileHandler("pipeline.log", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        
        # Formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        
    return logger
