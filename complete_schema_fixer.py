#!/usr/bin/env python3
"""
Complete Database Schema Fixer for Restaurant POS
Analyzes all models and ensures ALL columns exist in PostgreSQL
"""

import os
import sys
import logging
from sqlalchemy import text, inspect
from sqlalchemy.exc import ProgrammingError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_model_columns():
    """Extract all columns from SQLAlchemy models"""
    try:
        from app import create_app, db
        from config import ProductionConfig
        from app.models import (
            Branch, User, UserBranchAssignment, Category, MenuItem, Table, Customer, 
            Order, OrderItem, Payment, AuditLog, InventoryItem, Notification, 
            CashierSession, OrderCounter, DeliveryCompany, CashierUiPreference, 
            CashierUiSetting, AppSettings, AdminPinCode, CashierPin, 
            WaiterCashierAssignment, ManualCardPayment, OrderEditHistory,
            Kitchen, CategoryKitchenAssignment, KitchenOrder, KitchenOrderItem,
            CategorySpecialItemAssignment, EmailConfiguration
        )
        
        app = create_app(ProductionConfig)
        
        with app.app_context():
            # Get all model classes
            models = [
                Branch, User, UserBranchAssignment, Category, MenuItem, Table, Customer, 
                Order, OrderItem, Payment, AuditLog, InventoryItem, Notification, 
                CashierSession, OrderCounter, DeliveryCompany, CashierUiPreference, 
                CashierUiSetting, AppSettings, AdminPinCode, CashierPin, 
                WaiterCashierAssignment, ManualCardPayment, OrderEditHistory,
                Kitchen, CategoryKitchenAssignment, KitchenOrder, KitchenOrderItem,
                CategorySpecialItemAssignment, EmailConfiguration
            ]
            
            model_schema = {}
            
            for model in models:
                table_name = model.__tablename__
                columns = {}
                
                # Get all columns from the model
                for column_name, column in model.__table__.columns.items():
                    column_type = str(column.type)
                    nullable = column.nullable
                    default = column.default
                    
                    columns[column_name] = {
                        'type': column_type,
                        'nullable': nullable,
                        'default': default
                    }
                
                model_schema[table_name] = columns
                logger.info(f"Analyzed model {model.__name__}: {len(columns)} columns")
            
            return model_schema
            
    except Exception as e:
        logger.error(f"Error analyzing models: {e}")
        return {}

def get_database_schema():
    """Get current database schema from PostgreSQL"""
    try:
        from app import create_app, db
        from config import ProductionConfig
        
        app = create_app(ProductionConfig)
        
        with app.app_context():
            # Get database inspector
            inspector = inspect(db.engine)
            
            db_schema = {}
            
            # Get all tables
            tables = inspector.get_table_names()
            
            for table_name in tables:
                columns = {}
                
                # Get columns for each table
                for column in inspector.get_columns(table_name):
                    columns[column['name']] = {
                        'type': str(column['type']),
                        'nullable': column['nullable'],
                        'default': column.get('default')
                    }
                
                db_schema[table_name] = columns
                logger.info(f"Found database table {table_name}: {len(columns)} columns")
            
            return db_schema
            
    except Exception as e:
        logger.error(f"Error reading database schema: {e}")
        return {}

def generate_missing_columns_sql():
    """Generate SQL statements for all missing columns"""
    model_schema = get_model_columns()
    db_schema = get_database_schema()
    
    missing_columns = []
    
    for table_name, model_columns in model_schema.items():
        db_columns = db_schema.get(table_name, {})
        
        for column_name, column_info in model_columns.items():
            if column_name not in db_columns:
                # Column is missing, generate SQL to add it
                sql_type = convert_sqlalchemy_type_to_postgres(column_info['type'])
                nullable = "NULL" if column_info['nullable'] else "NOT NULL"
                
                # Handle defaults
                default_clause = ""
                if column_info['default'] is not None:
                    default_value = get_default_value(column_info['default'], column_info['type'])
                    if default_value:
                        default_clause = f" DEFAULT {default_value}"
                
                sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}{default_clause}"
                if not column_info['nullable']:
                    sql += f" {nullable}"
                
                missing_columns.append({
                    'table': table_name,
                    'column': column_name,
                    'sql': sql,
                    'type': column_info['type']
                })
                
                logger.info(f"Missing column: {table_name}.{column_name} ({column_info['type']})")
    
    return missing_columns

