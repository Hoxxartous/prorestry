from flask import render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app import db, socketio
from app.kitchen import kitchen
from app.models import (
    Kitchen, KitchenOrder, KitchenOrderItem, KitchenOrderStatus,
    Order, OrderItem, Category, CategoryKitchenAssignment, User, UserRole, TimezoneManager, DeliveryCompany
)
from app.auth.decorators import login_required_with_role
from datetime import datetime, timedelta
from sqlalchemy import and_, or_

@kitchen.route('/dashboard')
@login_required
@login_required_with_role(UserRole.KITCHEN)
def dashboard():
    """Kitchen dashboard showing pending orders"""
    # Get the kitchen for current user
    user_kitchen = Kitchen.query.filter_by(
        kitchen_user_id=current_user.id,
        is_active=True
    ).first()
    
    if not user_kitchen:
        flash('No kitchen assigned to your account.', 'error')
        return redirect(url_for('auth.login'))
    
    # Get pending kitchen orders (grouped by order number)
    pending_kitchen_orders = KitchenOrder.query.filter_by(
        kitchen_id=user_kitchen.id
    ).filter(
        KitchenOrder.status.in_([KitchenOrderStatus.RECEIVED, KitchenOrderStatus.PREPARING])
    ).order_by(KitchenOrder.received_at.asc()).all()
    
    # Get ready orders (last 2 hours, grouped by order number)
    two_hours_ago = datetime.utcnow() - timedelta(hours=2)
    ready_kitchen_orders = KitchenOrder.query.filter_by(
        kitchen_id=user_kitchen.id,
        status=KitchenOrderStatus.READY
    ).filter(
        KitchenOrder.ready_at >= two_hours_ago
    ).order_by(KitchenOrder.ready_at.desc()).all()
    
    # Group orders by order_number (same logic as API)
    def group_kitchen_orders_by_number(kitchen_orders):
        grouped_orders = {}
        
        for kitchen_order in kitchen_orders:
            order_number = kitchen_order.order.order_number
            
            if order_number not in grouped_orders:
                grouped_orders[order_number] = kitchen_order
                # Add a combined_items property that includes all items from same order
                kitchen_order.combined_items = list(kitchen_order.kitchen_items)
                kitchen_order.combined_kitchen_order_ids = [kitchen_order.id]
            else:
                # Add items from this kitchen order to the existing grouped order
                existing_order = grouped_orders[order_number]
                existing_order.combined_items.extend(kitchen_order.kitchen_items)
                existing_order.combined_kitchen_order_ids.append(kitchen_order.id)
                
                # Update status to most advanced status
                if existing_order.status == KitchenOrderStatus.RECEIVED and kitchen_order.status in [KitchenOrderStatus.PREPARING, KitchenOrderStatus.READY]:
                    existing_order.status = kitchen_order.status
                elif existing_order.status == KitchenOrderStatus.PREPARING and kitchen_order.status == KitchenOrderStatus.READY:
                    existing_order.status = kitchen_order.status
        
        return list(grouped_orders.values())
    
    pending_orders = group_kitchen_orders_by_number(pending_kitchen_orders)
    ready_orders = group_kitchen_orders_by_number(ready_kitchen_orders)
    
    # Debug information
    assigned_categories = user_kitchen.get_assigned_categories()
    current_app.logger.info(f"Kitchen {user_kitchen.name} has {len(assigned_categories)} assigned categories: {[cat.name for cat in assigned_categories]}")
    
    return render_template('kitchen/dashboard.html',
                         kitchen=user_kitchen,
                         pending_orders=pending_orders,
                         ready_orders=ready_orders)

