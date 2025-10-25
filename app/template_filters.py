"""
Template filters for POS system
These filters automatically handle modifier pricing in templates
"""

from flask import current_app
from app.utils.pricing_helpers import get_order_total_with_modifiers

def register_template_filters(app):
    """Register custom template filters"""
    
    @app.template_filter('order_total_with_modifiers')
    def order_total_with_modifiers_filter(order):
        """
        Template filter to get order total including modifiers
        Usage in templates: {{ order|order_total_with_modifiers }}
        """
        return get_order_total_with_modifiers(order)
    
    @app.template_filter('item_total_with_modifiers')
    def item_total_with_modifiers_filter(item):
        """
        Template filter to get item total including modifiers
        Usage in templates: {{ item|item_total_with_modifiers }}
        """
        if not item:
            return 0.0
        return float(item.total_price) + float(item.modifiers_total_price or 0)
    
    @app.template_filter('format_currency')
    def format_currency_filter(amount):
        """
        Template filter to format currency
        Usage in templates: {{ amount|format_currency }}
        """
        try:
            return f"{float(amount):.2f}"
        except (ValueError, TypeError):
            return "0.00"
