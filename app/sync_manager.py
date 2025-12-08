"""
Comprehensive Sync Manager for Hybrid Offline/Online POS System

This module provides bidirectional sync between local SQLite (edge) and
cloud PostgreSQL (Render) with:
- Non-blocking background sync (doesn't affect app performance)
- Secure token-based authentication
- Delta sync (only changes since last sync)
- Conflict resolution (last-write-wins for transactional, cloud-wins for config)
- Full data integrity (no missing data)
"""

import os
import uuid
import json
import threading
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Type
import requests
from flask import current_app
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app import db


# ============================================================================
# SYNC CONFIGURATION
# ============================================================================

SYNC_INTERVAL_SECONDS = int(os.getenv('EDGE_SYNC_INTERVAL_SECONDS', '30'))

# Models that push from Edge → Cloud (transactional data created locally)
PUSH_MODELS = [
    'Order', 'OrderItem', 'Payment', 
    'KitchenOrder', 'KitchenOrderItem',
    'CashierSession', 'ManualCardPayment', 
    'OrderEditHistory', 'Customer',
    'WaiterCashierAssignment'
]

# Models that pull from Cloud → Edge (reference/config data)
PULL_MODELS = [
    'Branch', 'User', 'UserBranchAssignment',
    'Category', 'MenuItem', 'Table',
    'DeliveryCompany', 'Kitchen',
    'CategoryKitchenAssignment', 'CategorySpecialItemAssignment',
    'AdminPinCode', 'CashierPin', 'AppSettings', 'InventoryItem'
]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _iso(dt) -> Optional[str]:
    """Convert datetime to ISO format string."""
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(iso_str) -> Optional[datetime]:
    """Parse ISO format string to datetime."""
    if not iso_str:
        return None
    try:
        # Handle various ISO formats
        if iso_str.endswith('Z'):
            iso_str = iso_str[:-1] + '+00:00'
        return datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return None


def _ensure_external_id(obj) -> str:
    """Ensure object has an external_id, generate if missing."""
    if not hasattr(obj, 'external_id') or not obj.external_id:
        obj.external_id = str(uuid.uuid4())
        try:
            db.session.flush()
        except Exception:
            pass
    return obj.external_id


def _get_model_class(model_name: str):
    """Get SQLAlchemy model class by name."""
    from app import models
    return getattr(models, model_name, None)


def _get_sync_headers() -> Dict[str, str]:
    """Get headers for sync API requests."""
    token = os.getenv('SYNC_API_TOKEN', '').strip()
    return {
        'Content-Type': 'application/json',
        'X-Edge-Token': token
    }


def _get_cloud_url(endpoint: str) -> str:
    """Get cloud API URL for sync endpoint."""
    base_url = os.getenv('CLOUD_SYNC_BASE_URL', '').strip().rstrip('/')
    return f"{base_url}/api/sync/{endpoint}"


# ============================================================================
# SERIALIZATION - Convert SQLAlchemy objects to JSON-safe dicts
# ============================================================================

def serialize_model(obj, include_relations: List[str] = None) -> Dict[str, Any]:
    """
    Serialize a SQLAlchemy model instance to a dictionary.
    Includes all columns and optionally specified relationships.
    """
    if obj is None:
        return None
    
    result = {}
    mapper = inspect(obj.__class__)
    
    # Serialize all columns
    for column in mapper.columns:
        value = getattr(obj, column.key, None)
        
        # Handle special types
        if isinstance(value, datetime):
            result[column.key] = _iso(value)
        elif hasattr(value, 'value'):  # Enum
            result[column.key] = value.value
        elif hasattr(value, '__decimal__'):  # Decimal
            result[column.key] = float(value)
        else:
            result[column.key] = value
    
    # Ensure external_id exists
    if 'external_id' in result and not result['external_id']:
        result['external_id'] = _ensure_external_id(obj)
    
    # Serialize specified relationships
    if include_relations:
        for rel_name in include_relations:
            rel_value = getattr(obj, rel_name, None)
            if rel_value is not None:
                if hasattr(rel_value, 'all'):  # Dynamic relationship
                    result[rel_name] = [serialize_model(item) for item in rel_value.all()]
                elif hasattr(rel_value, '__iter__') and not isinstance(rel_value, str):
                    result[rel_name] = [serialize_model(item) for item in rel_value]
                else:
                    result[rel_name] = serialize_model(rel_value)
    
    return result


def serialize_order_complete(order) -> Dict[str, Any]:
    """Serialize an Order with all related data for complete sync."""
    data = serialize_model(order)
    
    # Include order items
    items = []
    for item in list(order.order_items):
        item_data = serialize_model(item)
        # Include menu item name for reference
        if item.menu_item:
            item_data['menu_item_name'] = item.menu_item.name
        items.append(item_data)
    data['items'] = items
    
    # Include payments
    payments = []
    for payment in list(order.payments):
        payments.append(serialize_model(payment))
    data['payments'] = payments
    
    return data


