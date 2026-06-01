"""Cenefas v2 — motor de generación de cenefas por componentes."""
from app.services.cenefas.render_engine import generate_pptx_bytes
from app.services.cenefas.data_engine import load_products_from_bytes, generate_template_bytes
from app.services.cenefas.component_renderer import render_template_to_pptx, generate_from_template_v2
from app.services.cenefas.rules_engine import evaluate_rules, apply_visibility
from app.services.cenefas.layout_engine import compute_layout, get_format, FORMATS, cm_to_emu
from app.services.cenefas.validation_engine import validate_products, build_summary

__all__ = [
    "generate_pptx_bytes",
    "load_products_from_bytes",
    "generate_template_bytes",
    "render_template_to_pptx",
    "generate_from_template_v2",
    "evaluate_rules",
    "apply_visibility",
    "compute_layout",
    "get_format",
    "FORMATS",
    "cm_to_emu",
    "validate_products",
    "build_summary",
]
