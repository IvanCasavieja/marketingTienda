"""Backward-compat shim — toda la lógica vive en app.services.cenefas.*"""
from app.services.cenefas.render_engine import generate_pptx_bytes
from app.services.cenefas.data_engine import load_products_from_bytes, generate_template_bytes

__all__ = ["generate_pptx_bytes", "load_products_from_bytes", "generate_template_bytes"]
