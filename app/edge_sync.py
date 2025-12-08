import os
import threading
import time
import uuid
import json
from datetime import datetime, timezone
import requests
from flask import current_app
from app import db
from app.models import Order, OrderItem


def _iso(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.astimezone(timezone.utc).isoformat()


def _serialize_order(order: Order):
    # Ensure external_id exists
    if not getattr(order, 'external_id', None):
        order.external_id = str(uuid.uuid4())
        # Flush but do not commit yet
        db.session.flush()

    items = []
    try:
        for it in list(order.order_items):
            items.append({
                'id': it.id,
                'menu_item_id': it.menu_item_id,
                'menu_item_name': getattr(it.menu_item, 'name', None),
                'quantity': int(it.quantity or 0),
                'unit_price': float(it.unit_price or 0),
                'total_price': float(it.total_price or 0),
                'modifiers_total_price': float(it.modifiers_total_price or 0),
                'notes': it.notes,
                'is_deleted': bool(it.is_deleted),
            })
    except Exception:
        # In worst-case, send without items
        items = []

    return {
        'external_id': order.external_id,
        'branch_id': order.branch_id,
        'order_number': order.order_number,
        'status': order.status.value if order.status else None,
        'total_amount': float(order.total_amount or 0),
        'created_at': _iso(order.created_at),
        'updated_at': _iso(order.updated_at),
        'paid_at': _iso(order.paid_at),
        'items': items,
    }


essential_headers = {
    'Content-Type': 'application/json'
}


def push_unsynced_orders(app):
    """Push unsynced orders (or updated ones) to cloud. Return summary dict."""
    base_url = os.getenv('CLOUD_SYNC_BASE_URL', '').strip()
    token = os.getenv('SYNC_API_TOKEN', '').strip() or app.config.get('SYNC_API_TOKEN')

    if not base_url or not token:
        app.logger.info('Edge sync disabled: missing CLOUD_SYNC_BASE_URL or SYNC_API_TOKEN')
        return {'success': False, 'reason': 'not_configured'}

    # Log minimal one-time config diagnostics (no secrets)
    if not getattr(app, '_edge_sync_logged_cfg', False):
        try:
            app.logger.info(
                f"Edge sync configured: base_url={base_url.rstrip('/')} token_len={len(token)}"
            )
        except Exception:
            pass
        app._edge_sync_logged_cfg = True

    url = base_url.rstrip('/') + '/api/sync/push'

    # Debug: count total orders and unsynced orders
    try:
        total_orders = Order.query.count()
        unsynced_count = Order.query.filter(
            (Order.synced_at.is_(None)) | (Order.updated_at > Order.synced_at)
        ).count()
        app.logger.info(f"Edge sync check: total_orders={total_orders}, unsynced={unsynced_count}")
    except Exception as e:
        app.logger.warning(f"Edge sync count query failed: {e}")

    # Find orders that are new or updated since last sync
    q = Order.query.filter(
        (Order.synced_at.is_(None)) | (Order.updated_at > Order.synced_at)
    ).order_by(Order.updated_at.asc()).limit(50)

    orders = q.all()
    if not orders:
        app.logger.info("Edge sync: No unsynced orders to push")
        return {'success': True, 'pushed': 0}

    # Serialize and ensure external_id exists
    payload_orders = []
    for o in orders:
        payload_orders.append(_serialize_order(o))

    data = {'orders': payload_orders}
    headers = dict(essential_headers)
    headers['X-Edge-Token'] = token

    try:
        resp = requests.post(url, data=json.dumps(data), headers=headers, timeout=15)
        if resp.status_code != 200:
            app.logger.warning(f'Edge sync push failed: HTTP {resp.status_code} - {resp.text[:200]}')
            return {'success': False, 'http': resp.status_code}
        res = resp.json()
        if not res.get('success'):
            app.logger.warning(f'Edge sync push rejected: {res}')
            return {'success': False, 'cloud': res}

        # Mark pushed orders as synced
        now = datetime.utcnow()
        for o in orders:
            o.synced_at = now
        db.session.commit()
        app.logger.info(f'Edge sync SUCCESS: pushed {len(orders)} orders to cloud')
        return {'success': True, 'pushed': len(orders)}
    except Exception as e:
        app.logger.warning(f'Edge sync push exception: {e}')
        db.session.rollback()
        return {'success': False, 'error': str(e)}


def _worker(app):
    with app.app_context():
        app.logger.info('Starting Edge sync worker...')
        while True:
            try:
                push_unsynced_orders(app)
            except Exception as e:
                app.logger.warning(f'Edge sync worker loop error: {e}')
            time.sleep(int(os.getenv('EDGE_SYNC_INTERVAL_SECONDS', '30')))


def start_edge_sync_worker(app):
    if not app.config.get('EDGE_MODE'):
        return
    # Only start once per process
    if getattr(app, '_edge_sync_started', False):
        return
    app._edge_sync_started = True
    t = threading.Thread(target=_worker, args=(app,), daemon=True)
    t.start()
