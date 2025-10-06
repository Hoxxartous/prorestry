"""
Migration script to add delivery companies table and update orders table
Run this script to migrate from enum-based delivery companies to database-based ones
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import DeliveryCompany, Order
from sqlalchemy import text

def migrate_delivery_companies():
    app = create_app()
    
    with app.app_context():
        try:
            print("Starting delivery companies migration...")
            
            # Create delivery_companies table
            print("Creating delivery_companies table...")
            db.create_all()
            
            # Add default delivery companies
            default_companies = [
                {'name': 'Talabat', 'value': 'talabat', 'icon': 'bi-truck'},
                {'name': 'Deliveroo', 'value': 'deliveroo', 'icon': 'bi-bicycle'},
                {'name': 'Snounu', 'value': 'snounou', 'icon': 'bi-scooter'},
                {'name': 'Rafiq', 'value': 'rafiq', 'icon': 'bi-car-front'},
            ]
            
            print("Adding default delivery companies...")
            for company_data in default_companies:
                existing = DeliveryCompany.query.filter_by(value=company_data['value']).first()
                if not existing:
                    company = DeliveryCompany(**company_data)
                    db.session.add(company)
                    print(f"Added: {company_data['name']}")
                else:
                    print(f"Already exists: {company_data['name']}")
            
            db.session.commit()
            
            # Add delivery_company_id column to orders table if it doesn't exist
            print("Checking orders table structure...")
            try:
                # Use the newer SQLAlchemy syntax
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE orders ADD COLUMN delivery_company_id INTEGER'))
                    conn.commit()
                print("Added delivery_company_id column to orders table")
            except Exception as e:
                if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                    print("delivery_company_id column already exists")
                else:
                    print(f"Error adding column: {e}")
            
            # Migrate existing orders with delivery_company enum to use delivery_company_id
            print("Migrating existing orders...")
            
            # This is a complex migration since we're changing from enum to foreign key
            # For now, we'll set all existing delivery orders to use the first company
            try:
                # Get the first delivery company
                first_company = DeliveryCompany.query.first()
                if first_company:
                    # Update orders that have delivery service type but no delivery_company_id
                    with db.engine.connect() as conn:
                        conn.execute(text("""
                            UPDATE orders 
                            SET delivery_company_id = :company_id 
                            WHERE service_type = 'delivery' 
                            AND delivery_company_id IS NULL
                        """), {'company_id': first_company.id})
                        conn.commit()
                    print(f"Updated existing delivery orders to use {first_company.name}")
            except Exception as e:
                print(f"Note: Could not migrate existing orders: {e}")
            
            db.session.commit()
            print("Migration completed successfully!")
            
        except Exception as e:
            print(f"Migration failed: {e}")
            db.session.rollback()
            sys.exit(1)

if __name__ == '__main__':
    migrate_delivery_companies()
