from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app.superuser import superuser
from app.models import User, Branch, UserRole, Order, Category, MenuItem, Table, Customer, DeliveryCompany, OrderItem, AuditLog, CashierSession, OrderStatus, AppSettings, TimezoneManager, OrderCounter, OrderEditHistory, ManualCardPayment
from app import db
from app.auth.decorators import super_admin_required
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_

@superuser.before_request
@super_admin_required
def before_request():
    # Access control is handled by the decorator
    pass

@superuser.route('/dashboard')
def dashboard():
    """Super User dashboard with system overview"""
    # Get system statistics
    total_branches = Branch.query.filter_by(is_active=True).count()
    total_users = User.query.filter_by(is_active=True).count()
    
    # Get today's order statistics - separate paid and unpaid
    today_filter = func.date(Order.created_at) == datetime.utcnow().date()
    
    total_orders_today = Order.query.filter(today_filter).count()
    paid_orders_today = Order.query.filter(
        today_filter,
        Order.status == OrderStatus.PAID
    ).count()
    unpaid_orders_today = Order.query.filter(
        today_filter,
        Order.status == OrderStatus.PENDING
    ).count()
    
    # Get revenue today - only from PAID orders
    today_revenue = db.session.query(func.sum(Order.total_amount)).filter(
        today_filter,
        Order.status == OrderStatus.PAID
    ).scalar() or 0
    
    # Get total statistics across all time
    total_orders_all_time = Order.query.count()
    total_paid_orders = Order.query.filter(Order.status == OrderStatus.PAID).count()
    total_unpaid_orders = Order.query.filter(Order.status == OrderStatus.PENDING).count()
    total_revenue_all_time = db.session.query(func.sum(Order.total_amount)).filter(
        Order.status == OrderStatus.PAID
    ).scalar() or 0
    
    # Include manual card payments in revenue calculations
    today = datetime.utcnow().date()
    manual_card_total_today = db.session.query(func.sum(ManualCardPayment.amount)).filter(
        ManualCardPayment.date == today
    ).scalar() or 0
    manual_card_total_all_time = db.session.query(func.sum(ManualCardPayment.amount)).scalar() or 0
    
    # Update totals to include manual card payments
    today_revenue_with_cards = today_revenue + manual_card_total_today
    total_revenue_all_time_with_cards = total_revenue_all_time + manual_card_total_all_time
    
    # Get branch performance data - fixed query to show real data
    
    # Get today's orders per branch - all orders
    today_orders_subquery = db.session.query(
        Order.branch_id,
        func.count(Order.id).label('total_orders_count')
    ).filter(func.date(Order.created_at) == today)\
     .group_by(Order.branch_id).subquery()
    
    # Get today's paid orders and revenue per branch
    today_paid_orders_subquery = db.session.query(
        Order.branch_id,
        func.count(Order.id).label('paid_orders_count'),
        func.sum(Order.total_amount).label('revenue')
    ).filter(
        func.date(Order.created_at) == today,
        Order.status == OrderStatus.PAID
    ).group_by(Order.branch_id).subquery()
    
    # Get today's unpaid orders per branch
    today_unpaid_orders_subquery = db.session.query(
        Order.branch_id,
        func.count(Order.id).label('unpaid_orders_count')
    ).filter(
        func.date(Order.created_at) == today,
        Order.status == OrderStatus.PENDING
    ).group_by(Order.branch_id).subquery()
    
    # Get active users count per branch
    users_subquery = db.session.query(
        User.branch_id,
        func.count(User.id).label('users_count')
    ).filter(User.is_active == True)\
     .group_by(User.branch_id).subquery()
    
    # Get manual card payments per branch for today
    manual_card_subquery = db.session.query(
        ManualCardPayment.branch_id,
        func.sum(ManualCardPayment.amount).label('manual_card_amount')
    ).filter(ManualCardPayment.date == today)\
     .group_by(ManualCardPayment.branch_id).subquery()
    
    # Combine branch data with statistics
    branch_stats = db.session.query(
        Branch.id,
        Branch.name,
        Branch.code,
        func.coalesce(today_orders_subquery.c.total_orders_count, 0).label('total_orders_count'),
        func.coalesce(today_paid_orders_subquery.c.paid_orders_count, 0).label('paid_orders_count'),
        func.coalesce(today_unpaid_orders_subquery.c.unpaid_orders_count, 0).label('unpaid_orders_count'),
        func.coalesce(today_paid_orders_subquery.c.revenue, 0).label('revenue'),
        func.coalesce(manual_card_subquery.c.manual_card_amount, 0).label('manual_card_amount'),
        func.coalesce(users_subquery.c.users_count, 0).label('users_count')
    ).outerjoin(today_orders_subquery, Branch.id == today_orders_subquery.c.branch_id)\
     .outerjoin(today_paid_orders_subquery, Branch.id == today_paid_orders_subquery.c.branch_id)\
     .outerjoin(today_unpaid_orders_subquery, Branch.id == today_unpaid_orders_subquery.c.branch_id)\
     .outerjoin(manual_card_subquery, Branch.id == manual_card_subquery.c.branch_id)\
     .outerjoin(users_subquery, Branch.id == users_subquery.c.branch_id)\
     .filter(Branch.is_active == True)\
     .all()
    
    # Get edited orders statistics for today (all branches)
    edited_orders_today = Order.query.filter(
        today_filter,
        Order.edit_count > 0
    ).count()
    
    # Get total edited orders (all time, all branches)
    total_edited_orders = Order.query.filter(Order.edit_count > 0).count()
    
    # Get recent activities across all branches
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    
    # Get top cashiers by order edits this week (all branches)
    week_start = datetime.utcnow() - timedelta(days=7)
    
    # Query to get cashiers with their edit counts this week across all branches
    top_editing_cashiers_query = db.session.query(
        User.id,
        User.first_name,
        User.last_name,
        User.role,
        User.branch_id,
        Branch.name.label('branch_name'),
        Branch.code.label('branch_code'),
        func.count(OrderEditHistory.id).label('edit_count')
    ).join(
        OrderEditHistory, User.id == OrderEditHistory.edited_by
    ).join(
        Order, OrderEditHistory.order_id == Order.id
    ).outerjoin(
        Branch, User.branch_id == Branch.id
    ).filter(
        User.role == UserRole.CASHIER,
        OrderEditHistory.edited_at >= week_start
    )
    
    # Group by cashier and order by edit count
    top_editing_cashiers_raw = top_editing_cashiers_query.group_by(
        User.id, User.first_name, User.last_name, User.role, User.branch_id, Branch.name, Branch.code
    ).order_by(
        func.count(OrderEditHistory.id).desc()
    ).limit(6).all()
    
    # Format the data for the chart
    top_editing_cashiers = []
    for cashier in top_editing_cashiers_raw:
        full_name = f"{cashier.first_name} {cashier.last_name}".strip()
        if not full_name:
            full_name = f"Cashier {cashier.id}"
        
        # Format role name
        role_name = cashier.role.name.replace('_', ' ').title() if cashier.role else 'Unknown'
        
        # Format branch info
        branch_info = f"{cashier.branch_name} ({cashier.branch_code})" if cashier.branch_name else 'No Branch'
        
        top_editing_cashiers.append({
            'full_name': full_name,
            'edit_count': cashier.edit_count,
            'role_name': role_name,
            'branch_info': branch_info,
            'branch_name': cashier.branch_name or 'No Branch',
            'branch_code': cashier.branch_code or 'N/A'
        })
    
    # Calculate cash payments (Order Revenue Only - NOT total revenue which includes cards)
    cash_total_today = today_revenue  # This is order revenue only (cash payments)
    cash_total_all_time = total_revenue_all_time  # This is order revenue only (cash payments)
    
    return render_template('superuser/dashboard.html',
                         total_branches=total_branches,
                         total_users=total_users,
                         total_orders_today=total_orders_today,
                         paid_orders_today=paid_orders_today,
                         unpaid_orders_today=unpaid_orders_today,
                         today_revenue=today_revenue_with_cards,
                         total_orders_all_time=total_orders_all_time,
                         total_paid_orders=total_paid_orders,
                         total_unpaid_orders=total_unpaid_orders,
                         total_revenue_all_time=total_revenue_all_time_with_cards,
                         branch_stats=branch_stats,
                         recent_orders=recent_orders,
                         edited_orders_today=edited_orders_today,
                         total_edited_orders=total_edited_orders,
                         top_editing_cashiers=top_editing_cashiers,
                         manual_card_total_today=manual_card_total_today,
                         manual_card_total_all_time=manual_card_total_all_time,
                         cash_total_today=cash_total_today,
                         cash_total_all_time=cash_total_all_time)