def convert_sqlalchemy_type_to_postgres(sqlalchemy_type):
    """Convert SQLAlchemy type to PostgreSQL type"""
    type_str = sqlalchemy_type.upper()
    
    # Handle common type mappings
    if 'INTEGER' in type_str:
        return 'INTEGER'
    elif 'VARCHAR' in type_str:
        # Extract length if present
        if '(' in type_str:
            return type_str.replace('VARCHAR', 'VARCHAR')
        return 'VARCHAR(255)'
    elif 'TEXT' in type_str:
        return 'TEXT'
    elif 'BOOLEAN' in type_str:
        return 'BOOLEAN'
    elif 'DATETIME' in type_str:
        return 'TIMESTAMP'
    elif 'DATE' in type_str:
        return 'DATE'
    elif 'NUMERIC' in type_str:
        return type_str.replace('NUMERIC', 'NUMERIC')
    elif 'DECIMAL' in type_str:
        return type_str.replace('DECIMAL', 'DECIMAL')
    elif 'ENUM' in type_str:
        return 'VARCHAR(50)'  # Use VARCHAR for enums
    else:
        return 'TEXT'  # Default fallback

def get_default_value(default_obj, column_type):
    """Get appropriate default value for PostgreSQL"""
    if default_obj is None:
        return None
    
    # Handle SQLAlchemy default objects
    if hasattr(default_obj, 'arg'):
        # Extract the actual default value from SQLAlchemy default object
        actual_value = default_obj.arg
        if actual_value is None:
            return None
        
        # Handle different value types
        if isinstance(actual_value, (int, float)):
            return str(actual_value)
        elif isinstance(actual_value, bool):
            return 'TRUE' if actual_value else 'FALSE'
        elif isinstance(actual_value, str):
            return f"'{actual_value}'"
        else:
            # Convert to string and handle as before
            default_str = str(actual_value)
    else:
        # Handle different default types as string
        default_str = str(default_obj)
    
    if 'datetime.utcnow' in default_str or 'func.now()' in default_str:
        return 'CURRENT_TIMESTAMP'
    elif 'True' in default_str and 'BOOLEAN' in column_type.upper():
        return 'TRUE'
    elif 'False' in default_str and 'BOOLEAN' in column_type.upper():
        return 'FALSE'
    elif default_str.isdigit():
        return default_str
    elif default_str.replace('.', '').isdigit():
        return default_str
    else:
        # For ScalarElementColumnDefault and other complex objects, try to extract numeric values
        if 'ScalarElementColumnDefault' in default_str:
            # Extract numeric value from ScalarElementColumnDefault(value)
            import re
            match = re.search(r'ScalarElementColumnDefault\(([^)]+)\)', default_str)
            if match:
                value = match.group(1)
                # Remove quotes if present
                value = value.strip('\'"')
                try:
                    # Try to convert to float to validate it's numeric
                    float(value)
                    return value
                except ValueError:
                    pass
        
        return f"'{default_str}'"

