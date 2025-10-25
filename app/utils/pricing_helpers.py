"""
Pricing helper functions for POS system
Handles special item modifier pricing calculations
"""

from app.models import Order, OrderItem, Category, MenuItem
from sqlalchemy import func
from decimal import Decimal

def get_order_total_with_modifiers(order):
    """
    Get order total including modifier prices
    This is a helper function that can be used in templates and views
    """
    if not order:
        return 0.0
    
    base_total = float(order.total_amount or 0)
    modifiers_total = sum(float(item.modifiers_total_price or 0) 
                         for item in order.order_items 
                         if not item.is_deleted)
    return base_total + modifiers_total

def calculate_revenue_with_modifiers(orders):
    """
    Calculate total revenue including modifier prices for a list of orders
    """
    total_revenue = 0.0
    for order in orders:
        if hasattr(order, 'status') and order.status.name == 'PAID':
            total_revenue += get_order_total_with_modifiers(order)
    return total_revenue

def update_all_order_totals():
    """
    Update all order totals to include modifier prices
    This should be called after the migration
    """
    from app import db
    
    orders = Order.query.all()
    updated_count = 0
    
    for order in orders:
        old_total = float(order.total_amount)
        order.update_total_with_modifiers()
        new_total = float(order.total_amount)
        
        if abs(old_total - new_total) > 0.01:  # Only count significant changes
            updated_count += 1
    
    db.session.commit()
    return updated_count

def get_daily_sales_with_modifiers(start_date, end_date, branch_id=None):
    """
    Get daily sales data including modifier prices
    """
    from app import db
    from sqlalchemy import func, case
    from app.models import OrderStatus
    
    # Get orders in date range
    query = Order.query.filter(
        Order.created_at >= start_date,
        Order.created_at <= end_date
    )
    
    if branch_id:
        query = query.filter(Order.branch_id == branch_id)
    
    orders = query.all()
    
    # Group by date and calculate totals with modifiers
    daily_data = {}
    
    for order in orders:
        date_key = order.created_at.date().strftime('%Y-%m-%d')
        
        if date_key not in daily_data:
            daily_data[date_key] = {
                'date': date_key,
                'total_orders': 0,
                'paid_orders': 0,
                'unpaid_orders': 0,
                'revenue': 0.0
            }
        
        daily_data[date_key]['total_orders'] += 1
        
        if order.status.name == 'PAID':
            daily_data[date_key]['paid_orders'] += 1
            daily_data[date_key]['revenue'] += get_order_total_with_modifiers(order)
        else:
            daily_data[date_key]['unpaid_orders'] += 1
    
    return list(daily_data.values())

def get_service_type_stats_with_modifiers(start_date, end_date, branch_id=None):
    """
    Get service type statistics including modifier prices
    """
    query = Order.query.filter(
        Order.created_at >= start_date,
        Order.created_at <= end_date,
        Order.status.has(name='PAID')
    )
    
    if branch_id:
        query = query.filter(Order.branch_id == branch_id)
    
    orders = query.all()
    
    # Group by service type
    service_stats = {}
    
    for order in orders:
        service_type = order.service_type.value if order.service_type else 'on_table'
        
        if service_type not in service_stats:
            service_stats[service_type] = {
                'count': 0,
                'revenue': 0.0
            }
        
        service_stats[service_type]['count'] += 1
        service_stats[service_type]['revenue'] += get_order_total_with_modifiers(order)
    
    return service_stats

def format_order_for_api(order):
    """
    Format order data for API responses including modifier prices
    """
    return {
        'id': order.id,
        'order_number': order.order_number,
        'order_counter': order.order_counter if order.order_counter else None,
        'total_amount': float(order.total_amount),
        'total_amount_with_modifiers': get_order_total_with_modifiers(order),
        'status': order.status.value,
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'paid_at': order.paid_at.isoformat() if order.paid_at else None,
        'table_number': order.table.table_number if order.table else None,
        'cashier_name': order.cashier.get_full_name() if order.cashier else None,
        'service_type': order.service_type.value if order.service_type else 'on_table',
        'delivery_company': order.delivery_company_info.name if order.delivery_company_info else None,
        'branch_name': order.branch.name if order.branch else None
    }

def format_order_item_for_api(item):
    """
    Format order item data for API responses including modifier prices
    """
    return {
        'id': item.id,
        'menu_item_id': item.menu_item_id,
        'menu_item_name': item.menu_item.name,
        'quantity': item.quantity,
        'unit_price': float(item.unit_price),
        'total_price': float(item.total_price),
        'modifiers_total_price': float(item.modifiers_total_price or 0),
        'total_price_with_modifiers': item.total_price_with_modifiers,
        'notes': item.notes,
        'special_requests': item.special_requests,
        'is_new': item.is_new or False,
        'is_deleted': item.is_deleted or False
    }
