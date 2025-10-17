#!/usr/bin/env python3
"""
Production-ready migration script for Restaurant POS
Migrates data from SQLite to PostgreSQL for Render deployment
"""

import os
import sys
import sqlite3
import psycopg2
import logging
from urllib.parse import urlparse
from datetime import datetime
import json

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_database_connections():
    """Get SQLite source and PostgreSQL destination connections"""
    
    # SQLite source database
    sqlite_path = os.path.join('instance', 'restaurant_pos.db')
    if not os.path.exists(sqlite_path):
        logger.error(f"SQLite database not found at {sqlite_path}")
        return None, None
    
    # PostgreSQL destination database
    postgres_url = os.environ.get('DATABASE_URL')
    if not postgres_url:
        logger.error("DATABASE_URL environment variable not set")
        logger.info("Please set DATABASE_URL to your PostgreSQL connection string")
        return None, None
    
    # Parse PostgreSQL URL
    if postgres_url.startswith('postgres://'):
        postgres_url = postgres_url.replace('postgres://', 'postgresql://', 1)
    
    try:
        # Connect to SQLite
        sqlite_conn = sqlite3.connect(sqlite_path)
        sqlite_conn.row_factory = sqlite3.Row  # Enable column access by name
        logger.info(f"Connected to SQLite database: {sqlite_path}")
        
        # Connect to PostgreSQL
        postgres_conn = psycopg2.connect(postgres_url)
        logger.info("Connected to PostgreSQL database")
        
        return sqlite_conn, postgres_conn
        
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return None, None

def get_table_data(sqlite_conn, table_name):
    """Get all data from a SQLite table"""
    try:
        cursor = sqlite_conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        
        # Get column names
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in cursor.fetchall()]
        
        logger.info(f"Retrieved {len(rows)} rows from {table_name}")
        return rows, columns
    except Exception as e:
        logger.error(f"Error reading from {table_name}: {e}")
        return [], []

def migrate_table_data(sqlite_conn, postgres_conn, table_name, column_mapping=None):
    """Migrate data from SQLite table to PostgreSQL"""
    rows, columns = get_table_data(sqlite_conn, table_name)
    
    if not rows:
        logger.info(f"No data to migrate for {table_name}")
        return True
    
    try:
        postgres_cursor = postgres_conn.cursor()
        
        # Apply column mapping if provided
        if column_mapping and table_name in column_mapping:
            columns = [column_mapping[table_name].get(col, col) for col in columns]
        
        # Create INSERT statement
        placeholders = ', '.join(['%s'] * len(columns))
        columns_str = ', '.join(columns)
        insert_sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
        
        # Convert rows to tuples
        data_tuples = [tuple(row) for row in rows]
        
        # Execute batch insert
        postgres_cursor.executemany(insert_sql, data_tuples)
        postgres_conn.commit()
        
        logger.info(f"Successfully migrated {len(rows)} rows to {table_name}")
        return True
        
    except Exception as e:
        logger.error(f"Error migrating {table_name}: {e}")
        postgres_conn.rollback()
        return False

def create_postgresql_schema(postgres_conn):
    """Create PostgreSQL schema using Flask-SQLAlchemy models"""
    try:
        # Import Flask app to create tables
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from app import create_app, db
        from config import ProductionConfig
        
        app = create_app(ProductionConfig)
        with app.app_context():
            # Create all tables
            db.create_all()
            logger.info("PostgreSQL schema created successfully")
            return True
            
    except Exception as e:
        logger.error(f"Error creating PostgreSQL schema: {e}")
        return False

def main():
    """Main migration process"""
    logger.info("Starting Restaurant POS migration to PostgreSQL")
    
    # Get database connections
    sqlite_conn, postgres_conn = get_database_connections()
    if not sqlite_conn or not postgres_conn:
        return False
    
    try:
        # Create PostgreSQL schema
        logger.info("Creating PostgreSQL schema...")
        if not create_postgresql_schema(postgres_conn):
            return False
        
        # Define migration order (respecting foreign key constraints)
        migration_order = [
            'branches',
            'users',
            'user_branch_assignments',
            'categories',
            'menu_items',
            'tables',
            'customers',
            'delivery_companies',
            'orders',
            'order_items',
            'payments',
            'order_edit_history',
            'audit_logs',
            'inventory_items',
            'notifications',
            'cashier_sessions',
            'order_counters'
        ]
        
        # Migrate each table
        success_count = 0
        for table_name in migration_order:
            logger.info(f"Migrating table: {table_name}")
            if migrate_table_data(sqlite_conn, postgres_conn, table_name):
                success_count += 1
            else:
                logger.warning(f"Failed to migrate {table_name}, continuing...")
        
        logger.info(f"Migration completed: {success_count}/{len(migration_order)} tables migrated successfully")
        
        # Update sequences for auto-increment columns
        logger.info("Updating PostgreSQL sequences...")
        update_sequences(postgres_conn)
        
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False
        
    finally:
        sqlite_conn.close()
        postgres_conn.close()

def update_sequences(postgres_conn):
    """Update PostgreSQL sequences to match current max IDs"""
    try:
        cursor = postgres_conn.cursor()
        
        # Tables with auto-increment primary keys
        tables_with_sequences = [
            'branches', 'users', 'user_branch_assignments', 'categories', 
            'menu_items', 'tables', 'customers', 'delivery_companies',
            'orders', 'order_items', 'payments', 'order_edit_history',
            'audit_logs', 'inventory_items', 'notifications', 
            'cashier_sessions', 'order_counters'
        ]
        
        for table in tables_with_sequences:
            try:
                # Get current max ID
                cursor.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table}")
                max_id = cursor.fetchone()[0]
                
                if max_id > 0:
                    # Update sequence
                    sequence_name = f"{table}_id_seq"
                    cursor.execute(f"SELECT setval('{sequence_name}', {max_id})")
                    logger.info(f"Updated sequence {sequence_name} to {max_id}")
                    
            except Exception as e:
                logger.warning(f"Could not update sequence for {table}: {e}")
        
        postgres_conn.commit()
        logger.info("Sequence updates completed")
        
    except Exception as e:
        logger.error(f"Error updating sequences: {e}")

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