@kitchen.route('/orders')
@login_required
@login_required_with_role(UserRole.KITCHEN)
def orders():
    """Kitchen orders page with pagination"""
    # Get the kitchen for current user
    user_kitchen = Kitchen.query.filter_by(
        kitchen_user_id=current_user.id,
        is_active=True
    ).first()
    
    if not user_kitchen:
        flash('No kitchen assigned to your account.', 'error')
        return redirect(url_for('auth.login'))
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Get kitchen orders with pagination
    kitchen_orders = KitchenOrder.query.filter_by(
        kitchen_id=user_kitchen.id
    ).order_by(KitchenOrder.received_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('kitchen/orders.html',
                         kitchen=user_kitchen,
                         kitchen_orders=kitchen_orders)

@kitchen.route('/order/<int:order_id>')
@login_required
@login_required_with_role(UserRole.KITCHEN)
def order_details(order_id):
    """Kitchen order details"""
    # Get the kitchen for current user
    user_kitchen = Kitchen.query.filter_by(
        kitchen_user_id=current_user.id,
        is_active=True
    ).first()
    
    if not user_kitchen:
        flash('No kitchen assigned to your account.', 'error')
        return redirect(url_for('auth.login'))
    
    # Get kitchen order
    kitchen_order = KitchenOrder.query.filter_by(
        id=order_id,
        kitchen_id=user_kitchen.id
    ).first_or_404()
    
    return render_template('kitchen/order_details.html',
                         kitchen=user_kitchen,
                         kitchen_order=kitchen_order)

@kitchen.route('/update_status', methods=['POST'])
@login_required
@login_required_with_role(UserRole.KITCHEN)
def update_order_status():
    """Update kitchen order status - updates all kitchen orders for the same order number"""
    try:
        data = request.get_json()
        kitchen_order_id = data.get('kitchen_order_id')
        new_status = data.get('status')
        
        # Get the kitchen for current user
        user_kitchen = Kitchen.query.filter_by(
            kitchen_user_id=current_user.id,
            is_active=True
        ).first()
        
        if not user_kitchen:
            return jsonify({'success': False, 'message': 'No kitchen assigned to your account'})
        
        # Get the primary kitchen order
        primary_kitchen_order = KitchenOrder.query.filter_by(
            id=kitchen_order_id,
            kitchen_id=user_kitchen.id
        ).first()
        
        if not primary_kitchen_order:
            return jsonify({'success': False, 'message': 'Kitchen order not found'})
        
        # Validate status
        try:
            status_enum = KitchenOrderStatus(new_status)
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid status'})
        
        # Get all kitchen orders for the same order number in this kitchen
        order_number = primary_kitchen_order.order.order_number
        all_kitchen_orders = KitchenOrder.query.join(Order).filter(
            Order.order_number == order_number,
            KitchenOrder.kitchen_id == user_kitchen.id
        ).all()
        
        # Update status for all kitchen orders of the same order number
        for kitchen_order in all_kitchen_orders:
            kitchen_order.update_status(status_enum)
            # Also update all items in each kitchen order
            for item in kitchen_order.kitchen_items:
                item.update_status(status_enum)
        
        db.session.commit()
        
        # Emit real-time update to cashiers and waiters
        socketio.emit('kitchen_order_status_update', {
            'order_id': primary_kitchen_order.order_id,
            'kitchen_id': primary_kitchen_order.kitchen_id,
            'kitchen_name': user_kitchen.name,
            'order_number': order_number,
            'status': new_status,
            'updated_at': datetime.utcnow().isoformat()
        }, room=f'branch_{user_kitchen.branch_id}')
        
        return jsonify({
            'success': True,
            'message': f'Order {order_number} status updated to {status_enum.value}',
            'status': new_status
        })
        
    except Exception as e:
        current_app.logger.error(f"Error updating kitchen order status: {str(e)}")
        return jsonify({'success': False, 'message': 'Failed to update status'})

@kitchen.route('/update_item_status', methods=['POST'])
@login_required
@login_required_with_role(UserRole.KITCHEN)
def update_item_status():
    """Update individual kitchen order item status"""
    try:
        data = request.get_json()
        kitchen_item_id = data.get('kitchen_item_id')
        new_status = data.get('status')
        
        # Get the kitchen for current user
        user_kitchen = Kitchen.query.filter_by(
            kitchen_user_id=current_user.id,
            is_active=True
        ).first()
        
        if not user_kitchen:
            return jsonify({'success': False, 'message': 'No kitchen assigned to your account'})
        
        # Get kitchen order item
        kitchen_item = KitchenOrderItem.query.join(KitchenOrder).filter(
            KitchenOrderItem.id == kitchen_item_id,
            KitchenOrder.kitchen_id == user_kitchen.id
        ).first()
        
        if not kitchen_item:
            return jsonify({'success': False, 'message': 'Kitchen order item not found'})
        
        # Validate status
        try:
            status_enum = KitchenOrderStatus(new_status)
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid status'})
        
        # Update item status
        kitchen_item.update_status(status_enum)
        
        # Check if all items in the kitchen order are ready
        kitchen_order = kitchen_item.kitchen_order
        all_items = kitchen_order.kitchen_items.all()
        
        if all(item.status == KitchenOrderStatus.READY for item in all_items):
            # Update kitchen order status to ready
            kitchen_order.update_status(KitchenOrderStatus.READY)
        
        db.session.commit()
        
        # Emit real-time update
        socketio.emit('kitchen_item_status_update', {
            'order_id': kitchen_order.order_id,
            'kitchen_id': kitchen_order.kitchen_id,
            'kitchen_name': user_kitchen.name,
            'item_id': kitchen_item_id,
            'item_name': kitchen_item.item_name,
            'status': new_status,
            'all_ready': kitchen_order.status == KitchenOrderStatus.READY,
            'updated_at': datetime.utcnow().isoformat()
        }, room=f'branch_{user_kitchen.branch_id}')
        
        return jsonify({
            'success': True,
            'message': f'Item status updated to {status_enum.value}',
            'status': new_status,
            'kitchen_order_status': kitchen_order.status.value
        })
        
    except Exception as e:
        current_app.logger.error(f"Error updating kitchen item status: {str(e)}")
        return jsonify({'success': False, 'message': 'Failed to update item status'})

@kitchen.route('/api/orders')
@login_required
@login_required_with_role(UserRole.KITCHEN)
def api_orders():
    """API endpoint for kitchen orders (for AJAX pagination)"""
    try:
        # Get the kitchen for current user
        user_kitchen = Kitchen.query.filter_by(
            kitchen_user_id=current_user.id,
            is_active=True
        ).first()
        
        if not user_kitchen:
            return jsonify({'success': False, 'message': 'No kitchen assigned to your account'})
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status_filter = request.args.get('status', '')
        
        # Build query
        query = KitchenOrder.query.filter_by(kitchen_id=user_kitchen.id)
        
        if status_filter:
            try:
                status_enum = KitchenOrderStatus(status_filter)
                query = query.filter_by(status=status_enum)
            except ValueError:
                pass
        
        # Get paginated results
        kitchen_orders = query.order_by(KitchenOrder.received_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # Format orders data
        orders_data = []
        for kitchen_order in kitchen_orders.items:
            order_data = {
                'id': kitchen_order.id,
                'order_id': kitchen_order.order_id,
                'order_number': kitchen_order.order.order_number,
                'table_number': kitchen_order.order.table.table_number if kitchen_order.order.table else 'N/A',
                'status': kitchen_order.status.value,
                'received_at': TimezoneManager.format_local_time(kitchen_order.received_at, '%Y-%m-%d %H:%M'),
                'items_count': kitchen_order.get_total_items_count(),
                'items': []
            }
            
            # Add items
            for item in kitchen_order.kitchen_items:
                order_data['items'].append({
                    'id': item.id,
                    'name': item.item_name,
                    'name_ar': item.item_name_ar,
                    'quantity': item.quantity,
                    'special_requests': item.special_requests,
                    'status': item.status.value,
                    'is_new': getattr(item, 'is_new', False),
                    'is_deleted': getattr(item, 'is_deleted', False),
                    'is_edited': getattr(item, 'is_edited', False)
                })
            
            orders_data.append(order_data)
        
        return jsonify({
            'success': True,
            'orders': orders_data,
            'pagination': {
                'page': kitchen_orders.page,
                'pages': kitchen_orders.pages,
                'per_page': kitchen_orders.per_page,
                'total': kitchen_orders.total,
                'has_prev': kitchen_orders.has_prev,
                'has_next': kitchen_orders.has_next
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching kitchen orders: {str(e)}")
        return jsonify({'success': False, 'message': 'Failed to fetch orders'})

@kitchen.route('/api/dashboard')
@login_required
@login_required_with_role(UserRole.KITCHEN)
def api_dashboard():
    """API endpoint for kitchen dashboard data (for AJAX updates)"""
    try:
        # Get the kitchen for current user
        user_kitchen = Kitchen.query.filter_by(
            kitchen_user_id=current_user.id,
            is_active=True
        ).first()
        
        if not user_kitchen:
            return jsonify({'success': False, 'message': 'No kitchen assigned to your account'})
        
        # Get filter parameters
        status_filters = request.args.getlist('status')  # Can be multiple: ['received', 'preparing']
        table_filters = request.args.getlist('table')   # Can be multiple: ['table', 'takeaway']
        
        # Get pending kitchen orders
        pending_kitchen_orders = KitchenOrder.query.filter_by(
            kitchen_id=user_kitchen.id
        ).filter(
            KitchenOrder.status.in_([KitchenOrderStatus.RECEIVED, KitchenOrderStatus.PREPARING])
        ).order_by(KitchenOrder.received_at.asc()).all()
        
        # Get ready orders (last 2 hours)
        two_hours_ago = datetime.utcnow() - timedelta(hours=2)
        ready_kitchen_orders = KitchenOrder.query.filter_by(
            kitchen_id=user_kitchen.id,
            status=KitchenOrderStatus.READY
        ).filter(
            KitchenOrder.ready_at >= two_hours_ago
        ).order_by(KitchenOrder.ready_at.desc()).all()
        
        # Group orders by order_number to consolidate items from same order
        def group_orders_by_number(kitchen_orders):
            grouped_orders = {}
            
            for kitchen_order in kitchen_orders:
                order_number = kitchen_order.order.order_number
                
                if order_number not in grouped_orders:
                    # Create new grouped order entry
                    table_number = kitchen_order.order.table.table_number if kitchen_order.order.table else 'N/A'
                    service_type = kitchen_order.order.service_type.value if kitchen_order.order.service_type else 'on_table'
                    
                    # Get delivery company name if it's a delivery order
                    delivery_company = None
                    if service_type == 'delivery' and kitchen_order.order.delivery_company_id:
                        delivery_company_obj = DeliveryCompany.query.filter_by(
                            id=kitchen_order.order.delivery_company_id,
                            is_active=True
                        ).first()
                        if delivery_company_obj:
                            delivery_company = delivery_company_obj.name
                    
                    # Determine if it's takeaway for backward compatibility
                    is_takeaway = service_type == 'take_away'
                    
                    grouped_orders[order_number] = {
                        'id': kitchen_order.id,  # Use first kitchen_order id for actions
                        'order_id': kitchen_order.order_id,
                        'order_number': order_number,
                        'table_number': table_number,
                        'service_type': service_type,
                        'delivery_company': delivery_company,
                        'is_takeaway': is_takeaway,
                        'status': kitchen_order.status.value,
                        'received_at': TimezoneManager.format_local_time(kitchen_order.received_at, '%Y-%m-%d %H:%M'),
                        'received_at_timestamp': kitchen_order.received_at.timestamp(),
                        'ready_at': TimezoneManager.format_local_time(kitchen_order.ready_at, '%Y-%m-%d %H:%M') if kitchen_order.ready_at else None,
                        'items': [],
                        'kitchen_order_ids': [kitchen_order.id]  # Track all kitchen order IDs
                    }
                else:
                    # Update status to most advanced status and track additional kitchen order IDs
                    grouped_orders[order_number]['kitchen_order_ids'].append(kitchen_order.id)
                    # If any part is ready, mark as ready; if any part is preparing, mark as preparing
                    current_status = grouped_orders[order_number]['status']
                    new_status = kitchen_order.status.value
                    if current_status == 'received' and new_status in ['preparing', 'ready']:
                        grouped_orders[order_number]['status'] = new_status
                    elif current_status == 'preparing' and new_status == 'ready':
                        grouped_orders[order_number]['status'] = new_status
                
                # Add all items from this kitchen order
                for item in kitchen_order.kitchen_items:
                    grouped_orders[order_number]['items'].append({
                        'id': item.id,
                        'name': item.item_name,
                        'name_ar': item.item_name_ar,
                        'quantity': item.quantity,
                        'special_requests': item.special_requests,
                        'status': item.status.value,
                        'is_new': getattr(item, 'is_new', False),
                        'is_deleted': getattr(item, 'is_deleted', False),
                        'is_edited': getattr(item, 'is_edited', False)
                    })
            
            # Convert to list and add items_count
            result = []
            for order_data in grouped_orders.values():
                order_data['items_count'] = len(order_data['items'])
                result.append(order_data)
            
            return result
        
        # Get all orders first
        all_pending = group_orders_by_number(pending_kitchen_orders)
        all_ready = group_orders_by_number(ready_kitchen_orders)
        all_orders = all_pending + all_ready
        
        # Apply filters
        filtered_orders = []
        for order in all_orders:
            # Status filter
            if status_filters and order['status'] not in status_filters:
                continue
            
            # Table/Location filter
            if table_filters and 'all' not in table_filters:
                order_matches_filter = False
                
                if 'table' in table_filters and order['service_type'] == 'on_table':
                    order_matches_filter = True
                elif 'takeaway' in table_filters and order['service_type'] == 'take_away':
                    order_matches_filter = True
                elif 'delivery' in table_filters and order['service_type'] == 'delivery':
                    order_matches_filter = True
                
                if not order_matches_filter:
                    continue  # Skip if doesn't match location filter
            
            filtered_orders.append(order)
        
        # Sort by oldest first (chronological order) - default behavior
        filtered_orders.sort(key=lambda x: x['received_at_timestamp'], reverse=False)
        
        # Separate back into pending and ready for response
        pending_orders_data = [o for o in filtered_orders if o['status'] in ['received', 'preparing']]
        ready_orders_data = [o for o in filtered_orders if o['status'] == 'ready']
        
        # Calculate statistics - only new and ready
        new_count = len([o for o in pending_orders_data if o['status'] == 'received'])
        ready_count = len(ready_orders_data)
        total_count = len(pending_orders_data) + len(ready_orders_data)
        
        return jsonify({
            'success': True,
            'pending_orders': pending_orders_data,
            'ready_orders': ready_orders_data,
            'statistics': {
                'new': new_count,
                'ready': ready_count,
                'total': total_count
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching kitchen dashboard data: {str(e)}")
        return jsonify({'success': False, 'message': 'Failed to fetch dashboard data'})

@kitchen.route('/print_order/<int:kitchen_order_id>')
@login_required
@login_required_with_role(UserRole.KITCHEN)
def print_order_items(kitchen_order_id):
    """Print kitchen order items - includes all items from same order number"""
    try:
        # Get the kitchen for current user
        user_kitchen = Kitchen.query.filter_by(
            kitchen_user_id=current_user.id,
            is_active=True
        ).first()
        
        if not user_kitchen:
            flash('No kitchen assigned to your account.', 'error')
            return redirect(url_for('kitchen.dashboard'))
        
        # Get the primary kitchen order
        primary_kitchen_order = KitchenOrder.query.filter_by(
            id=kitchen_order_id,
            kitchen_id=user_kitchen.id
        ).first_or_404()
        
        # Get all kitchen orders for the same order number in this kitchen
        order_number = primary_kitchen_order.order.order_number
        all_kitchen_orders = KitchenOrder.query.join(Order).filter(
            Order.order_number == order_number,
            KitchenOrder.kitchen_id == user_kitchen.id
        ).all()
        
        # Combine all items from all kitchen orders with same order number
        all_items = []
        for kitchen_order in all_kitchen_orders:
            all_items.extend(kitchen_order.kitchen_items)
        
        # Add combined items to primary order for template
        primary_kitchen_order.combined_items = all_items
        
        return render_template('kitchen/print_order.html',
                             kitchen=user_kitchen,
                             kitchen_order=primary_kitchen_order,
                             print_time=TimezoneManager.get_current_time(),
                             received_at_formatted=TimezoneManager.format_local_time(primary_kitchen_order.received_at, '%Y-%m-%d %H:%M'),
                             ready_at_formatted=TimezoneManager.format_local_time(primary_kitchen_order.ready_at, '%Y-%m-%d %H:%M') if primary_kitchen_order.ready_at else None)
        
    except Exception as e:
        current_app.logger.error(f"Error printing kitchen order: {str(e)}")
        flash('Failed to print order', 'error')
        return redirect(url_for('kitchen.dashboard'))

@kitchen.route('/print_all_pending')
@login_required
@login_required_with_role(UserRole.KITCHEN)
def print_all_pending():
    """Print all pending kitchen orders in bulk - each order on separate page"""
    try:
        # Get the kitchen for current user
        user_kitchen = Kitchen.query.filter_by(
            kitchen_user_id=current_user.id,
            is_active=True
        ).first()
        
        if not user_kitchen:
            flash('No kitchen assigned to your account.', 'error')
            return redirect(url_for('kitchen.dashboard'))
        
        # Get all new kitchen orders (received status only - not preparing or ready)
        pending_kitchen_orders = KitchenOrder.query.filter_by(
            kitchen_id=user_kitchen.id,
            status=KitchenOrderStatus.RECEIVED
        ).order_by(KitchenOrder.received_at.asc()).all()
        
        if not pending_kitchen_orders:
            flash('No new orders to print. Only "New Orders" (received status) can be bulk printed.', 'info')
            return redirect(url_for('kitchen.dashboard'))
        
        # Group orders by order_number to consolidate items from same order
        grouped_orders = {}
        for kitchen_order in pending_kitchen_orders:
            order_number = kitchen_order.order.order_number
            
            if order_number not in grouped_orders:
                # Create new grouped order entry
                grouped_orders[order_number] = {
                    'kitchen_order': kitchen_order,
                    'all_items': list(kitchen_order.kitchen_items),
                    'kitchen_order_ids': [kitchen_order.id]
                }
            else:
                # Add items from this kitchen order to existing group
                grouped_orders[order_number]['all_items'].extend(kitchen_order.kitchen_items)
                grouped_orders[order_number]['kitchen_order_ids'].append(kitchen_order.id)
        
        # Prepare data for template
        orders_to_print = []
        for order_data in grouped_orders.values():
            kitchen_order = order_data['kitchen_order']
            kitchen_order.combined_items = order_data['all_items']
            
            orders_to_print.append({
                'kitchen_order': kitchen_order,
                'received_at_formatted': TimezoneManager.format_local_time(kitchen_order.received_at, '%Y-%m-%d %H:%M'),
                'ready_at_formatted': TimezoneManager.format_local_time(kitchen_order.ready_at, '%Y-%m-%d %H:%M') if kitchen_order.ready_at else None
            })
        
        current_app.logger.info(f"Kitchen {user_kitchen.name} printing {len(orders_to_print)} pending orders in bulk")
        
        return render_template('kitchen/print_all_pending.html',
                             kitchen=user_kitchen,
                             orders_to_print=orders_to_print,
                             print_time=TimezoneManager.get_current_time(),
                             total_orders=len(orders_to_print))
        
    except Exception as e:
        current_app.logger.error(f"Error printing all pending kitchen orders: {str(e)}")
        flash('Failed to print pending orders', 'error')
        return redirect(url_for('kitchen.dashboard'))

@kitchen.route('/clear_ready_orders', methods=['POST'])
@login_required
@login_required_with_role(UserRole.KITCHEN)
def clear_ready_orders():
    """Clear all ready orders from the kitchen dashboard"""
    try:
        # Get the kitchen for current user
        user_kitchen = Kitchen.query.filter_by(
            kitchen_user_id=current_user.id,
            is_active=True
        ).first()
        
        if not user_kitchen:
            return jsonify({'success': False, 'message': 'No kitchen assigned to your account.'})
        
        # Get all ready kitchen orders
        ready_kitchen_orders = KitchenOrder.query.filter_by(
            kitchen_id=user_kitchen.id,
            status=KitchenOrderStatus.READY
        ).all()
        
        if not ready_kitchen_orders:
            return jsonify({'success': False, 'message': 'No ready orders to clear.'})
        
        # Update all ready orders to served status
        cleared_count = 0
        for kitchen_order in ready_kitchen_orders:
            kitchen_order.status = KitchenOrderStatus.SERVED
            kitchen_order.served_at = TimezoneManager.get_current_time()
            cleared_count += 1
        
        # Commit the changes
        db.session.commit()
        
        current_app.logger.info(f"Kitchen {user_kitchen.name} cleared {cleared_count} ready orders")
        
        return jsonify({
            'success': True, 
            'message': f'Successfully cleared {cleared_count} ready orders.',
            'cleared_count': cleared_count
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error clearing ready kitchen orders: {str(e)}")
        return jsonify({'success': False, 'message': 'Failed to clear ready orders'})