# ============================================================================
# DESERIALIZATION - Convert JSON dicts back to SQLAlchemy objects
# ============================================================================

def deserialize_to_model(Model, data: Dict[str, Any], update_existing: bool = True):
    """
    Deserialize a dictionary to a SQLAlchemy model instance.
    If update_existing is True, will find and update existing record by external_id.
    """
    if not data:
        return None
    
    external_id = data.get('external_id')
    
    # Try to find existing record
    obj = None
    if external_id and hasattr(Model, 'external_id'):
        obj = Model.query.filter_by(external_id=external_id).first()
    
    if obj is None:
        obj = Model()
        db.session.add(obj)
    elif not update_existing:
        return obj  # Already exists, don't update
    
    # Get model columns
    mapper = inspect(Model)
    column_names = {c.key for c in mapper.columns}
    
    # Update fields
    for key, value in data.items():
        if key not in column_names:
            continue
        if key == 'id':
            continue  # Don't overwrite local ID
        
        column = mapper.columns.get(key)
        if column is None:
            continue
        
        # Handle datetime fields
        if hasattr(column.type, 'python_type') and column.type.python_type == datetime:
            value = _parse_iso(value)
        
        # Handle enum fields
        col_type = column.type
        if hasattr(col_type, 'enum_class') and col_type.enum_class:
            if value is not None:
                try:
                    value = col_type.enum_class(value)
                except (ValueError, KeyError):
                    pass
        
        setattr(obj, key, value)
    
    return obj


# ============================================================================
# PUSH SYNC - Edge → Cloud
# ============================================================================

def get_unsynced_records(Model, limit: int = 50) -> List:
    """Get records that need to be synced to cloud."""
    if not hasattr(Model, 'synced_at'):
        return []
    
    query = Model.query.filter(
        (Model.synced_at.is_(None)) | 
        (Model.updated_at > Model.synced_at)
    )
    
    if hasattr(Model, 'updated_at'):
        query = query.order_by(Model.updated_at.asc())
    
    return query.limit(limit).all()


def push_model_data(app, model_name: str) -> Dict[str, Any]:
    """Push unsynced records of a specific model to cloud."""
    Model = _get_model_class(model_name)
    if Model is None:
        return {'success': False, 'error': f'Model {model_name} not found'}
    
    records = get_unsynced_records(Model)
    if not records:
        return {'success': True, 'pushed': 0, 'model': model_name}
    
    # Serialize records
    if model_name == 'Order':
        # Orders need complete serialization with items and payments
        payload = [serialize_order_complete(r) for r in records]
    else:
        payload = [serialize_model(r) for r in records]
    
    # Push to cloud
    try:
        url = _get_cloud_url('push')
        data = {
            'model': model_name,
            'records': payload
        }
        
        resp = requests.post(
            url, 
            data=json.dumps(data), 
            headers=_get_sync_headers(),
            timeout=30
        )
        
        if resp.status_code != 200:
            return {'success': False, 'http': resp.status_code, 'model': model_name}
        
        result = resp.json()
        if not result.get('success'):
            return {'success': False, 'cloud': result, 'model': model_name}
        
        # Mark records as synced
        now = datetime.utcnow()
        for record in records:
            record.synced_at = now
        db.session.commit()
        
        app.logger.info(f"Sync pushed {len(records)} {model_name} records")
        return {'success': True, 'pushed': len(records), 'model': model_name}
        
    except requests.Timeout:
        return {'success': False, 'error': 'timeout', 'model': model_name}
    except Exception as e:
        db.session.rollback()
        return {'success': False, 'error': str(e), 'model': model_name}


def push_all_models(app) -> Dict[str, Any]:
    """Push all unsynced data from all push models."""
    results = {}
    total_pushed = 0
    
    for model_name in PUSH_MODELS:
        try:
            result = push_model_data(app, model_name)
            results[model_name] = result
            if result.get('success') and result.get('pushed', 0) > 0:
                total_pushed += result['pushed']
        except Exception as e:
            results[model_name] = {'success': False, 'error': str(e)}
            app.logger.warning(f"Push failed for {model_name}: {e}")
    
    return {'success': True, 'total_pushed': total_pushed, 'details': results}


# ============================================================================
# PULL SYNC - Cloud → Edge
# ============================================================================

