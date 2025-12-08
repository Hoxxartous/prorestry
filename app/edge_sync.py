"""
Edge Sync Worker - Background sync between local SQLite and cloud PostgreSQL

This module provides:
- Background sync worker thread that runs periodically
- Push sync: Local transactional data → Cloud
- Pull sync: Cloud reference data → Local
- Non-blocking, performance-optimized sync

Usage:
    from app.edge_sync import start_edge_sync_worker
    start_edge_sync_worker(app)  # Call during app initialization in edge mode
"""

import os
import uuid
import json
import threading
import time
from datetime import datetime
import requests
from flask import current_app

from app import db
from app.models import (
    Order, OrderItem, Payment, Customer,
    CashierSession, KitchenOrder, KitchenOrderItem,
    ManualCardPayment, OrderEditHistory, WaiterCashierAssignment,
    Branch, User, UserBranchAssignment, Category, MenuItem, Table,
    DeliveryCompany, Kitchen, CategoryKitchenAssignment,
    CategorySpecialItemAssignment, AdminPinCode, CashierPin,
    AppSettings, InventoryItem
)


# ============================================================================
# CONFIGURATION
# ============================================================================

SYNC_INTERVAL = int(os.getenv('EDGE_SYNC_INTERVAL_SECONDS', '30'))