def fix_all_missing_columns():
    """Fix all missing columns in the database"""
    try:
        from app import create_app, db
        from config import ProductionConfig
        
        app = create_app(ProductionConfig)
        
        with app.app_context():
            logger.info("Starting comprehensive database schema fix...")
            
            # Generate missing columns
            missing_columns = generate_missing_columns_sql()
            
            if not missing_columns:
                logger.info("✅ All columns are present in the database!")
                return True
            
            logger.info(f"Found {len(missing_columns)} missing columns to add")
            
            # Execute SQL statements to add missing columns
            success_count = 0
            
            for column_info in missing_columns:
                try:
                    logger.info(f"Adding column: {column_info['table']}.{column_info['column']}")
                    logger.info(f"SQL: {column_info['sql']}")
                    
                    db.session.execute(text(column_info['sql']))
                    db.session.commit()
                    
                    success_count += 1
                    logger.info(f"✅ Added {column_info['table']}.{column_info['column']}")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to add {column_info['table']}.{column_info['column']}: {e}")
                    db.session.rollback()
            
            logger.info(f"Schema fix completed: {success_count}/{len(missing_columns)} columns added successfully")
            
            # Create any missing tables
            logger.info("Ensuring all tables exist...")
            db.create_all()
            logger.info("✅ All tables verified/created")
            
            return success_count == len(missing_columns)
            
    except Exception as e:
        logger.error(f"Failed to fix database schema: {e}")
        return False

def create_missing_tables():
    """Ensure all model tables exist"""
    try:
        from app import create_app, db
        from config import ProductionConfig
        
        app = create_app(ProductionConfig)
        
        with app.app_context():
            logger.info("Creating any missing tables...")
            db.create_all()
            logger.info("✅ All tables created/verified")
            return True
            
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        return False

def verify_schema():
    """Verify that all columns now exist"""
    try:
        model_schema = get_model_columns()
        db_schema = get_database_schema()
        
        missing_count = 0
        
        for table_name, model_columns in model_schema.items():
            db_columns = db_schema.get(table_name, {})
            
            for column_name in model_columns.keys():
                if column_name not in db_columns:
                    logger.error(f"❌ Still missing: {table_name}.{column_name}")
                    missing_count += 1
        
        if missing_count == 0:
            logger.info("✅ Schema verification passed - all columns present!")
            return True
        else:
            logger.error(f"❌ Schema verification failed - {missing_count} columns still missing")
            return False
            
    except Exception as e:
        logger.error(f"Error verifying schema: {e}")
        return False