def pull_model_data(app, model_name: str, since: datetime = None) -> Dict[str, Any]:
    """Pull updated records of a specific model from cloud."""
    Model = _get_model_class(model_name)
    if Model is None:
        return {'success': False, 'error': f'Model {model_name} not found'}
    
    try:
        url = _get_cloud_url('pull')
        params = {'model': model_name}
        if since:
            params['since'] = _iso(since)
        
        resp = requests.get(
            url,
            params=params,
            headers=_get_sync_headers(),
            timeout=30
        )
        
        if resp.status_code != 200:
            return {'success': False, 'http': resp.status_code, 'model': model_name}
        
        result = resp.json()
        if not result.get('success'):
            return {'success': False, 'cloud': result, 'model': model_name}
        
        records = result.get('records', [])
        updated = 0
        
        for record_data in records:
            try:
                obj = deserialize_to_model(Model, record_data)
                if obj:
                    updated += 1
            except Exception as e:
                app.logger.warning(f"Failed to deserialize {model_name}: {e}")
        
        db.session.commit()
        
        if updated > 0:
            app.logger.info(f"Sync pulled {updated} {model_name} records")
        
        return {'success': True, 'pulled': updated, 'model': model_name}
        
    except requests.Timeout:
        return {'success': False, 'error': 'timeout', 'model': model_name}
    except Exception as e:
        db.session.rollback()
        return {'success': False, 'error': str(e), 'model': model_name}


def pull_all_models(app, since: datetime = None) -> Dict[str, Any]:
    """Pull all updated data from cloud for all pull models."""
    results = {}
    total_pulled = 0
    
    for model_name in PULL_MODELS:
        try:
            result = pull_model_data(app, model_name, since)
            results[model_name] = result
            if result.get('success') and result.get('pulled', 0) > 0:
                total_pulled += result['pulled']
        except Exception as e:
            results[model_name] = {'success': False, 'error': str(e)}
            app.logger.warning(f"Pull failed for {model_name}: {e}")
    
    return {'success': True, 'total_pulled': total_pulled, 'details': results}


# ============================================================================
# FULL SYNC CYCLE
# ============================================================================

def run_full_sync(app) -> Dict[str, Any]:
    """
    Run a complete sync cycle:
    1. Push local changes to cloud
    2. Pull cloud changes to local
    """
    push_result = push_all_models(app)
    pull_result = pull_all_models(app)
    
    return {
        'success': True,
        'push': push_result,
        'pull': pull_result,
        'timestamp': _iso(datetime.utcnow())
    }


# ============================================================================
# BACKGROUND SYNC WORKER
# ============================================================================

class SyncWorker:
    """
    Background sync worker that runs in a separate thread.
    Non-blocking, doesn't affect main app performance.
    """
    
    def __init__(self, app):
        self.app = app
        self._stop_event = threading.Event()
        self._thread = None
        self._last_sync = None
        self._sync_count = 0
        self._error_count = 0
    
    def start(self):
        """Start the background sync worker."""
        if self._thread is not None and self._thread.is_alive():
            return
        
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()
        self.app.logger.info("Sync worker started")
    
    def stop(self):
        """Stop the background sync worker."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.app.logger.info("Sync worker stopped")
    
    def _worker_loop(self):
        """Main worker loop - runs sync cycles at configured interval."""
        with self.app.app_context():
            self.app.logger.info(
                f"Sync worker running (interval: {SYNC_INTERVAL_SECONDS}s)"
            )
            
            while not self._stop_event.is_set():
                try:
                    self._run_sync_cycle()
                except Exception as e:
                    self._error_count += 1
                    self.app.logger.warning(f"Sync cycle error: {e}")
                
                # Wait for next cycle or stop signal
                self._stop_event.wait(timeout=SYNC_INTERVAL_SECONDS)
    
    def _run_sync_cycle(self):
        """Execute one sync cycle."""
        base_url = os.getenv('CLOUD_SYNC_BASE_URL', '').strip()
        token = os.getenv('SYNC_API_TOKEN', '').strip()
        
        if not base_url or not token:
            return  # Sync not configured
        
        # Run full sync
        result = run_full_sync(self.app)
        
        self._last_sync = datetime.utcnow()
        self._sync_count += 1
        
        # Log summary
        push_count = result.get('push', {}).get('total_pushed', 0)
        pull_count = result.get('pull', {}).get('total_pulled', 0)
        
        if push_count > 0 or pull_count > 0:
            self.app.logger.info(
                f"Sync cycle #{self._sync_count}: pushed={push_count}, pulled={pull_count}"
            )
    
    def get_status(self) -> Dict[str, Any]:
        """Get current sync worker status."""
        return {
            'running': self._thread is not None and self._thread.is_alive(),
            'last_sync': _iso(self._last_sync),
            'sync_count': self._sync_count,
            'error_count': self._error_count,
            'interval_seconds': SYNC_INTERVAL_SECONDS
        }


# Global sync worker instance
_sync_worker: Optional[SyncWorker] = None


def start_sync_worker(app):
    """Start the global sync worker."""
    global _sync_worker
    
    if not app.config.get('EDGE_MODE'):
        return  # Only run in edge mode
    
    if _sync_worker is not None:
        return  # Already started
    
    _sync_worker = SyncWorker(app)
    _sync_worker.start()


def stop_sync_worker():
    """Stop the global sync worker."""
    global _sync_worker
    
    if _sync_worker:
        _sync_worker.stop()
        _sync_worker = None


def get_sync_status() -> Dict[str, Any]:
    """Get sync worker status."""
    if _sync_worker:
        return _sync_worker.get_status()
    return {'running': False}
