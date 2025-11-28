"""
Email notification system for admin alerts on cashier logout
"""
import os
import io
import socket
import time
from datetime import datetime, timedelta
from flask import current_app, render_template_string
from flask_mail import Mail, Message
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table as ReportTable, TableStyle
from reportlab.lib.units import inch
from sqlalchemy import func
from app import db, socketio, mail
from app.models import User, UserRole, Order, OrderStatus, ManualCardPayment, AdminNotification

def generate_cashier_logout_pdf(cashier, logout_time, daily_stats):
    """Generate PDF report for cashier logout"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        alignment=1,  # Center alignment
        textColor=HexColor('#2c3e50')
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        spaceAfter=12,
        textColor=HexColor('#34495e')
    )
    
    # Header
    elements.append(Paragraph("🍽️ Restaurant POS", title_style))
    elements.append(Paragraph("Cashier Logout Report", title_style))
    elements.append(Spacer(1, 20))
    
    # Cashier info
    cashier_info = f"""
    <b>Cashier:</b> {cashier.get_full_name()}<br/>
    <b>Branch:</b> {cashier.branch.name if cashier.branch else 'N/A'}<br/>
    <b>Logout Date:</b> {logout_time.strftime('%A, %B %d, %Y')}<br/>
    <b>Logout Time:</b> {logout_time.strftime('%I:%M %p')}<br/>
    <b>Report Generated:</b> {datetime.now().strftime('%I:%M %p')}
    """
    elements.append(Paragraph(cashier_info, styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # Daily Performance
    elements.append(Paragraph("📊 Daily Performance Summary", heading_style))
    performance_data = [
        ['Metric', 'Value'],
        ['Total Orders Processed', str(daily_stats['total_orders'])],
        ['Total Revenue Generated', f"{daily_stats['total_sales']:.2f} QAR"],
        ['Cash Sales', f"{daily_stats['cash_sales']:.2f} QAR"],
        ['Card Payments', f"{daily_stats['card_payments']:.2f} QAR"],
        ['Waiter Orders Processed', str(daily_stats['waiter_orders'])],
        ['Waiter Orders Revenue', f"{daily_stats['waiter_sales']:.2f} QAR"]
    ]
    
    performance_table = ReportTable(performance_data, colWidths=[3*inch, 2*inch])
    performance_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#3498db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), HexColor('#ecf0f1')),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(performance_table)
    elements.append(Spacer(1, 20))
    
    # Order Status Breakdown
    if daily_stats['order_breakdown']:
        elements.append(Paragraph("📋 Order Status Breakdown", heading_style))
        breakdown_data = [['Status', 'Count', 'Revenue']]
        for status, data in daily_stats['order_breakdown'].items():
            breakdown_data.append([
                status.replace('_', ' ').title(),
                str(data['count']),
                f"{data['revenue']:.2f} QAR"
            ])
        
        breakdown_table = ReportTable(breakdown_data, colWidths=[2*inch, 1.5*inch, 1.5*inch])
        breakdown_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#27ae60')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), HexColor('#d5f4e6')),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(breakdown_table)
        elements.append(Spacer(1, 20))
    
    # Footer
    footer_text = f"""
    <br/><br/>
    <i>This report was automatically generated upon cashier logout.<br/>
    System: Restaurant POS v2.0<br/>
    Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>
    """
    elements.append(Paragraph(footer_text, styles['Normal']))
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer

def get_cashier_daily_stats(cashier, date):
    """Get comprehensive daily statistics for a cashier"""
    # Base query for cashier's orders (both created and assigned)
    base_query = Order.query.filter(
        db.or_(
            Order.cashier_id == cashier.id,
            Order.assigned_cashier_id == cashier.id
        ),
        func.date(Order.created_at) == date
    )
    
    # Total orders
    total_orders = base_query.count()
    
    # Total sales (only paid orders)
    total_sales = db.session.query(func.sum(Order.total_amount)).filter(
        db.or_(
            Order.cashier_id == cashier.id,
            Order.assigned_cashier_id == cashier.id
        ),
        Order.status == OrderStatus.PAID,
        func.date(Order.created_at) == date
    ).scalar() or 0
    
    # Waiter orders statistics
    waiter_orders = Order.query.filter(
        Order.assigned_cashier_id == cashier.id,
        Order.notes.like('%[WAITER ORDER]%'),
        func.date(Order.created_at) == date
    ).count()
    
    waiter_sales = db.session.query(func.sum(Order.total_amount)).filter(
        Order.assigned_cashier_id == cashier.id,
        Order.notes.like('%[WAITER ORDER]%'),
        Order.status == OrderStatus.PAID,
        func.date(Order.created_at) == date
    ).scalar() or 0
    
    # Card payments for the branch
    card_payments = ManualCardPayment.query.filter_by(
        branch_id=cashier.branch_id,
        date=date
    ).first()
    card_payment_amount = card_payments.amount if card_payments else 0
    
    # Cash sales (total sales minus card payments)
    cash_sales = total_sales - card_payment_amount
    
    # Order status breakdown
    order_breakdown = {}
    for status in OrderStatus:
        count = base_query.filter(Order.status == status).count()
        revenue = db.session.query(func.sum(Order.total_amount)).filter(
            db.or_(
                Order.cashier_id == cashier.id,
                Order.assigned_cashier_id == cashier.id
            ),
            Order.status == status,
            func.date(Order.created_at) == date
        ).scalar() or 0
        
        if count > 0:
            order_breakdown[status.value] = {
                'count': count,
                'revenue': revenue
            }
    
    return {
        'total_orders': total_orders,
        'total_sales': float(total_sales),
        'cash_sales': float(cash_sales),
        'card_payments': float(card_payment_amount),
        'waiter_orders': waiter_orders,
        'waiter_sales': float(waiter_sales),
        'order_breakdown': order_breakdown
    }

def send_cashier_logout_notification(cashier_id):
    """Send email notification to branch admins when cashier logs out"""
    max_retries = 3
    retry_delay = 2  # Start with 2 seconds
    
    for attempt in range(max_retries):
        try:
            current_app.logger.info(f"Starting cashier logout notification for ID: {cashier_id} (Attempt {attempt + 1}/{max_retries})")
            
            # Set socket timeout to prevent indefinite hangs
            default_timeout = socket.getdefaulttimeout()
            timeout_value = current_app.config.get('MAIL_TIMEOUT', 30)
            socket.setdefaulttimeout(timeout_value)
            current_app.logger.info(f"Socket timeout set to {timeout_value} seconds")
            
            try:
                # Check email configuration first
                is_configured, missing_configs = check_email_configuration()
                if not is_configured:
                    current_app.logger.error(f"Email not configured for logout notification. Missing: {', '.join(missing_configs)}")
                    return False
                
                # Get cashier information
                cashier = User.query.get(cashier_id)
                if not cashier or cashier.role != UserRole.CASHIER:
                    current_app.logger.error(f"Invalid cashier ID for logout notification: {cashier_id}")
                    return False
                
                current_app.logger.info(f"Processing logout notification for cashier: {cashier.get_full_name()}")
                
                logout_time = datetime.utcnow()
                today = logout_time.date()
                
                # Get daily statistics
                daily_stats = get_cashier_daily_stats(cashier, today)
                
                # Generate PDF report
                pdf_buffer = generate_cashier_logout_pdf(cashier, logout_time, daily_stats)
                
                # Get branch admins to notify
                branch_admins = User.query.filter(
                    User.branch_id == cashier.branch_id,
                    User.role.in_([UserRole.BRANCH_ADMIN, UserRole.SUPER_USER]),
                    User.is_active == True,
                    User.email.isnot(None)
                ).all()
                
                current_app.logger.info(f"Found {len(branch_admins)} admins to notify for branch {cashier.branch_id}")
                for admin in branch_admins:
                    current_app.logger.info(f"Admin: {admin.get_full_name()} ({admin.email}) - Role: {admin.role.value}")
                
                if not branch_admins:
                    current_app.logger.warning(f"No branch admins found to notify for cashier logout: {cashier.get_full_name()}")
                    return False
                
                # Email template
                email_subject = f"🔔 Cashier Logout Alert - {cashier.get_full_name()}"
                
                email_body = f"""
                <html>
                <head>
                    <style>
                        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                        .header {{ background-color: #3498db; color: white; padding: 20px; text-align: center; }}
                        .content {{ padding: 20px; }}
                        .stats-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                        .stats-table th, .stats-table td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                        .stats-table th {{ background-color: #f2f2f2; font-weight: bold; }}
                        .highlight {{ background-color: #e8f4fd; padding: 15px; border-left: 4px solid #3498db; margin: 20px 0; }}
                        .footer {{ background-color: #f8f9fa; padding: 15px; text-align: center; font-size: 12px; color: #666; }}
                    </style>
                </head>
                <body>
                    <div class="header">
                        <h1>🍽️ Restaurant POS - Cashier Logout Alert</h1>
                    </div>
                    
                    <div class="content">
                        <div class="highlight">
                            <h2>📋 Logout Summary</h2>
                            <p><strong>Cashier:</strong> {cashier.get_full_name()}</p>
                            <p><strong>Branch:</strong> {cashier.branch.name if cashier.branch else 'N/A'}</p>
                            <p><strong>Logout Time:</strong> {logout_time.strftime('%A, %B %d, %Y at %I:%M %p')}</p>
                        </div>
                        
                        <h3>📊 Daily Performance Summary</h3>
                        <table class="stats-table">
                            <tr><th>Metric</th><th>Value</th></tr>
                            <tr><td>Total Orders Processed</td><td>{daily_stats['total_orders']}</td></tr>
                            <tr><td>Total Revenue Generated</td><td>{daily_stats['total_sales']:.2f} QAR</td></tr>
                            <tr><td>Cash Sales</td><td>{daily_stats['cash_sales']:.2f} QAR</td></tr>
                            <tr><td>Card Payments</td><td>{daily_stats['card_payments']:.2f} QAR</td></tr>
                            <tr><td>Waiter Orders Processed</td><td>{daily_stats['waiter_orders']}</td></tr>
                            <tr><td>Waiter Orders Revenue</td><td>{daily_stats['waiter_sales']:.2f} QAR</td></tr>
                        </table>
                        
                        <p><strong>📎 Detailed PDF Report:</strong> Please find the complete daily report attached to this email.</p>
                        
                        <div class="highlight">
                            <p><strong>🔔 Real-time Notification:</strong> This alert was sent automatically when the cashier completed their logout process.</p>
                        </div>
                    </div>
                    
                    <div class="footer">
                        <p>Restaurant POS System - Automated Notification<br>
                        Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    </div>
                </body>
                </html>
                """
                
                # Send notification data (convert Decimals to floats for JSON serialization)
                def convert_decimals(obj):
                    """Recursively convert Decimal objects to float for JSON serialization"""
                    from decimal import Decimal
                    if isinstance(obj, Decimal):
                        return float(obj)
                    elif isinstance(obj, dict):
                        return {key: convert_decimals(value) for key, value in obj.items()}
                    elif isinstance(obj, list):
                        return [convert_decimals(item) for item in obj]
                    else:
                        return obj
                
                notification_data = {
                    'cashier_name': cashier.get_full_name(),
                    'branch_name': cashier.branch.name if cashier.branch else 'N/A',
                    'logout_time': logout_time.strftime('%I:%M %p'),
                    'logout_date': logout_time.strftime('%B %d, %Y'),
                    'daily_stats': convert_decimals(daily_stats),
                    'timestamp': logout_time.isoformat()
                }
                
                emails_sent = 0
                
                # Use mail connection context for reliable sending
                current_app.logger.info(f"Attempting to connect to SMTP server: {current_app.config.get('MAIL_SERVER')}:{current_app.config.get('MAIL_PORT')}")
                with mail.connect() as conn:
                    current_app.logger.info("✅ Successfully connected to SMTP server")
                    for admin in branch_admins:
                        try:
                            msg = Message(
                                subject=email_subject,
                                sender=current_app.config['MAIL_DEFAULT_SENDER'],
                                recipients=[admin.email],
                                html=email_body
                            )
                            
                            # Attach PDF report
                            pdf_buffer.seek(0)
                            msg.attach(
                                filename=f"cashier_report_{cashier.get_full_name().replace(' ', '_')}_{today.strftime('%Y%m%d')}.pdf",
                                content_type="application/pdf",
                                data=pdf_buffer.read()
                            )
                            
                            conn.send(msg)
                            emails_sent += 1
                            current_app.logger.info(f"✅ Logout notification sent to admin: {admin.email}")
                            
                            # Save notification to database for persistence
                            try:
                                import json
                                db_notification = AdminNotification(
                                    type='cashier_logout',
                                    title=f'Cashier Logout: {cashier.get_full_name()}',
                                    message=f'Cashier {cashier.get_full_name()} logged out at {logout_time.strftime("%I:%M %p")} with {daily_stats["total_orders"]} orders processed.',
                                    cashier_id=cashier.id,
                                    cashier_name=cashier.get_full_name(),
                                    branch_name=cashier.branch.name if cashier.branch else 'N/A',
                                    logout_time=logout_time,
                                    daily_stats=json.dumps(convert_decimals(daily_stats)),
                                    recipient_id=admin.id
                                )
                                db.session.add(db_notification)
                                db.session.commit()
                                current_app.logger.info(f"💾 Database notification saved for admin: {admin.email}")
                            except Exception as db_e:
                                current_app.logger.error(f"❌ Failed to save notification to database for {admin.email}: {str(db_e)}")
                                db.session.rollback()
                            
                            # Send real-time WebSocket notification to admin (separate try-catch)
                            try:
                                current_app.logger.info(f"🔌 Attempting WebSocket emission to room: admin_{admin.id}")
                                current_app.logger.info(f"🔌 Notification data keys: {list(notification_data.keys())}")
                                socketio.emit('cashier_logout_notification', notification_data, 
                                            room=f'admin_{admin.id}')
                                current_app.logger.info(f"✅ WebSocket notification sent to admin: {admin.email}")
                            except Exception as ws_e:
                                current_app.logger.error(f"❌ Failed to send WebSocket notification to {admin.email}: {str(ws_e)}")
                                current_app.logger.error(f"❌ WebSocket error type: {type(ws_e).__name__}")
                                import traceback
                                current_app.logger.error(f"❌ WebSocket traceback: {traceback.format_exc()}")
                            
                        except Exception as e:
                            current_app.logger.error(f"Failed to send logout notification to {admin.email}: {str(e)}")
                
                # Send branch-wide notification (separate try-catch)
                if cashier.branch_id:
                    try:
                        socketio.emit('cashier_logout_notification', notification_data, 
                                    room=f'branch_{cashier.branch_id}')
                        current_app.logger.info(f"Branch-wide WebSocket notification sent for branch: {cashier.branch_id}")
                    except Exception as ws_e:
                        current_app.logger.error(f"Failed to send branch-wide WebSocket notification: {str(ws_e)}")
                
                current_app.logger.info(f"✅ Cashier logout notifications sent successfully: {emails_sent} emails")
                return emails_sent > 0
                
            finally:
                # Restore original socket timeout
                socket.setdefaulttimeout(default_timeout)
                
        except socket.timeout as e:
            current_app.logger.error(f"❌ Socket timeout on attempt {attempt + 1}/{max_retries}: {str(e)}")
            if attempt < max_retries - 1:
                current_app.logger.info(f"⏳ Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                current_app.logger.error(f"❌ All {max_retries} attempts failed due to timeout. SMTP server may be unreachable.")
                return False
                
        except OSError as e:
            # Catch [Errno 110] ETIMEDOUT and similar errors
            if e.errno == 110 or 'ETIMEDOUT' in str(e) or 'timed out' in str(e).lower():
                current_app.logger.error(f"❌ Connection timeout on attempt {attempt + 1}/{max_retries}: {str(e)}")
                if attempt < max_retries - 1:
                    current_app.logger.info(f"⏳ Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    current_app.logger.error(f"❌ All {max_retries} attempts failed. Check SMTP server connectivity and firewall rules.")
                    return False
            else:
                current_app.logger.error(f"❌ OSError sending cashier logout notification: {str(e)}")
                return False
                
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            current_app.logger.error(f"❌ Error ({error_type}) sending cashier logout notification: {error_msg}")
            
            # Provide specific guidance based on error type
            if 'authentication' in error_msg.lower() or 'auth' in error_msg.lower():
                current_app.logger.error("⚠️ Authentication failed. For Gmail, ensure you're using an App Password, not your regular password.")
            elif 'connection refused' in error_msg.lower():
                current_app.logger.error("⚠️ Connection refused. SMTP server may be down or firewall is blocking the connection.")
            elif 'tls' in error_msg.lower() or 'ssl' in error_msg.lower():
                current_app.logger.error("⚠️ TLS/SSL error. Check MAIL_USE_TLS setting matches the SMTP port.")
            
            return False
    
    return False

def check_email_configuration():
    """Check if email is properly configured"""
    required_configs = ['MAIL_SERVER', 'MAIL_USERNAME', 'MAIL_PASSWORD', 'MAIL_DEFAULT_SENDER']
    missing_configs = []
    
    for config in required_configs:
        if not current_app.config.get(config):
            missing_configs.append(config)
    
    return len(missing_configs) == 0, missing_configs

def send_test_notification(admin_email):
    """Send test notification to verify email system"""
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            # Check email configuration first
            is_configured, missing_configs = check_email_configuration()
            if not is_configured:
                current_app.logger.error(f"Email not configured. Missing: {', '.join(missing_configs)}")
                return False, f"Email not configured. Missing: {', '.join(missing_configs)}"
            
            # Set socket timeout to prevent indefinite hangs
            default_timeout = socket.getdefaulttimeout()
            timeout_value = current_app.config.get('MAIL_TIMEOUT', 30)
            socket.setdefaulttimeout(timeout_value)
            current_app.logger.info(f"Test email attempt {attempt + 1}/{max_retries} - Socket timeout set to {timeout_value} seconds")
            
            try:
                # Create a fresh mail connection with current config
                current_app.logger.info(f"Attempting to connect to SMTP server: {current_app.config.get('MAIL_SERVER')}:{current_app.config.get('MAIL_PORT')}")
                with mail.connect() as conn:
                    current_app.logger.info("✅ Successfully connected to SMTP server")
                    msg = Message(
                        subject="🧪 Test Notification - Restaurant POS",
                        sender=current_app.config['MAIL_DEFAULT_SENDER'],
                        recipients=[admin_email],
                        html="""
                        <html>
                        <body style="font-family: Arial, sans-serif;">
                            <div style="background-color: #28a745; color: white; padding: 20px; text-align: center;">
                                <h1>✅ Email System Test</h1>
                            </div>
                            <div style="padding: 20px;">
                                <p>This is a test email to verify that the Restaurant POS notification system is working correctly.</p>
                                <p><strong>Test sent at:</strong> {}</p>
                                <p><strong>Configuration Status:</strong></p>
                                <ul>
                                    <li>Mail Server: {}</li>
                                    <li>Mail Port: {}</li>
                                    <li>TLS Enabled: {}</li>
                                    <li>Sender: {}</li>
                                </ul>
                                <p>If you receive this email, the notification system is configured properly!</p>
                            </div>
                        </body>
                        </html>
                        """.format(
                            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            current_app.config.get('MAIL_SERVER', 'Not configured'),
                            current_app.config.get('MAIL_PORT', 'Not configured'),
                            current_app.config.get('MAIL_USE_TLS', 'Not configured'),
                            current_app.config.get('MAIL_DEFAULT_SENDER', 'Not configured')
                        )
                    )
                    
                    conn.send(msg)
                    current_app.logger.info(f"✅ Test email sent successfully to {admin_email}")
                    return True, "Test email sent successfully! Check your inbox."
                    
            finally:
                # Restore original socket timeout
                socket.setdefaulttimeout(default_timeout)
        
        except socket.timeout as e:
            current_app.logger.error(f"❌ Socket timeout on attempt {attempt + 1}/{max_retries}: {str(e)}")
            if attempt < max_retries - 1:
                current_app.logger.info(f"⏳ Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                error_msg = f"Connection timeout after {max_retries} attempts. Your SMTP server (port {current_app.config.get('MAIL_PORT')}) may be unreachable. If using Render, try using an email API service like SendGrid instead of SMTP."
                current_app.logger.error(f"❌ {error_msg}")
                return False, error_msg
                
        except OSError as e:
            # Catch [Errno 110] ETIMEDOUT and similar errors
            if e.errno == 110 or 'ETIMEDOUT' in str(e) or 'timed out' in str(e).lower():
                current_app.logger.error(f"❌ Connection timeout on attempt {attempt + 1}/{max_retries}: {str(e)}")
                if attempt < max_retries - 1:
                    current_app.logger.info(f"⏳ Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    error_msg = f"Connection timeout (ETIMEDOUT) after {max_retries} attempts. Render platform may be blocking SMTP port {current_app.config.get('MAIL_PORT')}. Consider using SendGrid, Mailgun, or another email API service instead."
                    current_app.logger.error(f"❌ {error_msg}")
                    return False, error_msg
            else:
                error_msg = f"Network error: {str(e)}"
                current_app.logger.error(f"❌ {error_msg}")
                return False, error_msg
                
        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            current_app.logger.error(f"❌ Test notification failed ({error_type}): {error_msg}")
            
            # Provide helpful error messages
            if "authentication" in error_msg.lower() or "auth" in error_msg.lower():
                return False, "Authentication failed. For Gmail, you MUST use an App Password (not your regular password). Generate one at: https://myaccount.google.com/apppasswords"
            elif "connection" in error_msg.lower() or "connect" in error_msg.lower():
                return False, f"Connection failed. Check your mail server ({current_app.config.get('MAIL_SERVER')}) and port ({current_app.config.get('MAIL_PORT')}) settings."
            elif "tls" in error_msg.lower() or "ssl" in error_msg.lower():
                return False, "TLS/SSL error. For port 587 use TLS=true, for port 465 use TLS=false (SSL)."
            elif "timeout" in error_msg.lower():
                # This shouldn't happen now due to socket.timeout, but keep as fallback
                return False, f"Connection timeout. Your cloud platform may be blocking SMTP connections on port {current_app.config.get('MAIL_PORT')}."
            else:
                return False, f"Email error ({error_type}): {error_msg}"
    
    return False, "Failed to send test email after all retry attempts."
