from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models import AppSettings, Order, OrderStatus
from sqlalchemy import text
from datetime import datetime
import json

sync_api = Blueprint('sync_api', __name__)


def _auth_ok():
    token_header = request.headers.get('X-Edge-Token') or request.headers.get('Authorization', '').replace('Bearer ', '')
    expected = current_app.config.get('SYNC_API_TOKEN') or AppSettings.get_value('sync_api_token') or None
    if not expected:
        # If no token is configured, deny by default
        return False
    return str(token_header).strip() == str(expected).strip()


@sync_api.route('/api/sync/push', methods=['POST'])
def sync_push():
    """
    Cloud endpoint: Edge pushes unsynced orders as denormalized JSON payloads.
    We store them in a simple intake table to avoid FK mapping issues.
    """
    if not _auth_ok():
        return jsonify({'success': False, 'error': 'unauthorized'}), 401

    payload = request.get_json(silent=True) or {}
    orders = payload.get('orders', [])

    if not isinstance(orders, list):
        return jsonify({'success': False, 'error': 'invalid payload'}), 400

    # Ensure intake table exists (Postgres JSON)
    try:
        with db.engine.begin() as conn:
            conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS synced_orders (
                  id SERIAL PRIMARY KEY,
                  external_id VARCHAR(64) UNIQUE,
                  branch_id INTEGER,
                  order_number VARCHAR(64),
                  total_amount NUMERIC(10,2),
                  status VARCHAR(32),
                  created_at TIMESTAMP,
                  paid_at TIMESTAMP,
                  payload JSON,
                  received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            ))
    except Exception as e:
        current_app.logger.error(f"Failed creating synced_orders table: {e}")
        return jsonify({'success': False, 'error': 'storage init failed'}), 500

    created = 0
    skipped = 0
    results = []
    merged = 0

    for o in orders:
        ext_id = (o or {}).get('external_id')
        if not ext_id:
            results.append({'external_id': None, 'status': 'missing_external_id'})
            skipped += 1
            continue
        try:
            with db.engine.begin() as conn:
                res = conn.execute(text(
                    """
                    INSERT INTO synced_orders (external_id, branch_id, order_number, total_amount, status, created_at, paid_at, payload)
                    VALUES (:external_id, :branch_id, :order_number, :total_amount, :status, :created_at, :paid_at, CAST(:payload AS JSON))
                    ON CONFLICT (external_id) DO NOTHING
                    """
                ), {
                    'external_id': ext_id,
                    'branch_id': o.get('branch_id'),
                    'order_number': o.get('order_number'),
                    'total_amount': o.get('total_amount'),
                    'status': o.get('status'),
                    'created_at': o.get('created_at'),
                    'paid_at': o.get('paid_at'),
                    'payload': json.dumps(o)
                })
                # Confirm existence
                check = conn.execute(text("SELECT 1 FROM synced_orders WHERE external_id = :eid"), {'eid': ext_id}).fetchone()
                if check:
                    created += 1
                    results.append({'external_id': ext_id, 'status': 'created'})
                else:
                    skipped += 1
                    results.append({'external_id': ext_id, 'status': 'exists'})
        except Exception as e:
            current_app.logger.error(f"sync_push insert failed for {ext_id}: {e}")
            results.append({'external_id': ext_id, 'status': 'error'})

        # Best-effort merge into primary orders table (header only)
        try:
            # Map status string to enum safely
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

            # Update fields
            obj.total_amount = o.get('total_amount') or obj.total_amount
            obj.status = st
            # Timestamps
            try:
                obj.created_at = o.get('created_at') or obj.created_at
                obj.paid_at = o.get('paid_at') or obj.paid_at
            except Exception:
                pass

            # Tag as cloud-merged
            note_tag = "[EDGE_SYNC]"
            if not (obj.notes or '').startswith(note_tag):
                obj.notes = f"{note_tag} Imported header from Edge."
            merged += 1
            db.session.flush()
        except Exception as e_merge:
            current_app.logger.warning(f"Order merge skipped for {ext_id}: {e_merge}")

    try:
        db.session.commit()
    except Exception as e_commit:
        db.session.rollback()
        current_app.logger.warning(f"Commit failed after merges: {e_commit}")

    return jsonify({'success': True, 'created': created, 'skipped': skipped, 'merged': merged, 'results': results})
