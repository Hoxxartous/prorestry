"""
Sync API - Cloud endpoints for Edge↔Cloud synchronization

Endpoints:
- POST /api/sync/push - Edge pushes transactional data to cloud
- GET /api/sync/pull - Edge pulls reference/config data from cloud
- GET /api/sync/ping - Health check with auth validation
"""

from flask import Blueprint, request, jsonify, current_app
import os
from app import db
from app.models import (
    AppSettings, Order, OrderStatus, OrderItem, Payment,
    Branch, User, UserBranchAssignment, Category, MenuItem, Table,
    Customer, DeliveryCompany, Kitchen, CategoryKitchenAssignment,
    CategorySpecialItemAssignment, AdminPinCode, CashierPin,
    CashierSession, ManualCardPayment, OrderEditHistory,
    KitchenOrder, KitchenOrderItem, WaiterCashierAssignment,
    InventoryItem, PaymentMethod, ServiceType, KitchenOrderStatus
)
from sqlalchemy import text, inspect
from datetime import datetime
import json

sync_api = Blueprint('sync_api', __name__)


# ============================================================================
# AUTHENTICATION
# ============================================================================

def _normalize_token(val):
    s = str(val or '').strip()
    # Strip common accidental quotes from env/vars
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1].strip()
    if s.startswith("'") and s.endswith("'"):
        s = s[1:-1].strip()
    return s


def _get_expected_token():
    """Return (token, source) without logging the secret. Prefer env > config > db."""
    envv = os.environ.get('SYNC_API_TOKEN')
    if envv:
        return _normalize_token(envv), 'env'
    cfg = current_app.config.get('SYNC_API_TOKEN')
    if cfg:
        return _normalize_token(cfg), 'config'
    dbv = AppSettings.get_value('sync_api_token')
    if dbv:
        return _normalize_token(dbv), 'db'
    return None, 'none'


def _auth_ok():
    token_header = request.headers.get('X-Edge-Token') or request.headers.get('Authorization', '').replace('Bearer ', '')
    expected, src = _get_expected_token()
    if not expected:
        current_app.logger.warning('Sync API token not configured (source=none)')
        return False
    ok = _normalize_token(token_header) == expected
    try:
        current_app.logger.info(
            f"sync_auth check: source={src} header_present={bool(token_header)} header_len={len(str(token_header or ''))}"
        )
    except Exception:
        pass
    return ok


# ============================================================================
# MODEL REGISTRY - Maps model names to classes
# ============================================================================

MODEL_REGISTRY = {
    # Transactional (pushed from edge)
    'Order': Order,
    'OrderItem': OrderItem,
    'Payment': Payment,
    'KitchenOrder': KitchenOrder,
    'KitchenOrderItem': KitchenOrderItem,
    'CashierSession': CashierSession,
    'ManualCardPayment': ManualCardPayment,
    'OrderEditHistory': OrderEditHistory,
    'Customer': Customer,
    'WaiterCashierAssignment': WaiterCashierAssignment,
    
    # Reference/Config (pulled by edge)
    'Branch': Branch,
    'User': User,
    'UserBranchAssignment': UserBranchAssignment,
    'Category': Category,
    'MenuItem': MenuItem,
    'Table': Table,
    'DeliveryCompany': DeliveryCompany,
    'Kitchen': Kitchen,
    'CategoryKitchenAssignment': CategoryKitchenAssignment,
    'CategorySpecialItemAssignment': CategorySpecialItemAssignment,
    'AdminPinCode': AdminPinCode,
    'CashierPin': CashierPin,
    'AppSettings': AppSettings,
    'InventoryItem': InventoryItem,
}

# Enum mappings for deserialization
ENUM_MAPPINGS = {
    'status': {'pending': OrderStatus.PENDING, 'paid': OrderStatus.PAID, 'cancelled': OrderStatus.CANCELLED},
    'payment_method': {'cash': PaymentMethod.CASH, 'card': PaymentMethod.CARD, 'qr_code': PaymentMethod.QR_CODE},
    'service_type': {'on_table': ServiceType.ON_TABLE, 'take_away': ServiceType.TAKE_AWAY, 'delivery': ServiceType.DELIVERY, 'card': ServiceType.CARD},
    'kitchen_status': {'received': KitchenOrderStatus.RECEIVED, 'preparing': KitchenOrderStatus.PREPARING, 'ready': KitchenOrderStatus.READY, 'served': KitchenOrderStatus.SERVED},
}


# ============================================================================
# SERIALIZATION HELPERS
# ============================================================================

def _iso(dt):
    """Convert datetime to ISO string."""
    if not dt:
        return None
    if hasattr(dt, 'isoformat'):
        return dt.isoformat()
    return str(dt)


def _parse_iso(iso_str):
    """Parse ISO string to datetime."""
    if not iso_str:
        return None
    try:
        if iso_str.endswith('Z'):
            iso_str = iso_str[:-1] + '+00:00'
        return datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return None


