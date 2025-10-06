#!/usr/bin/env python3
"""
Database Health Check Utility for Restaurant POS
Monitors SQLite WAL mode, connection pooling, and performance metrics
"""

import os
import sys
import sqlite3
import time
from datetime import datetime
from pathlib import Path

def check_sqlite_wal_mode(db_path):
    """Check if SQLite database is using WAL mode"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check journal mode
        cursor.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        
        # Check other important settings
        cursor.execute("PRAGMA synchronous")
        synchronous = cursor.fetchone()[0]
        
        cursor.execute("PRAGMA cache_size")
        cache_size = cursor.fetchone()[0]
        
        cursor.execute("PRAGMA busy_timeout")
        busy_timeout = cursor.fetchone()[0]
        
        cursor.execute("PRAGMA foreign_keys")
        foreign_keys = cursor.fetchone()[0]
        
        # Check WAL file existence
        wal_file = f"{db_path}-wal"
        wal_exists = os.path.exists(wal_file)
        wal_size = os.path.getsize(wal_file) if wal_exists else 0
        
        # Check SHM file existence
        shm_file = f"{db_path}-shm"
        shm_exists = os.path.exists(shm_file)
        
        conn.close()
        
        return {
            'journal_mode': journal_mode,
            'synchronous': synchronous,
            'cache_size': cache_size,
            'busy_timeout': busy_timeout,
            'foreign_keys': foreign_keys,
            'wal_file_exists': wal_exists,
            'wal_file_size': wal_size,
            'shm_file_exists': shm_exists,
            'is_wal_enabled': journal_mode.upper() == 'WAL'
        }
        
    except Exception as e:
        return {'error': str(e)}

def check_database_performance(db_path, test_queries=True):
    """Check database performance metrics"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get database size
        cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
        db_size = cursor.fetchone()[0]
        
        # Get table count
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count = cursor.fetchone()[0]
        
        # Get index count
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index'")
        index_count = cursor.fetchone()[0]
        
        performance_metrics = {
            'database_size_bytes': db_size,
            'database_size_mb': round(db_size / (1024 * 1024), 2),
            'table_count': table_count,
            'index_count': index_count,
        }
        
        if test_queries:
            # Test query performance
            start_time = time.time()
            cursor.execute("SELECT COUNT(*) FROM sqlite_master")
            cursor.fetchone()
            query_time = time.time() - start_time
            performance_metrics['test_query_time_ms'] = round(query_time * 1000, 2)
        
        conn.close()
        return performance_metrics
        
    except Exception as e:
        return {'error': str(e)}

def check_connection_pool_health():
    """Check SQLAlchemy connection pool health (requires app context)"""
    try:
        from app import create_app, db
        from config import Config
        
        app = create_app(Config)
        with app.app_context():
            # Get engine info
            engine = db.engine
            pool = engine.pool
            
            return {
                'pool_size': pool.size(),
                'checked_in_connections': pool.checkedin(),
                'checked_out_connections': pool.checkedout(),
                'overflow_connections': pool.overflow(),
                'total_connections': pool.size() + pool.overflow(),
            }
            
    except Exception as e:
        return {'error': str(e)}

def run_comprehensive_health_check():
    """Run comprehensive database health check"""
    print("=" * 60)
    print("RESTAURANT POS - DATABASE HEALTH CHECK")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Find database files
    db_files = [
        'restaurant_pos.db',
        'restaurant_pos_dev.db',
        'instance/restaurant_pos.db'
    ]
    
    for db_file in db_files:
        if os.path.exists(db_file):
            print(f"[DATABASE] CHECKING: {db_file}")
            print("-" * 40)
            
            # Check WAL mode
            wal_info = check_sqlite_wal_mode(db_file)
            if 'error' not in wal_info:
                print(f"[OK] Journal Mode: {wal_info['journal_mode']}")
                print(f"[OK] WAL Enabled: {'Yes' if wal_info['is_wal_enabled'] else 'No'}")
                print(f"[OK] WAL File Exists: {'Yes' if wal_info['wal_file_exists'] else 'No'}")
                if wal_info['wal_file_exists']:
                    print(f"[OK] WAL File Size: {wal_info['wal_file_size']} bytes")
                print(f"[OK] SHM File Exists: {'Yes' if wal_info['shm_file_exists'] else 'No'}")
                print(f"[OK] Synchronous Mode: {wal_info['synchronous']}")
                print(f"[OK] Cache Size: {wal_info['cache_size']} pages")
                print(f"[OK] Busy Timeout: {wal_info['busy_timeout']} ms")
                print(f"[OK] Foreign Keys: {'Enabled' if wal_info['foreign_keys'] else 'Disabled'}")
            else:
                print(f"[ERROR] Error checking WAL mode: {wal_info['error']}")
            
            print()
            
            # Check performance
            perf_info = check_database_performance(db_file)
            if 'error' not in perf_info:
                print(f"[PERF] Database Size: {perf_info['database_size_mb']} MB")
                print(f"[PERF] Table Count: {perf_info['table_count']}")
                print(f"[PERF] Index Count: {perf_info['index_count']}")
                if 'test_query_time_ms' in perf_info:
                    print(f"[PERF] Test Query Time: {perf_info['test_query_time_ms']} ms")
            else:
                print(f"[ERROR] Error checking performance: {perf_info['error']}")
            
            print()
    
    # Check connection pool
    print("[CONNECTION POOL] STATUS")
    print("-" * 40)
    pool_info = check_connection_pool_health()
    if 'error' not in pool_info:
        print(f"[OK] Pool Size: {pool_info['pool_size']}")
        print(f"[OK] Checked In: {pool_info['checked_in_connections']}")
        print(f"[OK] Checked Out: {pool_info['checked_out_connections']}")
        print(f"[OK] Overflow: {pool_info['overflow_connections']}")
        print(f"[OK] Total Connections: {pool_info['total_connections']}")
    else:
        print(f"[ERROR] Error checking connection pool: {pool_info['error']}")
    
    print()
    print("=" * 60)
    print("HEALTH CHECK COMPLETED")
    print("=" * 60)

def enable_wal_mode_manually(db_path):
    """Manually enable WAL mode for existing database"""
    try:
        print(f"[SETUP] Enabling WAL mode for {db_path}...")
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Enable WAL mode
        cursor.execute("PRAGMA journal_mode=WAL")
        result = cursor.fetchone()[0]
        
        # Apply optimizations
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=10000")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA optimize")
        
        conn.close()
        
        print(f"[OK] WAL mode enabled successfully. Journal mode: {result}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Error enabling WAL mode: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--enable-wal":
            # Enable WAL mode for all found databases
            db_files = ['restaurant_pos.db', 'restaurant_pos_dev.db']
            for db_file in db_files:
                if os.path.exists(db_file):
                    enable_wal_mode_manually(db_file)
        elif sys.argv[1] == "--check":
            run_comprehensive_health_check()
        else:
            print("Usage:")
            print("  python db_health_check.py --check        # Run health check")
            print("  python db_health_check.py --enable-wal   # Enable WAL mode")
    else:
        run_comprehensive_health_check()