def fix_userrole_enum():
    """Fix UserRole enum values and invalid user roles"""
    try:
        from app import create_app, db
        from config import ProductionConfig
        
        app = create_app(ProductionConfig)
        
        with app.app_context():
            logger.info("🔧 Fixing UserRole enum and user role values...")
            
            # Get raw database connection
            connection = db.engine.raw_connection()
            cursor = connection.cursor()
            
            try:
                # Check current enum values
                cursor.execute("""
                    SELECT enumlabel 
                    FROM pg_enum 
                    WHERE enumtypid = (
                        SELECT oid 
                        FROM pg_type 
                        WHERE typname = 'userrole'
                    );
                """)
                
                existing_values = [row[0] for row in cursor.fetchall()]
                logger.info(f"Current UserRole enum values: {existing_values}")
                
                # Define expected values (lowercase as per Python enum)
                expected_values = [
                    'super_user', 'it_admin', 'branch_admin', 
                    'manager', 'cashier', 'waiter', 'kitchen'
                ]
                
                # Add missing enum values
                for value in expected_values:
                    if value not in existing_values:
                        try:
                            cursor.execute(f"ALTER TYPE userrole ADD VALUE '{value}';")
                            logger.info(f"✅ Added '{value}' to UserRole enum")
                            connection.commit()
                        except Exception as e:
                            if "already exists" in str(e):
                                logger.info(f"ℹ️ Value '{value}' already exists in UserRole enum")
                            else:
                                logger.warning(f"⚠️ Could not add '{value}' to UserRole enum: {e}")
                
                # Fix users with invalid role values
                # First, check what invalid roles exist
                cursor.execute("""
                    SELECT DISTINCT role FROM users 
                    WHERE role NOT IN ('super_user', 'it_admin', 'branch_admin', 'manager', 'cashier', 'waiter', 'kitchen');
                """)
                
                invalid_roles = [row[0] for row in cursor.fetchall()]
                logger.info(f"Found invalid roles in database: {invalid_roles}")
                
                # Map invalid roles to valid ones
                role_mappings = {
                    'IT_ADMIN': 'it_admin',
                    'SUPER_USER': 'super_user',
                    'BRANCH_ADMIN': 'branch_admin',
                    'MANAGER': 'manager',
                    'CASHIER': 'cashier',
                    'WAITER': 'waiter',
                    'KITCHEN': 'kitchen'
                }
                
                # Only try to fix roles that actually exist in the database
                for old_role in invalid_roles:
                    if old_role in role_mappings:
                        new_role = role_mappings[old_role]
                        try:
                            # Use a more robust approach with explicit casting
                            cursor.execute(f"""
                                UPDATE users 
                                SET role = '{new_role}'::userrole 
                                WHERE role::text = '{old_role}';
                            """)
                            if cursor.rowcount > 0:
                                logger.info(f"✅ Fixed {cursor.rowcount} users: {old_role} -> {new_role}")
                                connection.commit()
                        except Exception as e:
                            logger.warning(f"⚠️ Could not fix role {old_role}: {e}")
                            # Try alternative approach - set to default role
                            try:
                                cursor.execute(f"""
                                    UPDATE users 
                                    SET role = 'cashier'::userrole 
                                    WHERE role::text = '{old_role}';
                                """)
                                if cursor.rowcount > 0:
                                    logger.info(f"✅ Set {cursor.rowcount} users with role {old_role} to default 'cashier'")
                                    connection.commit()
                            except Exception as e2:
                                logger.error(f"❌ Failed to fix role {old_role}: {e2}")
                    else:
                        # Unknown role - set to default
                        try:
                            cursor.execute(f"""
                                UPDATE users 
                                SET role = 'cashier'::userrole 
                                WHERE role::text = '{old_role}';
                            """)
                            if cursor.rowcount > 0:
                                logger.info(f"✅ Set {cursor.rowcount} users with unknown role {old_role} to 'cashier'")
                                connection.commit()
                        except Exception as e:
                            logger.error(f"❌ Failed to fix unknown role {old_role}: {e}")
                
                # Check for any remaining invalid roles
                cursor.execute("""
                    SELECT COUNT(*) FROM users 
                    WHERE role NOT IN ('super_user', 'it_admin', 'branch_admin', 'manager', 'cashier', 'waiter', 'kitchen');
                """)
                
                invalid_count = cursor.fetchone()[0]
                if invalid_count > 0:
                    logger.warning(f"⚠️ Found {invalid_count} users with invalid roles - setting to 'cashier'")
                    cursor.execute("""
                        UPDATE users SET role = 'cashier' 
                        WHERE role NOT IN ('super_user', 'it_admin', 'branch_admin', 'manager', 'cashier', 'waiter', 'kitchen');
                    """)
                    connection.commit()
                    logger.info(f"✅ Fixed {cursor.rowcount} users with invalid roles")
                
                logger.info("✅ UserRole enum fixes completed successfully")
                return True
                
            finally:
                cursor.close()
                connection.close()
                
    except Exception as e:
        logger.error(f"❌ Failed to fix UserRole enum: {e}")
        return False

def main():
    """Main execution function"""
    logger.info("🔧 Starting Complete Database Schema Fix")
    
    # Step 1: Create missing tables
    if not create_missing_tables():
        logger.error("Failed to create tables")
        return False
    
    # Step 2: Fix missing columns
    if not fix_all_missing_columns():
        logger.error("Failed to fix all columns")
        return False
    
    # Step 3: Fix UserRole enum issues
    if not fix_userrole_enum():
        logger.error("Failed to fix UserRole enum")
        return False
    
    # Step 4: Verify schema
    if not verify_schema():
        logger.error("Schema verification failed")
        return False
    
    logger.info("🎉 Complete database schema fix completed successfully!")
    logger.info("Your Restaurant POS database is now fully up-to-date!")
    
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