@superuser.route('/branches')
def branches():
    """Branch management page"""
    branches = Branch.query.order_by(Branch.created_at.desc()).all()
    return render_template('superuser/branches.html', branches=branches)

@superuser.route('/branches/add', methods=['GET', 'POST'])
def add_branch():
    """Add new branch"""
    if request.method == 'POST':
        try:
            branch = Branch(
                name=request.form.get('name'),
                code=request.form.get('code'),
                address=request.form.get('address'),
                phone=request.form.get('phone'),
                email=request.form.get('email'),
                manager_name=request.form.get('manager_name'),
                timezone=request.form.get('timezone', 'UTC'),
                currency=request.form.get('currency', 'QAR'),
                tax_rate=float(request.form.get('tax_rate', 0)) / 100,
                service_charge=float(request.form.get('service_charge', 0)) / 100
            )
            
            db.session.add(branch)
            db.session.commit()
            
            # Create default categories and menu items for new branch
            create_default_branch_data(branch.id)
            
            flash(f'Branch "{branch.name}" created successfully!', 'success')
            return redirect(url_for('superuser.branches'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating branch: {str(e)}', 'error')
    
    return render_template('superuser/add_branch.html')

@superuser.route('/branches/<int:branch_id>/edit', methods=['GET', 'POST'])
def edit_branch(branch_id):
    """Edit branch details"""
    branch = Branch.query.get_or_404(branch_id)
    
    if request.method == 'POST':
        try:
            branch.name = request.form.get('name')
            branch.code = request.form.get('code')
            branch.address = request.form.get('address')
            branch.phone = request.form.get('phone')
            branch.email = request.form.get('email')
            branch.manager_name = request.form.get('manager_name')
            branch.timezone = request.form.get('timezone', 'UTC')
            branch.currency = request.form.get('currency', 'QAR')
            branch.tax_rate = float(request.form.get('tax_rate', 0)) / 100
            branch.service_charge = float(request.form.get('service_charge', 0)) / 100
            branch.updated_at = datetime.utcnow()
            
            db.session.commit()
            flash(f'Branch "{branch.name}" updated successfully!', 'success')
            return redirect(url_for('superuser.branches'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating branch: {str(e)}', 'error')
    
    return render_template('superuser/edit_branch.html', branch=branch)

@superuser.route('/branches/<int:branch_id>/deactivate', methods=['POST'])
def deactivate_branch(branch_id):
    """Deactivate branch"""
    try:
        branch = Branch.query.get_or_404(branch_id)
        branch.is_active = False
        branch.updated_at = datetime.utcnow()
        
        # Deactivate all users in this branch
        User.query.filter_by(branch_id=branch_id).update({'is_active': False})
        
        db.session.commit()
        
        # Check if this is an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': f'Branch "{branch.name}" deactivated successfully!'
            })
        
        flash(f'Branch "{branch.name}" deactivated successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        
        # Check if this is an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': f'Error deactivating branch: {str(e)}'
            }), 500
        
        flash(f'Error deactivating branch: {str(e)}', 'error')
    
    return redirect(url_for('superuser.branches'))

@superuser.route('/branches/<int:branch_id>/reactivate', methods=['POST'])
def reactivate_branch(branch_id):
    """Reactivate branch and optionally reactivate its users"""
    try:
        branch = Branch.query.get_or_404(branch_id)
        branch.is_active = True
        branch.updated_at = datetime.utcnow()
        
        # Count inactive users in this branch for the success message
        inactive_users_count = User.query.filter_by(branch_id=branch_id, is_active=False).count()
        
        db.session.commit()
        
        # Prepare success message
        message = f'Branch "{branch.name}" reactivated successfully!'
        if inactive_users_count > 0:
            message += f' Note: {inactive_users_count} inactive user(s) in this branch can now be reactivated individually.'
        
        # Check if this is an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': message
            })
        
        flash(message, 'success')
        
    except Exception as e:
        db.session.rollback()
        
        # Check if this is an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': f'Error reactivating branch: {str(e)}'
            }), 500
        
        flash(f'Error reactivating branch: {str(e)}', 'error')
    
    return redirect(url_for('superuser.branches'))

@superuser.route('/api/branches/<int:branch_id>/details')
def get_branch_details(branch_id):
    """Get detailed branch information for modal display"""
    try:
        branch = Branch.query.get_or_404(branch_id)
        
        # Get branch statistics
        total_users = User.query.filter_by(branch_id=branch_id, is_active=True).count()
        total_tables = Table.query.filter_by(branch_id=branch_id, is_active=True).count()
        total_orders = Order.query.filter_by(branch_id=branch_id).count()
        total_categories = Category.query.filter_by(branch_id=branch_id).count()
        total_menu_items = MenuItem.query.filter_by(branch_id=branch_id).count()
        
        # Get today's statistics
        today = datetime.utcnow().date()
        today_orders = Order.query.filter(
            Order.branch_id == branch_id,
            func.date(Order.created_at) == today
        ).count()
        
        today_revenue = db.session.query(func.sum(Order.total_amount)).filter(
            Order.branch_id == branch_id,
            func.date(Order.created_at) == today
        ).scalar() or 0
        
        # Get total revenue
        total_revenue = db.session.query(func.sum(Order.total_amount)).filter(
            Order.branch_id == branch_id
        ).scalar() or 0
        
        # Get recent orders (last 5)
        recent_orders = Order.query.filter_by(branch_id=branch_id)\
                                  .order_by(Order.created_at.desc())\
                                  .limit(5).all()
        
        # Get active users by role
        users_by_role = db.session.query(
            User.role,
            func.count(User.id).label('count')
        ).filter_by(branch_id=branch_id, is_active=True)\
         .group_by(User.role).all()
        
        # Format response data
        branch_data = {
            'id': branch.id,
            'name': branch.name,
            'code': branch.code,
            'address': branch.address,
            'phone': branch.phone,
            'email': branch.email,
            'manager_name': branch.manager_name,
            'timezone': branch.timezone,
            'currency': branch.currency,
            'tax_rate': round(branch.tax_rate * 100, 2) if branch.tax_rate else 0,
            'service_charge': round(branch.service_charge * 100, 2) if branch.service_charge else 0,
            'is_active': branch.is_active,
            'created_at': branch.created_at.strftime('%Y-%m-%d %H:%M') if branch.created_at else None,
            'updated_at': branch.updated_at.strftime('%Y-%m-%d %H:%M') if branch.updated_at else None,
            'statistics': {
                'total_users': total_users,
                'total_tables': total_tables,
                'total_orders': total_orders,
                'total_categories': total_categories,
                'total_menu_items': total_menu_items,
                'today_orders': today_orders,
                'today_revenue': float(today_revenue),
                'total_revenue': float(total_revenue)
            },
            'users_by_role': {role.value: count for role, count in users_by_role},
            'recent_orders': [
                {
                    'id': order.id,
                    'order_number': order.order_number,
                    'total_amount': float(order.total_amount),
                    'created_at': order.created_at.strftime('%Y-%m-%d %H:%M'),
                    'cashier_name': order.cashier.get_full_name() if order.cashier else 'N/A'
                } for order in recent_orders
            ]
        }
        
        return jsonify({'success': True, 'branch': branch_data})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@superuser.route('/users')
def users():
    """View all users from all branches with filtering"""
    # Get filter parameters
    branch_id = request.args.get('branch_id', type=int)
    role = request.args.get('role')
    status = request.args.get('status')
    
    # Build query for all users (no branch filtering for super user)
    query = User.query
    
    # Apply filters
    if branch_id:
        query = query.filter(User.branch_id == branch_id)
    
    if role and role != 'all':
        query = query.filter(User.role == UserRole[role.upper()])
    
    if status and status != 'all':
        if status == 'active':
            query = query.filter(User.is_active == True)
        elif status == 'inactive':
            query = query.filter(User.is_active == False)
    
    users = query.order_by(User.created_at.desc()).all()
    
    # Get filter options
    branches = Branch.query.filter_by(is_active=True).all()
    
    return render_template('admin/users.html',
                         users=users,
                         branches=branches,
                         current_branch=branch_id,
                         current_role=role,
                         current_status=status,
                         can_manage_users=True,
                         can_view_only=False)