def _serialize_record(obj):
    """Serialize a SQLAlchemy model instance to dict."""
    if obj is None:
        return None
    
    result = {}
    mapper = inspect(obj.__class__)
    
    for column in mapper.columns:
        value = getattr(obj, column.key, None)
        
        if isinstance(value, datetime):
            result[column.key] = _iso(value)
        elif hasattr(value, 'value'):  # Enum
            result[column.key] = value.value
        elif hasattr(value, '__float__'):  # Decimal
            result[column.key] = float(value)
        else:
            result[column.key] = value
    
    return result


def _deserialize_record(Model, data, update_existing=True):
    """Deserialize dict to model instance, creating or updating as needed."""
    if not data:
        return None
    
    external_id = data.get('external_id')
    
    # Find existing by external_id
    obj = None
    if external_id and hasattr(Model, 'external_id'):
        obj = Model.query.filter_by(external_id=external_id).first()
    
    if obj is None:
        obj = Model()
        db.session.add(obj)
    elif not update_existing:
        return obj
    
    # Get column info
    mapper = inspect(Model)
    column_keys = {c.key for c in mapper.columns}
    
    for key, value in data.items():
        if key not in column_keys or key == 'id':
            continue
        
        column = mapper.columns.get(key)
        if column is None:
            continue
        
        # Handle datetime
        if hasattr(column.type, 'python_type'):
            try:
                if column.type.python_type == datetime:
                    value = _parse_iso(value)
            except Exception:
                pass
        
        # Handle enums
        if key in ENUM_MAPPINGS and value:
            value_lower = str(value).lower()
            if value_lower in ENUM_MAPPINGS[key]:
                value = ENUM_MAPPINGS[key][value_lower]
        
        try:
            setattr(obj, key, value)
        except Exception:
            pass
    
    return obj


# ============================================================================
# PUSH ENDPOINT - Edge → Cloud
# ============================================================================

@sync_api.route('/api/sync/push', methods=['POST'])
def sync_push():
    """
    Cloud endpoint: Edge pushes transactional data.
    Supports both legacy (orders only) and new (multi-model) formats.
    """
    if not _auth_ok():
        return jsonify({'success': False, 'error': 'unauthorized'}), 401

    payload = request.get_json(silent=True) or {}
    
    # Detect format: new format has 'model' key, legacy has 'orders' key
    model_name = payload.get('model')
    
    if model_name:
        # New multi-model format
        return _handle_multi_model_push(payload)
    else:
        # Legacy format (orders only)
        return _handle_legacy_push(payload)


def _handle_multi_model_push(payload):
    """Handle new multi-model push format."""
    model_name = payload.get('model')
    records = payload.get('records', [])
    
    if model_name not in MODEL_REGISTRY:
        return jsonify({'success': False, 'error': f'Unknown model: {model_name}'}), 400
    
    if not isinstance(records, list):
        return jsonify({'success': False, 'error': 'records must be list'}), 400
    
    Model = MODEL_REGISTRY[model_name]
    created = 0
    updated = 0
    errors = []
    
    for record_data in records:
        try:
            external_id = record_data.get('external_id')
            if not external_id:
                errors.append({'error': 'missing external_id'})
                continue
            
            # Check if exists
            existing = None
            if hasattr(Model, 'external_id'):
                existing = Model.query.filter_by(external_id=external_id).first()
            
            obj = _deserialize_record(Model, record_data)
            
            if existing:
                updated += 1
            else:
                created += 1
            
            # Handle nested data for Orders
            if model_name == 'Order' and 'items' in record_data:
                _sync_order_items(obj, record_data.get('items', []))
            if model_name == 'Order' and 'payments' in record_data:
                _sync_order_payments(obj, record_data.get('payments', []))
            
            db.session.flush()
            
        except Exception as e:
            errors.append({'external_id': record_data.get('external_id'), 'error': str(e)})
            current_app.logger.warning(f"Push error for {model_name}: {e}")
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'commit failed: {e}'}), 500
    
    current_app.logger.info(f"Sync push {model_name}: created={created} updated={updated}")
    
    return jsonify({
        'success': True,
        'model': model_name,
        'created': created,
        'updated': updated,
        'errors': errors if errors else None
    })


def _sync_order_items(order, items_data):
    """Sync order items from push data."""
    for item_data in items_data:
        ext_id = item_data.get('external_id')
        if not ext_id:
            continue
        
        item = OrderItem.query.filter_by(external_id=ext_id).first()
        if item is None:
            item = OrderItem()
            item.order_id = order.id
            db.session.add(item)
        
        # Update fields
        for key in ['quantity', 'unit_price', 'total_price', 'notes', 'is_deleted', 
                    'menu_item_id', 'external_id', 'modifiers_total_price']:
            if key in item_data:
                try:
                    setattr(item, key, item_data[key])
                except Exception:
                    pass