# Headers for API requests
ESSENTIAL_HEADERS = {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

# Models to push from edge to cloud (transactional data)
PUSH_MODELS = [
    ('Order', Order, True),           # (name, class, include_relations)
    ('Customer', Customer, False),
    ('CashierSession', CashierSession, False),
    ('KitchenOrder', KitchenOrder, False),
]

# Models to pull from cloud to edge (reference/config data)
PULL_MODELS = [
    ('Branch', Branch),
    ('User', User),
    ('Category', Category),
    ('MenuItem', MenuItem),
    ('Table', Table),
    ('DeliveryCompany', DeliveryCompany),
    ('Kitchen', Kitchen),
    ('AdminPinCode', AdminPinCode),
    ('CashierPin', CashierPin),
    ('AppSettings', AppSettings),
]


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


def _ensure_external_id(obj):
    """Ensure object has an external_id."""
    if hasattr(obj, 'external_id') and not obj.external_id:
        obj.external_id = str(uuid.uuid4())
        try:
            db.session.flush()
        except Exception:
            pass
    return getattr(obj, 'external_id', None)


def _serialize_record(obj):
    """Serialize SQLAlchemy object to dict."""
    if obj is None:
        return None
    
    from sqlalchemy import inspect
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


def _serialize_order_complete(order):
    """Serialize Order with items and payments."""
    _ensure_external_id(order)
    data = _serialize_record(order)
    
    # Include items
    items = []
    for item in list(order.order_items):
        _ensure_external_id(item)
        item_data = _serialize_record(item)
        if item.menu_item:
            item_data['menu_item_name'] = item.menu_item.name
        items.append(item_data)
    data['items'] = items
    
    # Include payments
    payments = []
    for payment in list(order.payments):
        _ensure_external_id(payment)
        payments.append(_serialize_record(payment))
    data['payments'] = payments
    
    return data


# ============================================================================
# PUSH SYNC - Edge → Cloud
# ============================================================================

def push_unsynced_orders(app):
    """Push unsynced orders to cloud. Returns summary dict."""
    base_url = os.getenv('CLOUD_SYNC_BASE_URL', '').strip()
    token = os.getenv('SYNC_API_TOKEN', '').strip() or app.config.get('SYNC_API_TOKEN')

    if not base_url or not token:
        app.logger.debug('Edge sync disabled: missing CLOUD_SYNC_BASE_URL or SYNC_API_TOKEN')
        return {'success': False, 'reason': 'not_configured'}

    # Log config once
    if not getattr(app, '_edge_sync_logged_cfg', False):
        app.logger.info(
            f"Edge sync configured: base_url={base_url.rstrip('/')} token_len={len(token)}"
        )
        app._edge_sync_logged_cfg = True

    url = base_url.rstrip('/') + '/api/sync/push'

    # Count orders for logging
    try:
        total_orders = Order.query.count()
        unsynced_count = Order.query.filter(
            (Order.synced_at.is_(None)) | (Order.updated_at > Order.synced_at)
        ).count()
        if total_orders > 0:
            app.logger.debug(f"Edge sync check: total_orders={total_orders}, unsynced={unsynced_count}")
    except Exception as e:
        app.logger.warning(f"Edge sync count query failed: {e}")

    # Find unsynced orders
    orders = Order.query.filter(
        (Order.synced_at.is_(None)) | (Order.updated_at > Order.synced_at)
    ).order_by(Order.updated_at.asc()).limit(50).all()

    if not orders:
        return {'success': True, 'pushed': 0}

    # Serialize orders with items and payments
    payload_orders = [_serialize_order_complete(o) for o in orders]

    headers = dict(ESSENTIAL_HEADERS)
    headers['X-Edge-Token'] = token

    try:
        resp = requests.post(url, data=json.dumps({'orders': payload_orders}), 
                           headers=headers, timeout=30)
        
        if resp.status_code != 200:
            app.logger.warning(f'Edge sync push failed: HTTP {resp.status_code} - {resp.text[:200]}')
            return {'success': False, 'http': resp.status_code}
        
        res = resp.json()
        if not res.get('success'):
            app.logger.warning(f'Edge sync push rejected: {res}')
            return {'success': False, 'cloud': res}

        # Mark orders as synced
        now = datetime.utcnow()
        for o in orders:
            o.synced_at = now
        db.session.commit()
        
        app.logger.info(f'Edge sync SUCCESS: pushed {len(orders)} orders to cloud')
        return {'success': True, 'pushed': len(orders)}
        
    except requests.Timeout:
        app.logger.warning('Edge sync push timeout')
        return {'success': False, 'error': 'timeout'}
    except Exception as e:
        app.logger.warning(f'Edge sync push exception: {e}')
        db.session.rollback()
        return {'success': False, 'error': str(e)}


def push_model_data(app, model_name, Model):
    """Push unsynced records of a specific model."""
    base_url = os.getenv('CLOUD_SYNC_BASE_URL', '').strip()
    token = os.getenv('SYNC_API_TOKEN', '').strip()
    
    if not base_url or not token:
        return {'success': False, 'reason': 'not_configured'}
    
    if not hasattr(Model, 'synced_at') or not hasattr(Model, 'updated_at'):
        return {'success': False, 'reason': 'model_not_syncable'}
    
    # Find unsynced records
    records = Model.query.filter(
        (Model.synced_at.is_(None)) | (Model.updated_at > Model.synced_at)
    ).limit(50).all()
    
    if not records:
        return {'success': True, 'pushed': 0}
    
    # Serialize
    payload = [_serialize_record(r) for r in records]
    
    url = base_url.rstrip('/') + '/api/sync/push'
    headers = dict(ESSENTIAL_HEADERS)
    headers['X-Edge-Token'] = token
    
    try:
        data = {'model': model_name, 'records': payload}
        resp = requests.post(url, data=json.dumps(data), headers=headers, timeout=30)
        
        if resp.status_code != 200:
            return {'success': False, 'http': resp.status_code}
        
        # Mark as synced
        now = datetime.utcnow()
        for r in records:
            r.synced_at = now
        db.session.commit()
        
        if len(records) > 0:
            app.logger.info(f'Edge sync: pushed {len(records)} {model_name} records')
        
        return {'success': True, 'pushed': len(records)}
        
    except Exception as e:
        db.session.rollback()
        return {'success': False, 'error': str(e)}


# ============================================================================
# PULL SYNC - Cloud → Edge
# ============================================================================

def pull_model_data(app, model_name, Model):
    """Pull updated records from cloud."""
    base_url = os.getenv('CLOUD_SYNC_BASE_URL', '').strip()
    token = os.getenv('SYNC_API_TOKEN', '').strip()
    
    if not base_url or not token:
        return {'success': False, 'reason': 'not_configured'}
    
    url = base_url.rstrip('/') + '/api/sync/pull'
    headers = dict(ESSENTIAL_HEADERS)
    headers['X-Edge-Token'] = token
    
    try:
        resp = requests.get(url, params={'model': model_name}, headers=headers, timeout=30)
        
        if resp.status_code != 200:
            return {'success': False, 'http': resp.status_code}
        
        result = resp.json()
        if not result.get('success'):
            return {'success': False, 'cloud': result}
        
        records = result.get('records', [])
        updated = 0
        
        for record_data in records:
            try:
                external_id = record_data.get('external_id')
                if not external_id:
                    continue
                
                # Find or create
                obj = Model.query.filter_by(external_id=external_id).first() if hasattr(Model, 'external_id') else None
                if obj is None:
                    obj = Model()
                    db.session.add(obj)
                
                # Update fields
                from sqlalchemy import inspect
                mapper = inspect(Model)
                column_keys = {c.key for c in mapper.columns}
                
                for key, value in record_data.items():
                    if key not in column_keys or key == 'id':
                        continue
                    try:
                        setattr(obj, key, value)
                    except Exception:
                        pass
                
                updated += 1
                
            except Exception as e:
                app.logger.warning(f"Pull deserialize error for {model_name}: {e}")
        
        db.session.commit()
        
        if updated > 0:
            app.logger.info(f'Edge sync: pulled {updated} {model_name} records')
        
        return {'success': True, 'pulled': updated}
        
    except Exception as e:
        db.session.rollback()
        return {'success': False, 'error': str(e)}


# ============================================================================
# SYNC WORKER
# ============================================================================

def _worker(app):
    """Background sync worker thread."""
    with app.app_context():
        app.logger.info('Starting Edge sync worker...')
        
        while True:
            try:
                # Push orders (primary sync)
                push_unsynced_orders(app)
                
                # Push other transactional models
                for model_name, Model, _ in PUSH_MODELS:
                    if model_name != 'Order':  # Orders already pushed above
                        try:
                            push_model_data(app, model_name, Model)
                        except Exception as e:
                            app.logger.debug(f"Push {model_name} skipped: {e}")
                
                # Pull reference data from cloud (less frequently)
                sync_count = getattr(app, '_edge_sync_count', 0)
                if sync_count % 5 == 0:  # Every 5th cycle (~2.5 min)
                    for model_name, Model in PULL_MODELS:
                        try:
                            pull_model_data(app, model_name, Model)
                        except Exception as e:
                            app.logger.debug(f"Pull {model_name} skipped: {e}")
                
                app._edge_sync_count = sync_count + 1
                
            except Exception as e:
                app.logger.warning(f'Edge sync worker loop error: {e}')
            
            time.sleep(SYNC_INTERVAL)


def start_edge_sync_worker(app):
    """Start the background sync worker (edge mode only)."""
    if not app.config.get('EDGE_MODE'):
        return
    
    # Only start once per process
    if getattr(app, '_edge_sync_started', False):
        return
    
    app._edge_sync_started = True
    app._edge_sync_count = 0
    
    t = threading.Thread(target=_worker, args=(app,), daemon=True)
    t.start()