@superuser.route('/users/add', methods=['GET', 'POST'])
def add_user():
    """Add new user"""
    if request.method == 'POST':
        # Check if this is an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json'
        
        try:
            # Validate password confirmation
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            
            if password != confirm_password:
                error_msg = 'Passwords do not match!'
                if is_ajax:
                    return jsonify({'success': False, 'message': error_msg}), 400
                flash(error_msg, 'error')
                branches = Branch.query.filter_by(is_active=True).all()
                return render_template('superuser/add_user.html', branches=branches, roles=UserRole)
            
            # Check if username already exists
            existing_user = User.query.filter_by(username=request.form.get('username')).first()
            if existing_user:
                error_msg = 'Username already exists!'
                if is_ajax:
                    return jsonify({'success': False, 'message': error_msg}), 400
                flash(error_msg, 'error')
                branches = Branch.query.filter_by(is_active=True).all()
                return render_template('superuser/add_user.html', branches=branches, roles=UserRole)
            
            # Check if email already exists
            existing_email = User.query.filter_by(email=request.form.get('email')).first()
            if existing_email:
                error_msg = 'Email already exists!'
                if is_ajax:
                    return jsonify({'success': False, 'message': error_msg}), 400
                flash(error_msg, 'error')
                branches = Branch.query.filter_by(is_active=True).all()
                return render_template('superuser/add_user.html', branches=branches, roles=UserRole)
            
            # Create user (removed branch admin restriction - superuser can create multiple admins per branch)
            role_str = request.form.get('role').upper()
            user = User(
                username=request.form.get('username'),
                email=request.form.get('email'),
                first_name=request.form.get('first_name'),
                last_name=request.form.get('last_name'),
                role=UserRole[role_str],
                branch_id=int(request.form.get('branch_id')) if request.form.get('branch_id') else None,
                can_access_multiple_branches=bool(request.form.get('can_access_multiple_branches'))
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            success_msg = f'User "{user.username}" created successfully!'
            if is_ajax:
                return jsonify({'success': True, 'message': success_msg})
            
            flash(success_msg, 'success')
            return redirect(url_for('superuser.users'))
            
        except Exception as e:
            db.session.rollback()
            error_msg = f'Error creating user: {str(e)}'
            if is_ajax:
                return jsonify({'success': False, 'message': error_msg}), 500
            flash(error_msg, 'error')
    
    branches = Branch.query.filter_by(is_active=True).all()
    return render_template('superuser/add_user.html', branches=branches, roles=UserRole)

# Removed check_branch_admin endpoint - multiple admins per branch are now allowed

@superuser.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    """Toggle user active status (deactivate/activate instead of delete)"""
    try:
        user = User.query.get_or_404(user_id)
        
        # Prevent modifying other super users
        if user.role == UserRole.SUPER_USER and user.id != current_user.id:
            return jsonify({'success': False, 'message': 'Cannot modify other super users'}), 403
        
        # Prevent superuser from deactivating themselves
        if user.id == current_user.id and user.role == UserRole.SUPER_USER:
            return jsonify({'success': False, 'message': 'Super users cannot deactivate themselves'}), 403
        
        # Check if trying to activate a user from an inactive branch
        if not user.is_active and user.branch_id:  # User is currently inactive and has a branch
            branch = Branch.query.get(user.branch_id)
            if branch and not branch.is_active:
                return jsonify({
                    'success': False, 
                    'message': f'Cannot activate user from inactive branch "{branch.name}". Please reactivate the branch first.'
                }), 400
        
        # Toggle user active status instead of deleting to preserve data
        user.is_active = not user.is_active
        db.session.commit()
        
        status = 'activated' if user.is_active else 'deactivated'
        return jsonify({'success': True, 'message': f'User {status} successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@superuser.route('/update_user/<int:user_id>', methods=['POST'])
def update_user(user_id):
    """Update a user"""
    try:
        user = User.query.get_or_404(user_id)
        data = request.get_json()
        
        # Allow superuser to edit themselves, but prevent editing other super users
        if user.role == UserRole.SUPER_USER and user.id != current_user.id:
            return jsonify({'success': False, 'message': 'Cannot modify other super users'}), 403
        
        # Superuser can edit all fields including username and names
        
        if 'username' in data:
            # Check if username already exists for another user
            existing_user = User.query.filter(
                User.username == data['username'],
                User.id != user_id
            ).first()
            if existing_user:
                return jsonify({'success': False, 'message': 'Username already exists'}), 400
            user.username = data['username']
        
        if 'first_name' in data:
            user.first_name = data['first_name']
            
        if 'last_name' in data:
            user.last_name = data['last_name']
        
        if 'email' in data:
            # Check if email already exists for another user
            existing_user = User.query.filter(
                User.email == data['email'],
                User.id != user_id
            ).first()
            if existing_user:
                return jsonify({'success': False, 'message': 'Email already exists'}), 400
            user.email = data['email']
        
        if 'role' in data:
            user.role = UserRole[data['role'].upper()]
            
        if 'branch_id' in data:
            user.branch_id = data['branch_id']
            
        if 'is_active' in data:
            # Check if trying to activate a user from an inactive branch
            if data['is_active'] and not user.is_active and user.branch_id:  # Trying to activate an inactive user with a branch
                branch = Branch.query.get(user.branch_id)
                if branch and not branch.is_active:
                    return jsonify({
                        'success': False, 
                        'message': f'Cannot activate user from inactive branch "{branch.name}". Please reactivate the branch first.'
                    }), 400
            
            user.is_active = data['is_active']
        
        # Update password if provided
        if data.get('password'):
            user.set_password(data['password'])
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'User updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

def create_default_branch_data(branch_id):
    """Create default categories, menu items, and tables for new branch"""
    try:
        # Create default categories
        categories_data = [
            {'name': 'Quick', 'order_index': 0},
            {'name': 'Homos', 'order_index': 1},
            {'name': 'Foul', 'order_index': 2},
            {'name': 'FATA', 'order_index': 3},
            {'name': 'MIX', 'order_index': 4},
            {'name': 'Falafel', 'order_index': 5},
            {'name': 'Bakery', 'order_index': 6},
            {'name': 'طلبات خاصة', 'order_index': 7}
        ]
        
        for cat_data in categories_data:
            category = Category(
                name=cat_data['name'],
                order_index=cat_data['order_index'],
                branch_id=branch_id
            )
            db.session.add(category)
        
        # Create default tables
        for i in range(1, 11):  # Create 10 tables
            table = Table(
                table_number=f"T{i:02d}",
                capacity=4,
                branch_id=branch_id
            )
            db.session.add(table)
        
        # Create default customer
        customer = Customer(
            name="Walk-in Customer",
            phone="000-000-0000",
            branch_id=branch_id
        )
        db.session.add(customer)
        
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating default branch data: {str(e)}")
        raise e

@superuser.route('/orders')
def orders():
    """View orders from all branches"""
    # Get filter parameters
    branch_id = request.args.get('branch_id', type=int)
    service_type = request.args.get('service_type')
    payment_status = request.args.get('payment_status')  # New filter for payment status
    cashier_id = request.args.get('cashier_id', type=int)
    table_id = request.args.get('table_id', type=int)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    # Build query for all orders (no branch filtering for super user)
    query = Order.query
    
    # Apply filters
    if branch_id:
        query = query.filter(Order.branch_id == branch_id)
    
    if cashier_id:
        query = query.filter(Order.cashier_id == cashier_id)
        
    if table_id:
        query = query.filter(Order.table_id == table_id)
    
    # Apply payment status filter
    if payment_status and payment_status != 'all':
        if payment_status == 'paid':
            query = query.filter(Order.status == OrderStatus.PAID)
        elif payment_status == 'unpaid':
            query = query.filter(Order.status == OrderStatus.PENDING)
    
    if service_type and service_type != 'all':
        from app.models import ServiceType
        if service_type == 'delivery':
            query = query.filter(Order.service_type == ServiceType.DELIVERY)
        elif service_type == 'on_table':
            query = query.filter(Order.service_type == ServiceType.ON_TABLE)
        elif service_type == 'take_away':
            query = query.filter(Order.service_type == ServiceType.TAKE_AWAY)
        elif service_type == 'card':
            query = query.filter(Order.service_type == ServiceType.CARD)
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Order.created_at >= date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(Order.created_at < date_to_obj)
        except ValueError:
            pass
    
    # Get orders with pagination
    page = request.args.get('page', 1, type=int)
    orders = query.order_by(Order.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    
    # Get filter options - system-wide for superuser
    branches = Branch.query.filter_by(is_active=True).all()
    cashiers = User.query.filter(User.role == UserRole.CASHIER).filter_by(is_active=True).all()
    tables = Table.query.filter_by(is_active=True).all()
    
    # Create filters object for template
    filters = {
        'branch_id': branch_id,
        'service_type': service_type,
        'payment_status': payment_status,
        'cashier_id': cashier_id,
        'table_id': table_id,
        'date_from': date_from,
        'date_to': date_to
    }
    
    # Check if this is an AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Return JSON response for AJAX
        orders_data = []
        for order in orders.items:
            # Count regular items (excluding special items)
            regular_items_count = sum(1 for item in order.order_items if 'طلبات خاصة' not in item.menu_item.name)
            
            # Get delivery company info
            delivery_company_info = None
            if order.delivery_company_id and hasattr(order, 'delivery_company_info'):
                delivery_company_info = {
                    'name': order.delivery_company_info.name,
                    'value': order.delivery_company_info.value,
                    'icon': order.delivery_company_info.icon
                }
            
            order_data = {
                'id': order.id,
                'order_number': order.order_number,
                'order_counter': order.order_counter if order.order_counter else None,
                'table_number': order.table.table_number if order.table else 'N/A',
                'cashier_name': order.cashier.username if order.cashier else 'N/A',
                'total_amount': float(order.total_amount),
                'total_amount_with_modifiers': float(order.total_amount),
                'created_at': order.created_at.strftime('%Y-%m-%d %H:%M'),
                'service_type': order.service_type.value if order.service_type else 'on_table',
                'delivery_company': delivery_company_info,
                'regular_items_count': regular_items_count,
                'status': order.status.value if order.status else 'pending',
                'items_count': regular_items_count,
                # Add edit information to match static HTML
                'edit_count': order.edit_count if order.edit_count else 0,
                'last_edited_at': order.last_edited_at.strftime('%Y-%m-%d %H:%M') if order.last_edited_at else None,
                # Add cashier object structure for compatibility
                'cashier': {
                    'username': order.cashier.username if order.cashier else None,
                    'role': {
                        'value': order.cashier.role.value if order.cashier and order.cashier.role else None
                    }
                } if order.cashier else None,
                # Add branch information for super users
                'branch': {
                    'name': order.branch.name if order.branch else None
                } if order.branch else None,
                # Legacy fields for compatibility
                'cashier_username': order.cashier.username if order.cashier else 'N/A',
                'branch_name': order.branch.name if order.branch else 'N/A',
                'cashier_role': order.cashier.role.value if order.cashier else 'N/A'
            }
            orders_data.append(order_data)
        
        return jsonify({
            'success': True,
            'orders': orders_data,
            'pagination': {
                'page': orders.page,
                'pages': orders.pages,
                'per_page': orders.per_page,
                'total': orders.total,
                'has_next': orders.has_next,
                'has_prev': orders.has_prev,
                'next_num': orders.next_num,
                'prev_num': orders.prev_num
            }
        })
    
    return render_template('admin/orders.html',
                         orders=orders,
                         branches=branches,
                         cashiers=cashiers,
                         tables=tables,
                         filters=filters,
                         current_branch=branch_id,
                         current_service_type=service_type,
                         current_payment_status=payment_status,
                         date_from=date_from,
                         date_to=date_to)

@superuser.route('/audit_logs')
def audit_logs():
    """View audit logs from all branches"""
    # Get filter parameters
    branch_id = request.args.get('branch_id', type=int)
    user_id = request.args.get('user_id', type=int)
    action = request.args.get('action')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    # Build query for all audit logs (no branch filtering for super user)
    from app.models import AuditLog
    query = AuditLog.query
    
    # Apply filters
    if branch_id:
        # Filter by users from specific branch
        branch_user_ids = [u.id for u in User.query.filter_by(branch_id=branch_id).all()]
        query = query.filter(AuditLog.user_id.in_(branch_user_ids))
    
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    
    if action and action != 'all':
        query = query.filter(AuditLog.action == action)
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(AuditLog.created_at >= date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(AuditLog.created_at < date_to_obj)
        except ValueError:
            pass
    
    # Get logs with pagination
    page = request.args.get('page', 1, type=int)
    logs = query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=100, error_out=False
    )
    
    # Get filter options - system-wide for superuser
    branches = Branch.query.filter_by(is_active=True).all()
    users = User.query.filter_by(is_active=True).all()
    
    # Get distinct actions from audit logs for filter dropdown
    distinct_actions = db.session.query(AuditLog.action).distinct().all()
    actions = [action[0] for action in distinct_actions if action[0]]
    
    # Create filters object for template
    filters = {
        'branch_id': branch_id,
        'user_id': user_id,
        'action': action,
        'date_from': date_from,
        'date_to': date_to
    }
    
    # Check if this is an AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Get timezone from settings (default to Qatar)
        import pytz
        app_timezone = AppSettings.get_value('app_timezone', 'Asia/Qatar')
        try:
            tz = pytz.timezone(app_timezone)
        except pytz.UnknownTimeZoneError:
            tz = pytz.timezone('Asia/Qatar')  # Fallback to Qatar
        
        # Return JSON response for AJAX
        logs_data = []
        for log in logs.items:
            # Convert UTC to user's timezone
            utc_time = pytz.utc.localize(log.created_at) if log.created_at.tzinfo is None else log.created_at
            local_time = utc_time.astimezone(tz)
            
            log_data = {
                'id': log.id,
                'user': {
                    'username': log.user.username if log.user else 'System',
                    'full_name': log.user.get_full_name() if log.user else '',
                    'branch_name': log.user.branch.name if log.user and log.user.branch else 'N/A',
                    'role': log.user.role.value if log.user else 'N/A'
                },
                'action': log.action,
                'description': log.description or '',
                'ip_address': log.ip_address or 'N/A',
                'created_at': {
                    'date': local_time.strftime('%m/%d/%Y'),
                    'time': local_time.strftime('%I:%M:%S %p')
                }
            }
            logs_data.append(log_data)
        
        return jsonify({
            'success': True,
            'logs': logs_data,
            'pagination': {
                'page': logs.page,
                'pages': logs.pages,
                'per_page': logs.per_page,
                'total': logs.total,
                'has_next': logs.has_next,
                'has_prev': logs.has_prev,
                'next_num': logs.next_num,
                'prev_num': logs.prev_num
            }
        })
    
    return render_template('admin/audit_logs.html',
                         logs=logs,
                         branches=branches,
                         users=users,
                         actions=actions,
                         filters=filters,
                         current_branch=branch_id,
                         current_user_id=user_id,
                         current_action=action,
                         date_from=date_from,
                         date_to=date_to)

@superuser.route('/cashier_performance')
def cashier_performance():
    """View cashier performance across all branches"""
    # Get filter parameters
    branch_id = request.args.get('branch_id', type=int)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    # Build query for all cashiers (no branch filtering for super user)
    cashiers_query = User.query.filter_by(role=UserRole.CASHIER, is_active=True)
    
    if branch_id:
        cashiers_query = cashiers_query.filter(User.branch_id == branch_id)
    
    cashiers = cashiers_query.all()
    
    # Calculate performance metrics for each cashier
    performance_data = []
    for cashier in cashiers:
        # Count orders specific to this cashier only
        # This includes:
        # 1. Orders created directly by this cashier (both PAID and PENDING)
        # 2. Waiter orders that this cashier marked as PAID (processed by this cashier)
        
        # Get orders created by this cashier
        cashier_orders_query = Order.query.filter_by(cashier_id=cashier.id)
        
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                cashier_orders_query = cashier_orders_query.filter(Order.created_at >= date_from_obj)
            except ValueError:
                pass
        
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
                cashier_orders_query = cashier_orders_query.filter(Order.created_at < date_to_obj)
            except ValueError:
                pass
        
        cashier_orders = cashier_orders_query.all()
        
        # Get waiter orders assigned to this cashier
        assigned_waiter_orders_query = Order.query.filter_by(assigned_cashier_id=cashier.id)
        
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                assigned_waiter_orders_query = assigned_waiter_orders_query.filter(Order.created_at >= date_from_obj)
            except ValueError:
                pass
        
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
                assigned_waiter_orders_query = assigned_waiter_orders_query.filter(Order.created_at < date_to_obj)
            except ValueError:
                pass
        
        assigned_waiter_orders = assigned_waiter_orders_query.all()
        
        # Combine cashier's own orders with waiter orders assigned to them
        all_orders = cashier_orders + assigned_waiter_orders
        
        # Count ALL orders (cashier's own + waiter orders they processed)
        total_orders = len(all_orders)
        
        # Count only revenue from PAID orders
        paid_orders = [order for order in all_orders if hasattr(order, 'status') and order.status == OrderStatus.PAID]
        order_revenue = sum(order.total_amount for order in paid_orders)
        
        # Add manual card payments for this cashier in the date range
        manual_card_query = ManualCardPayment.query.filter_by(cashier_id=cashier.id)
        
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
                manual_card_query = manual_card_query.filter(ManualCardPayment.date >= date_from_obj)
            except ValueError:
                pass
        
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
                manual_card_query = manual_card_query.filter(ManualCardPayment.date <= date_to_obj)
            except ValueError:
                pass
        
        manual_card_revenue = sum(payment.amount for payment in manual_card_query.all())
        total_revenue = order_revenue + manual_card_revenue
        
        # Calculate average based on PAID orders only (manual card payments are separate)
        avg_order_value = order_revenue / len(paid_orders) if len(paid_orders) > 0 else 0
        
        # Calculate login count based on date range
        login_query = CashierSession.query.filter_by(cashier_id=cashier.id)
        
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
                login_query = login_query.filter(CashierSession.login_date >= date_from_obj)
            except ValueError:
                pass
        
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
                login_query = login_query.filter(CashierSession.login_date <= date_to_obj)
            except ValueError:
                pass
        
        login_count = login_query.count()
        
        # Count paid and unpaid orders separately
        unpaid_orders = [order for order in all_orders if hasattr(order, 'status') and order.status == OrderStatus.PENDING]
        
        performance_data.append({
            'cashier': cashier,
            'orders_count': total_orders,  # ALL orders (including waiter PENDING orders)
            'paid_orders_count': len(paid_orders),  # Only PAID orders
            'unpaid_orders_count': len(unpaid_orders),  # Only PENDING orders
            'total_sales': total_revenue,  # Orders + Manual Card Payments
            'order_revenue': order_revenue,  # Only from PAID orders
            'manual_card_revenue': manual_card_revenue,  # Manual card payments
            'avg_order_value': avg_order_value,  # Based on PAID orders only
            'login_count': login_count,  # Real login count from CashierSession
            'efficiency_score': min(100, (total_orders * 10) if total_orders > 0 else 0),  # Based on ALL orders
            'branch': cashier.branch
        })
    
    # Sort by total sales descending
    performance_data.sort(key=lambda x: x['total_sales'], reverse=True)
    
    # Get filter options
    branches = Branch.query.filter_by(is_active=True).all()
    
    # Set default dates if not provided
    if not date_from:
        start_date = datetime.now() - timedelta(days=7)
    else:
        try:
            start_date = datetime.strptime(date_from, '%Y-%m-%d')
        except ValueError:
            start_date = datetime.now() - timedelta(days=7)
    
    if not date_to:
        end_date = datetime.now()
    else:
        try:
            end_date = datetime.strptime(date_to, '%Y-%m-%d')
        except ValueError:
            end_date = datetime.now()
    
    return render_template('admin/cashier_performance.html',
                         performance_data=performance_data,
                         branches=branches,
                         current_branch=branch_id,
                         start_date=start_date,
                         end_date=end_date,
                         date_from=date_from,
                         date_to=date_to)

@superuser.route('/reports')
def reports():
    """System-wide reports and analytics"""
    # Get filter parameters
    branch_id = request.args.get('branch_id', type=int)
    
    # Build base query with optional branch filtering
    base_query = Order.query
    if branch_id:
        base_query = base_query.filter(Order.branch_id == branch_id)
    
    # Get statistics (system-wide or branch-specific) - separate paid and unpaid
    total_orders = base_query.count()  # ALL orders (including PENDING)
    total_paid_orders = base_query.filter(Order.status == OrderStatus.PAID).count()
    total_unpaid_orders = base_query.filter(Order.status == OrderStatus.PENDING).count()
    
    # Revenue only from PAID orders
    paid_orders_query = base_query.filter(Order.status == OrderStatus.PAID)
    order_revenue_query = db.session.query(func.sum(Order.total_amount)).filter(Order.status == OrderStatus.PAID)
    if branch_id:
        order_revenue_query = order_revenue_query.filter(Order.branch_id == branch_id)
    order_revenue = order_revenue_query.scalar() or 0
    
    # Add manual card payments
    manual_card_query = db.session.query(func.sum(ManualCardPayment.amount))
    if branch_id:
        manual_card_query = manual_card_query.filter(ManualCardPayment.branch_id == branch_id)
    manual_card_revenue = manual_card_query.scalar() or 0
    
    total_revenue = order_revenue + manual_card_revenue
    
    # Average order value - calculated from PAID orders only (excluding manual card payments)
    avg_order_value = (order_revenue / total_paid_orders) if total_paid_orders > 0 else 0
    
    # Today's statistics - separate paid and unpaid
    today = datetime.utcnow().date()
    today_query = base_query.filter(func.date(Order.created_at) == today)
    today_orders = today_query.count()
    today_paid_orders = today_query.filter(Order.status == OrderStatus.PAID).count()
    today_unpaid_orders = today_query.filter(Order.status == OrderStatus.PENDING).count()
    
    # Today's revenue only from PAID orders
    today_order_revenue_query = db.session.query(func.sum(Order.total_amount)).filter(
        func.date(Order.created_at) == today,
        Order.status == OrderStatus.PAID
    )
    if branch_id:
        today_order_revenue_query = today_order_revenue_query.filter(Order.branch_id == branch_id)
    today_order_revenue = today_order_revenue_query.scalar() or 0
    
    # Add today's manual card payments
    today_manual_card_query = db.session.query(func.sum(ManualCardPayment.amount)).filter(
        ManualCardPayment.date == today
    )
    if branch_id:
        today_manual_card_query = today_manual_card_query.filter(ManualCardPayment.branch_id == branch_id)
    today_manual_card_revenue = today_manual_card_query.scalar() or 0
    
    today_revenue = today_order_revenue + today_manual_card_revenue
    
    # Branch performance comparison - separate total orders and paid revenue
    from sqlalchemy import case
    branch_performance = db.session.query(
        Branch.name,
        func.count(Order.id).label('total_orders'),
        func.sum(case((Order.status == OrderStatus.PAID, 1), else_=0)).label('paid_orders'),
        func.sum(case((Order.status == OrderStatus.PENDING, 1), else_=0)).label('unpaid_orders'),
        func.sum(case((Order.status == OrderStatus.PAID, Order.total_amount), else_=0)).label('revenue')
    ).outerjoin(Order, Order.branch_id == Branch.id)\
     .filter(Branch.is_active == True)\
     .group_by(Branch.id, Branch.name)\
     .all()
    
    # Sales trend for last 30 days
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)
    
    daily_sales_query = db.session.query(
        func.date(Order.created_at).label('date'),
        func.sum(case((Order.status == OrderStatus.PAID, Order.total_amount), else_=0)).label('total'),
        func.count(Order.id).label('total_orders'),
        func.sum(case((Order.status == OrderStatus.PAID, 1), else_=0)).label('paid_orders'),
        func.sum(case((Order.status == OrderStatus.PENDING, 1), else_=0)).label('unpaid_orders')
    ).filter(Order.created_at >= start_date)
    
    if branch_id:
        daily_sales_query = daily_sales_query.filter(Order.branch_id == branch_id)
    
    daily_sales = daily_sales_query.group_by(
        func.date(Order.created_at)
    ).order_by(
        func.date(Order.created_at)
    ).all()
    
    # Top performing items (all branches or specific branch) - only from PAID orders
    top_items_query = db.session.query(
        MenuItem.name,
        Branch.name.label('branch_name'),
        func.sum(OrderItem.quantity).label('total_quantity'),
        func.sum(OrderItem.total_price).label('total_revenue')
    ).join(OrderItem, MenuItem.id == OrderItem.menu_item_id)\
     .join(Order, OrderItem.order_id == Order.id)\
     .join(Branch, MenuItem.branch_id == Branch.id)\
     .filter(
         Order.created_at >= start_date,
         Order.status == OrderStatus.PAID
     )
    
    if branch_id:
        top_items_query = top_items_query.filter(Order.branch_id == branch_id)
    
    top_items = top_items_query.group_by(MenuItem.id, MenuItem.name, Branch.name)\
     .order_by(func.sum(OrderItem.quantity).desc())\
     .limit(20).all()
    
    # Get service type distribution for pie chart - only from PAID orders
    from app.models import ServiceType
    service_type_stats = db.session.query(
        Order.service_type,
        func.count(Order.id).label('count'),
        func.sum(Order.total_amount).label('revenue')
    ).filter(
        Order.created_at >= start_date,
        Order.status == OrderStatus.PAID
    )
    
    if branch_id:
        service_type_stats = service_type_stats.filter(Order.branch_id == branch_id)
    
    service_type_stats = service_type_stats.group_by(Order.service_type).all()
    
    # Format service type data for the template
    service_type_data = {
        'on_table': {'count': 0, 'revenue': 0},
        'take_away': {'count': 0, 'revenue': 0},
        'delivery': {'count': 0, 'revenue': 0},
        'card': {'count': 0, 'revenue': 0}
    }
    
    for stat in service_type_stats:
        if stat.service_type == ServiceType.ON_TABLE:
            service_type_data['on_table'] = {'count': stat.count, 'revenue': float(stat.revenue or 0)}
        elif stat.service_type == ServiceType.TAKE_AWAY:
            service_type_data['take_away'] = {'count': stat.count, 'revenue': float(stat.revenue or 0)}
        elif stat.service_type == ServiceType.DELIVERY:
            service_type_data['delivery'] = {'count': stat.count, 'revenue': float(stat.revenue or 0)}
        elif stat.service_type == ServiceType.CARD:
            service_type_data['card'] = {'count': stat.count, 'revenue': float(stat.revenue or 0)}
    
    # Get branches for filter dropdown
    branches = Branch.query.filter_by(is_active=True).all()
    
    return render_template('admin/reports.html',
                         total_orders=total_orders,
                         total_paid_orders=total_paid_orders,
                         total_unpaid_orders=total_unpaid_orders,
                         total_revenue=total_revenue,
                         order_revenue=order_revenue,
                         manual_card_revenue=manual_card_revenue,
                         avg_order_value=avg_order_value,
                         today_orders=today_orders,
                         today_paid_orders=today_paid_orders,
                         today_unpaid_orders=today_unpaid_orders,
                         today_revenue=today_revenue,
                         today_order_revenue=today_order_revenue,
                         today_manual_card_revenue=today_manual_card_revenue,
                         branch_performance=branch_performance,
                        daily_sales=daily_sales,
                        top_items=top_items,
                        branches=branches,
                        current_branch=branch_id,
                        service_type_data=service_type_data)


@superuser.route('/settings')
def settings():
    """Super User settings page for app-wide configurations"""
    # Get current settings
    current_timezone = AppSettings.get_value('app_timezone', 'Asia/Qatar')
    current_date_format = AppSettings.get_value('date_format', '%Y-%m-%d %H:%M:%S')
    current_currency = AppSettings.get_value('default_currency', 'QAR')
    
    # Get counter reset settings
    counter_reset_enabled = AppSettings.get_value('counter_reset_enabled', 'false').lower() == 'true'
    counter_reset_time = AppSettings.get_value('counter_reset_time', '00:00')
    
    # Get available timezones
    available_timezones = TimezoneManager.get_available_timezones()
    
    # Get current time in configured timezone
    current_time_local = TimezoneManager.get_current_time()
    current_time_utc = datetime.utcnow()
    
    # Get counter statistics
    counter_stats = []
    branches = Branch.query.filter_by(is_active=True).all()
    for branch in branches:
        counter_record = OrderCounter.query.filter_by(branch_id=branch.id).first()
        counter_stats.append({
            'branch_id': branch.id,
            'branch_name': branch.name,
            'branch_code': branch.code,
            'current_counter': counter_record.current_counter if counter_record else 0,
            'last_reset_date': counter_record.last_reset_date if counter_record else None
        })
    
    return render_template('superuser/settings.html',
                         current_timezone=current_timezone,
                         current_date_format=current_date_format,
                         current_currency=current_currency,
                         counter_reset_enabled=counter_reset_enabled,
                         counter_reset_time=counter_reset_time,
                         counter_stats=counter_stats,
                         available_timezones=available_timezones,
                         current_time_local=current_time_local,
                         current_time_utc=current_time_utc)


@superuser.route('/settings/save', methods=['POST'])
def save_settings():
    """Save app-wide settings"""
    try:
        # Get form data
        timezone = request.form.get('timezone')
        date_format = request.form.get('date_format')
        currency = request.form.get('currency')
        counter_reset_enabled = request.form.get('counter_reset_enabled') == 'on'
        counter_reset_time = request.form.get('counter_reset_time', '00:00')
        
        current_app.logger.info(f'Saving settings: timezone={timezone}, date_format={date_format}, currency={currency}, counter_reset_enabled={counter_reset_enabled}, counter_reset_time={counter_reset_time}')
        
        # Validate timezone
        if timezone:
            try:
                import pytz
                pytz.timezone(timezone)  # This will raise exception if invalid
                AppSettings.set_value('app_timezone', timezone, 'Application timezone setting')
                current_app.logger.info(f'Timezone setting saved: {timezone}')
            except pytz.UnknownTimeZoneError as tz_error:
                current_app.logger.error(f'Invalid timezone: {timezone}, error: {tz_error}')
                flash('Invalid timezone selected', 'error')
                return redirect(url_for('superuser.settings'))
        
        # Save date format
        if date_format:
            AppSettings.set_value('date_format', date_format, 'Default date format for displaying timestamps')
            current_app.logger.info(f'Date format setting saved: {date_format}')
        
        # Save currency
        if currency:
            AppSettings.set_value('default_currency', currency, 'Default currency symbol for the application')
            current_app.logger.info(f'Currency setting saved: {currency}')
        
        # Save counter reset settings
        AppSettings.set_value('counter_reset_enabled', str(counter_reset_enabled).lower(), 'Enable/disable daily counter reset')
        current_app.logger.info(f'Counter reset enabled setting saved: {counter_reset_enabled}')
        
        # Validate and save counter reset time
        try:
            # Validate time format
            datetime.strptime(counter_reset_time, '%H:%M')
            AppSettings.set_value('counter_reset_time', counter_reset_time, 'Daily reset time for order counters (HH:MM format)')
            current_app.logger.info(f'Counter reset time setting saved: {counter_reset_time}')
        except ValueError:
            current_app.logger.error(f'Invalid time format: {counter_reset_time}')
            flash('Invalid time format for counter reset time. Please use HH:MM format.', 'error')
            return redirect(url_for('superuser.settings'))
        
        # Commit settings changes first
        db.session.commit()
        current_app.logger.info('Settings committed to database')
        
        # Log the change in audit log
        try:
            audit_log = AuditLog(
                user_id=current_user.id,
                action='UPDATE_APP_SETTINGS',
                description=f'Updated timezone to {timezone}, date format to {date_format}, currency to {currency}'
            )
            db.session.add(audit_log)
            db.session.commit()
            current_app.logger.info('Audit log created successfully')
        except Exception as audit_error:
            current_app.logger.error(f'Failed to create audit log: {audit_error}')
            # Don't fail the whole operation if audit log fails
        
        flash('Settings saved successfully! The new timezone will be used for all new orders and datetime displays.', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error saving settings: {str(e)}', exc_info=True)
        flash(f'Error saving settings: {str(e)}', 'error')
    
    return redirect(url_for('superuser.settings'))


@superuser.route('/settings/test_timezone')
def test_timezone():
    """Test endpoint to show current timezone information"""
    try:
        current_tz = TimezoneManager.get_app_timezone()
        current_time = TimezoneManager.get_current_time()
        utc_time = datetime.utcnow()
        
        # Test conversion
        test_utc = datetime.utcnow()
        test_local = TimezoneManager.convert_utc_to_local(test_utc)
        
        return jsonify({
            'success': True,
            'timezone_name': str(current_tz),
            'current_local_time': current_time.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'current_utc_time': utc_time.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'test_conversion': {
                'utc': test_utc.strftime('%Y-%m-%d %H:%M:%S UTC'),
                'local': test_local.strftime('%Y-%m-%d %H:%M:%S %Z')
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@superuser.route('/settings/reset_counters', methods=['POST'])
def reset_counters():
    """Manually reset all order counters"""
    try:
        # Reset all counters
        OrderCounter.reset_all_counters()
        db.session.commit()
        
        # Log the action
        audit_log = AuditLog(
            user_id=current_user.id,
            action='RESET_ORDER_COUNTERS',
            description='Manually reset all order counters'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        flash('All order counters have been reset successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error resetting counters: {str(e)}')
        flash(f'Error resetting counters: {str(e)}', 'error')
    
    return redirect(url_for('superuser.settings'))


@superuser.route('/settings/reset_counter/<int:branch_id>', methods=['POST'])
def reset_branch_counter(branch_id):
    """Reset counter for a specific branch"""
    try:
        branch = Branch.query.get_or_404(branch_id)
        
        # Reset counter for this branch
        OrderCounter.reset_counter(branch_id)
        db.session.commit()
        
        # Log the action
        audit_log = AuditLog(
            user_id=current_user.id,
            action='RESET_BRANCH_COUNTER',
            description=f'Manually reset order counter for branch: {branch.name}'
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Counter for branch "{branch.name}" has been reset successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error resetting branch counter: {str(e)}')
        return jsonify({
            'success': False,
            'message': f'Error resetting counter: {str(e)}'
        }), 500

@superuser.route('/api/reports/cash-per-date')
@login_required
def api_cash_per_date():
    """API endpoint for cash per date data - all branches or branch-specific"""
    if current_user.role != UserRole.SUPER_USER:
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        # Get parameters
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        branch_id = request.args.get('branch_id', type=int)
        time_period = request.args.get('time_period')
        service_type = request.args.get('service_type')
        delivery_company_id = request.args.get('delivery_company_id')
        
        # Handle time period filtering
        if time_period and time_period != 'custom':
            days = int(time_period)
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
        elif date_from and date_to:
            start_date = datetime.strptime(date_from, '%Y-%m-%d')
            end_date = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
        else:
            # Default to last 7 days
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=7)
        
        # Build query for cash (order payments only) per date
        from sqlalchemy import case
        cash_per_date_query = db.session.query(
            func.date(Order.created_at).label('date'),
            func.sum(case((Order.status == OrderStatus.PAID, Order.total_amount), else_=0)).label('cash_amount')
        ).filter(
            Order.created_at >= start_date,
            Order.created_at < end_date
        )
        
        # Apply branch filtering if specified
        if branch_id:
            cash_per_date_query = cash_per_date_query.filter(Order.branch_id == branch_id)
        
        # Add service type filtering
        if service_type and service_type != 'all':
            from app.models import ServiceType
            if service_type == 'on_table':
                cash_per_date_query = cash_per_date_query.filter(Order.service_type == ServiceType.ON_TABLE)
            elif service_type == 'take_away':
                cash_per_date_query = cash_per_date_query.filter(Order.service_type == ServiceType.TAKE_AWAY)
            elif service_type == 'delivery':
                cash_per_date_query = cash_per_date_query.filter(Order.service_type == ServiceType.DELIVERY)
        
        # Add delivery company filtering
        if delivery_company_id and delivery_company_id != 'all':
            cash_per_date_query = cash_per_date_query.filter(Order.delivery_company_id == delivery_company_id)
        
        cash_per_date_query = cash_per_date_query.group_by(
            func.date(Order.created_at)
        ).order_by(
            func.date(Order.created_at)
        )
        
        cash_data = cash_per_date_query.all()
        
        # Format data for chart
        result = {
            'dates': [str(item.date) for item in cash_data],
            'cash_amounts': [float(item.cash_amount or 0) for item in cash_data]
        }
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@superuser.route('/api/reports/peak-hours')
@login_required
def api_peak_hours():
    """API endpoint for peak selling hours data - all branches or branch-specific"""
    if current_user.role != UserRole.SUPER_USER:
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        # Get parameters
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        branch_id = request.args.get('branch_id', type=int)
        time_period = request.args.get('time_period')
        service_type = request.args.get('service_type')
        delivery_company_id = request.args.get('delivery_company_id')
        
        # Handle time period filtering
        if time_period and time_period != 'custom':
            days = int(time_period)
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
        elif date_from and date_to:
            start_date = datetime.strptime(date_from, '%Y-%m-%d')
            end_date = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
        else:
            # Default to last 7 days
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=7)
        
        # Build query for hourly sales data
        from sqlalchemy import case, extract
        hourly_sales_query = db.session.query(
            extract('hour', Order.created_at).label('hour'),
            func.count(Order.id).label('order_count'),
            func.sum(case((Order.status == OrderStatus.PAID, Order.total_amount), else_=0)).label('revenue')
        ).filter(
            Order.created_at >= start_date,
            Order.created_at < end_date
        )
        
        # Apply branch filtering if specified
        if branch_id:
            hourly_sales_query = hourly_sales_query.filter(Order.branch_id == branch_id)
        
        # Add service type filtering
        if service_type and service_type != 'all':
            from app.models import ServiceType
            if service_type == 'on_table':
                hourly_sales_query = hourly_sales_query.filter(Order.service_type == ServiceType.ON_TABLE)
            elif service_type == 'take_away':
                hourly_sales_query = hourly_sales_query.filter(Order.service_type == ServiceType.TAKE_AWAY)
            elif service_type == 'delivery':
                hourly_sales_query = hourly_sales_query.filter(Order.service_type == ServiceType.DELIVERY)
        
        # Add delivery company filtering
        if delivery_company_id and delivery_company_id != 'all':
            hourly_sales_query = hourly_sales_query.filter(Order.delivery_company_id == delivery_company_id)
        
        hourly_sales_query = hourly_sales_query.group_by(
            extract('hour', Order.created_at)
        ).order_by(
            extract('hour', Order.created_at)
        )
        
        hourly_data = hourly_sales_query.all()
        
        # Create 24-hour format with all hours (0-23)
        hours = list(range(24))
        order_counts = [0] * 24
        revenues = [0] * 24
        
        # Fill in actual data
        for item in hourly_data:
            hour_index = int(item.hour)
            if 0 <= hour_index <= 23:
                order_counts[hour_index] = item.order_count
                revenues[hour_index] = float(item.revenue or 0)
        
        # Format data for chart
        result = {
            'hours': [f"{hour:02d}:00" for hour in hours],
            'order_counts': order_counts,
            'revenues': revenues
        }
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@superuser.route('/items_insights')
def items_insights():
    """Items selling insights - comprehensive analysis of item sales across all branches"""
    from datetime import timedelta
    
    # Get filter parameters
    branch_id = request.args.get('branch_id', type=int)
    days = request.args.get('days', default='30')  # Keep as string to handle 'all' value
    
    # Calculate date range
    if days == 'all':
        start_date = None
    else:
        try:
            days_int = int(days)
            start_date = datetime.utcnow() - timedelta(days=days_int)
        except ValueError:
            # If days can't be converted to int, default to 30 days
            days = 30
            start_date = datetime.utcnow() - timedelta(days=30)
    
    # Build base query for items analysis - only from PAID orders
    items_query = db.session.query(
        MenuItem.id,
        MenuItem.name,
        MenuItem.name_ar,
        Branch.name.label('branch_name'),
        func.sum(OrderItem.quantity).label('total_quantity'),
        func.sum(OrderItem.total_price).label('total_revenue'),
        func.avg(OrderItem.unit_price).label('avg_price')
    ).join(OrderItem, MenuItem.id == OrderItem.menu_item_id)\
     .join(Order, OrderItem.order_id == Order.id)\
     .join(Branch, MenuItem.branch_id == Branch.id)\
     .filter(
         Order.status == OrderStatus.PAID,
         OrderItem.is_deleted == False
     )
    
    # Apply date filter if specified
    if start_date:
        items_query = items_query.filter(Order.created_at >= start_date)
    
    # Apply branch filter if specified
    if branch_id:
        items_query = items_query.filter(Order.branch_id == branch_id)
    
    # Group by item and branch, order by total quantity sold (descending)
    items_data = items_query.group_by(
        MenuItem.id, MenuItem.name, MenuItem.name_ar, Branch.name
    ).order_by(
        func.sum(OrderItem.quantity).desc()
    ).all()
    
    # Calculate summary statistics
    total_items_sold = sum(item.total_quantity for item in items_data)
    total_items_revenue = sum(float(item.total_revenue) for item in items_data)
    unique_items_count = len(items_data)
    avg_item_price = (total_items_revenue / total_items_sold) if total_items_sold > 0 else 0
    
    # Find max quantity for progress bar calculation
    max_quantity = max([item.total_quantity for item in items_data]) if items_data else 1
    
    # Convert items_data to a format with float values for template compatibility
    items_data_formatted = []
    for item in items_data:
        items_data_formatted.append({
            'id': item.id,
            'name': item.name,
            'name_ar': item.name_ar,
            'branch_name': item.branch_name,
            'total_quantity': item.total_quantity,
            'total_revenue': float(item.total_revenue),
            'avg_price': float(item.avg_price)
        })
    
    # Branch performance statistics (if multiple branches)
    branch_stats = []
    if not branch_id:  # Only show branch comparison if not filtering by specific branch
        branch_stats_query = db.session.query(
            Branch.name.label('branch_name'),
            func.sum(OrderItem.quantity).label('total_items'),
            func.sum(OrderItem.total_price).label('total_revenue')
        ).join(MenuItem, Branch.id == MenuItem.branch_id)\
         .join(OrderItem, MenuItem.id == OrderItem.menu_item_id)\
         .join(Order, OrderItem.order_id == Order.id)\
         .filter(
             Order.status == OrderStatus.PAID,
             OrderItem.is_deleted == False,
             Branch.is_active == True
         )
        
        if start_date:
            branch_stats_query = branch_stats_query.filter(Order.created_at >= start_date)
        
        branch_stats_raw = branch_stats_query.group_by(Branch.id, Branch.name).all()
        
        # Convert branch_stats to format with float values for template compatibility
        branch_stats = []
        for stat in branch_stats_raw:
            branch_stats.append({
                'branch_name': stat.branch_name,
                'total_items': stat.total_items,
                'total_revenue': float(stat.total_revenue)
            })
    
    # Find max branch revenue for progress bar calculation
    max_branch_revenue = max([stat['total_revenue'] for stat in branch_stats]) if branch_stats else 1.0
    
    # Get branches for filter dropdown
    branches = Branch.query.filter_by(is_active=True).all()
    
    return render_template('superuser/items_insights.html',
                         items_data=items_data_formatted,
                         total_items_sold=total_items_sold,
                         total_items_revenue=total_items_revenue,
                         unique_items_count=unique_items_count,
                         avg_item_price=avg_item_price,
                         max_quantity=max_quantity,
                         branch_stats=branch_stats,
                         max_branch_revenue=max_branch_revenue,
                         branches=branches,
                         current_branch=branch_id,
                         current_days=days)


@superuser.route('/active_users')
def active_users():
    """Get real-time active users with geolocation data"""
    try:
        from datetime import timedelta
        from app.models import AuditLog
        import pytz
        
        print("Starting active_users route...")
        
        # Get filter parameters
        status_filter = request.args.get('status', 'all')  # all, online, offline
        branch_filter = request.args.get('branch_id', type=int)
        role_filter = request.args.get('role')
        
        # Get timezone from settings (default to Qatar)
        app_timezone = AppSettings.get_value('app_timezone', 'Asia/Qatar')
        try:
            tz = pytz.timezone(app_timezone)
        except pytz.UnknownTimeZoneError:
            tz = pytz.timezone('Asia/Qatar')  # Fallback to Qatar
        
        # Consider users active if they had activity in the last 15 minutes
        active_threshold = datetime.utcnow() - timedelta(minutes=15)
        print(f"Active threshold: {active_threshold}")
        
        # Build query for users with filters
        users_query = User.query.filter_by(is_active=True)
        
        # Apply branch filter
        if branch_filter:
            users_query = users_query.filter(User.branch_id == branch_filter)
        
        # Apply role filter
        if role_filter and role_filter != 'all':
            try:
                role_enum = UserRole[role_filter.upper()]
                users_query = users_query.filter(User.role == role_enum)
            except KeyError:
                pass  # Invalid role, ignore filter
        
        users = users_query.all()
        print(f"Found {len(users)} active users")
        
        active_users_data = []
        for user in users:
            try:
                print(f"Processing user: {user.username}")
                
                # Check if user has recent activity (last_login or recent audit log)
                is_online = False
                
                # Check last_login field
                if user.last_login and user.last_login >= active_threshold:
                    is_online = True
                    print(f"User {user.username} is online via last_login: {user.last_login}")
                
                # Also check recent audit logs as backup
                if not is_online:
                    try:
                        recent_log = AuditLog.query.filter_by(user_id=user.id)\
                                                  .filter(AuditLog.created_at >= active_threshold)\
                                                  .first()
                        if recent_log:
                            is_online = True
                            print(f"User {user.username} is online via recent audit log: {recent_log.created_at}")
                    except Exception as audit_error:
                        print(f"Error checking audit logs for user {user.username}: {audit_error}")
                
                if not is_online:
                    print(f"User {user.username} is offline - last_login: {user.last_login}, threshold: {active_threshold}")
                
                # Get the latest IP address from audit logs
                ip_address = '127.0.0.1'  # Default
                try:
                    latest_log = AuditLog.query.filter_by(user_id=user.id)\
                                              .filter(AuditLog.ip_address.isnot(None))\
                                              .order_by(AuditLog.created_at.desc())\
                                              .first()
                    if latest_log and latest_log.ip_address:
                        ip_address = latest_log.ip_address
                except Exception as ip_error:
                    print(f"Error getting IP for user {user.username}: {ip_error}")
                
                # Safely get user details
                try:
                    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username
                    role = user.role.value if user.role else 'N/A'
                    branch_name = user.branch.name if user.branch else 'No Branch'
                    
                    # Convert last activity to user's timezone
                    last_activity = None
                    if user.last_login:
                        # Convert UTC to user's timezone
                        utc_time = pytz.utc.localize(user.last_login) if user.last_login.tzinfo is None else user.last_login
                        local_time = utc_time.astimezone(tz)
                        last_activity = local_time.strftime('%m/%d/%Y, %I:%M:%S %p')
                        
                except Exception as detail_error:
                    print(f"Error getting details for user {user.username}: {detail_error}")
                    full_name = user.username
                    role = 'N/A'
                    branch_name = 'No Branch'
                    last_activity = None
                
                active_users_data.append({
                    'id': user.id,
                    'username': user.username,
                    'full_name': full_name,
                    'role': role,
                    'branch_name': branch_name,
                    'is_online': is_online,
                    'last_activity': last_activity,
                    'ip_address': ip_address,
                    'location_data': None
                })
                
            except Exception as user_error:
                print(f"Error processing user {user.username}: {user_error}")
                # Add basic user data even if there's an error
                active_users_data.append({
                    'id': user.id,
                    'username': user.username,
                    'full_name': user.username,
                    'role': 'N/A',
                    'branch_name': 'No Branch',
                    'is_online': False,
                    'last_activity': None,
                    'ip_address': '127.0.0.1',
                    'location_data': None
                })
        
        # Apply status filter after processing all users
        if status_filter == 'online':
            active_users_data = [u for u in active_users_data if u['is_online']]
        elif status_filter == 'offline':
            active_users_data = [u for u in active_users_data if not u['is_online']]
        
        # Count online/offline users from original data (before status filter)
        all_users_data = active_users_data if status_filter == 'all' else []
        if status_filter != 'all':
            # Recalculate for all users to show correct stats
            all_users_query = User.query.filter_by(is_active=True)
            if branch_filter:
                all_users_query = all_users_query.filter(User.branch_id == branch_filter)
            if role_filter and role_filter != 'all':
                try:
                    role_enum = UserRole[role_filter.upper()]
                    all_users_query = all_users_query.filter(User.role == role_enum)
                except KeyError:
                    pass
            
            all_users = all_users_query.all()
            online_count = 0
            offline_count = 0
            
            for user in all_users:
                is_online = False
                if user.last_login and user.last_login >= active_threshold:
                    is_online = True
                if not is_online:
                    try:
                        recent_log = AuditLog.query.filter_by(user_id=user.id)\
                                                  .filter(AuditLog.created_at >= active_threshold)\
                                                  .first()
                        if recent_log:
                            is_online = True
                    except:
                        pass
                
                if is_online:
                    online_count += 1
                else:
                    offline_count += 1
        else:
            online_count = len([u for u in active_users_data if u['is_online']])
            offline_count = len([u for u in active_users_data if not u['is_online']])
        
        total_users = online_count + offline_count
        
        print(f"Returning {len(active_users_data)} users (filtered): {online_count} online, {offline_count} offline total")
        
        # Convert last_updated to user's timezone
        utc_now = datetime.utcnow()
        utc_time = pytz.utc.localize(utc_now)
        local_time = utc_time.astimezone(tz)
        
        return jsonify({
            'success': True,
            'users': active_users_data,
            'total_users': total_users,
            'online_users': online_count,
            'offline_users': offline_count,
            'filtered_count': len(active_users_data),
            'last_updated': local_time.strftime('%m/%d/%Y, %I:%M:%S %p'),
            'timezone': app_timezone
        })
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error in active_users route: {str(e)}")
        print(f"Full traceback: {error_details}")
        
        return jsonify({
            'success': False,
            'error': str(e),
            'error_details': error_details,
            'users': [],
            'total_users': 0,
            'online_users': 0,
            'offline_users': 0,
            'last_updated': datetime.utcnow().isoformat()
        }), 500


@superuser.route('/test_route')
def test_route():
    """Simple test route to verify routing works"""
    return jsonify({
        'success': True,
        'message': 'Test route is working!',
        'timestamp': datetime.utcnow().isoformat()
    })