def _sync_order_payments(order, payments_data):
    """Sync order payments from push data."""
    for pay_data in payments_data:
        ext_id = pay_data.get('external_id')
        if not ext_id:
            continue
        
        payment = Payment.query.filter_by(external_id=ext_id).first() if hasattr(Payment, 'external_id') else None
        if payment is None:
            payment = Payment()
            payment.order_id = order.id
            db.session.add(payment)
        
        for key in ['amount', 'payment_method', 'transaction_id', 'status']:
            if key in pay_data:
                value = pay_data[key]
                if key == 'payment_method' and value:
                    value = ENUM_MAPPINGS.get('payment_method', {}).get(str(value).lower(), value)
                try:
                    setattr(payment, key, value)
                except Exception:
                    pass


def _handle_legacy_push(payload):
    """Handle legacy push format (orders only) for backward compatibility."""
    orders = payload.get('orders', [])
    
    if not isinstance(orders, list):
        return jsonify({'success': False, 'error': 'invalid payload'}), 400
    
    created = 0
    merged = 0
    
    for o in orders:
        ext_id = (o or {}).get('external_id')
        if not ext_id:
            continue
        
        try:
            # Map status
            raw_status = (o.get('status') or '').lower()
            st = OrderStatus.PENDING
            if raw_status == 'paid':
                st = OrderStatus.PAID
            elif raw_status == 'cancelled':
                st = OrderStatus.CANCELLED
            
            obj = Order.query.filter_by(external_id=ext_id).first()
            if obj is None:
                obj = Order(
                    external_id=ext_id,
                    order_number=o.get('order_number') or f"EDGE-{ext_id[:8]}",
                    total_amount=o.get('total_amount') or 0,
                    branch_id=o.get('branch_id'),
                    status=st,
                )
                db.session.add(obj)
                created += 1
            else:
                merged += 1
            
            obj.total_amount = o.get('total_amount') or obj.total_amount
            obj.status = st
            
            try:
                if o.get('created_at'):
                    obj.created_at = _parse_iso(o.get('created_at'))
                if o.get('paid_at'):
                    obj.paid_at = _parse_iso(o.get('paid_at'))
            except Exception:
                pass
            
            # Sync items if present
            if 'items' in o:
                _sync_order_items(obj, o['items'])
            
            note_tag = "[EDGE_SYNC]"
            if not (obj.notes or '').startswith(note_tag):
                obj.notes = f"{note_tag} Synced from Edge."
            
            db.session.flush()
            
        except Exception as e:
            current_app.logger.warning(f"Order merge failed for {ext_id}: {e}")
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.warning(f"Commit failed: {e}")
    
    return jsonify({'success': True, 'created': created, 'merged': merged})


# ============================================================================
# PULL ENDPOINT - Cloud → Edge
# ============================================================================

@sync_api.route('/api/sync/pull', methods=['GET'])
def sync_pull():
    """
    Cloud endpoint: Edge pulls reference/config data.
    Query params:
      - model: Model name to pull (required)
      - since: ISO timestamp to get records updated since (optional)
    """
    if not _auth_ok():
        return jsonify({'success': False, 'error': 'unauthorized'}), 401
    
    model_name = request.args.get('model')
    since_str = request.args.get('since')
    
    if not model_name:
        return jsonify({'success': False, 'error': 'model parameter required'}), 400
    
    if model_name not in MODEL_REGISTRY:
        return jsonify({'success': False, 'error': f'Unknown model: {model_name}'}), 400
    
    Model = MODEL_REGISTRY[model_name]
    
    try:
        query = Model.query
        
        # Filter by updated_at if since provided and model has it
        if since_str and hasattr(Model, 'updated_at'):
            since = _parse_iso(since_str)
            if since:
                query = query.filter(Model.updated_at > since)
        
        # Limit results to prevent overload
        records = query.limit(500).all()
        
        # Serialize
        serialized = [_serialize_record(r) for r in records]
        
        current_app.logger.info(f"Sync pull {model_name}: {len(serialized)} records")
        
        return jsonify({
            'success': True,
            'model': model_name,
            'records': serialized,
            'count': len(serialized),
            'timestamp': _iso(datetime.utcnow())
        })
        
    except Exception as e:
        current_app.logger.error(f"Sync pull failed for {model_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# HEALTH CHECK
# ============================================================================

@sync_api.route('/api/sync/ping', methods=['GET'])
def sync_ping():
    """Quick auth check endpoint: returns 200 if token validated, else 401."""
    if _auth_ok():
        return jsonify({'success': True, 'status': 'ok'}), 200
    return jsonify({'success': False, 'error': 'unauthorized'}), 401


@sync_api.route('/api/sync/status', methods=['GET'])
def sync_status():
    """Get sync system status (no auth required for monitoring)."""
    return jsonify({
        'success': True,
        'timestamp': _iso(datetime.utcnow()),
        'models_available': list(MODEL_REGISTRY.keys())
    })
