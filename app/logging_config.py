import sys
import json
from pathlib import Path
from loguru import logger
from contextvars import ContextVar
from typing import Optional, Dict, Any

# Context variables voor tenant, lead en quote IDs
tenant_id_var: ContextVar[Optional[str]] = ContextVar('tenant_id', default=None)
lead_id_var: ContextVar[Optional[str]] = ContextVar('lead_id', default=None)
quote_id_var: ContextVar[Optional[str]] = ContextVar('quote_id', default=None)

def get_context_info() -> Dict[str, Any]:
    """Haal context informatie op voor logging"""
    context = {}
    
    tenant_id = tenant_id_var.get()
    if tenant_id:
        context['tenant_id'] = tenant_id
    
    lead_id = lead_id_var.get()
    if lead_id:
        context['lead_id'] = lead_id
    
    quote_id = quote_id_var.get()
    if quote_id:
        context['quote_id'] = quote_id
    
    return context

def setup_logging():
    """Configureer Loguru logging met context-aware formatting"""
    # Verwijder standaard handler
    logger.remove()
    
    # Console handler met kleuren
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <blue>tenant_id={extra[tenant_id]}</blue> | <yellow>lead_id={extra[lead_id]}</yellow> | <magenta>quote_id={extra[quote_id]}</magenta> | <level>{message}</level>",
        level="INFO",
        colorize=True,
        backtrace=True,
        diagnose=True
    )
    
    # File handler voor alle logs
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    logger.add(
        log_dir / "app.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | tenant_id={extra[tenant_id]} | lead_id={extra[lead_id]} | quote_id={extra[quote_id]} | {message}",
        level="DEBUG",
        rotation="1 day",
        retention="30 days",
        compression="zip"
    )
    
    # Error file handler
    logger.add(
        log_dir / "errors.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | tenant_id={extra[tenant_id]} | lead_id={extra[lead_id]} | quote_id={extra[quote_id]} | {message}",
        level="ERROR",
        rotation="1 day",
        retention="30 days",
        compression="zip"
    )

def get_logger(name: str = None):
    """Krijg een logger met context informatie"""
    if name:
        return logger.bind(
            tenant_id=tenant_id_var.get(),
            lead_id=lead_id_var.get(),
            quote_id=quote_id_var.get()
        )
    return logger

def set_context(tenant_id: Optional[str] = None, lead_id: Optional[str] = None, quote_id: Optional[str] = None):
    """Zet context variabelen voor logging"""
    if tenant_id is not None:
        tenant_id_var.set(tenant_id)
    if lead_id is not None:
        lead_id_var.set(lead_id)
    if quote_id is not None:
        quote_id_var.set(quote_id)

def clear_context():
    """Wis alle context variabelen"""
    tenant_id_var.set(None)
    lead_id_var.set(None)
    quote_id_var.set(None)

# Context manager voor automatische context setting
class LoggingContext:
    def __init__(self, tenant_id: Optional[str] = None, lead_id: Optional[str] = None, quote_id: Optional[str] = None):
        self.tenant_id = tenant_id
        self.lead_id = lead_id
        self.quote_id = quote_id
        self.old_tenant_id = None
        self.old_lead_id = None
        self.old_quote_id = None
    
    def __enter__(self):
        self.old_tenant_id = tenant_id_var.get()
        self.old_lead_id = lead_id_var.get()
        self.old_quote_id = quote_id_var.get()
        
        set_context(self.tenant_id, self.lead_id, self.quote_id)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        set_context(self.old_tenant_id, self.old_lead_id, self.old_quote_id)
