#!/usr/bin/env python3
"""
Production cleanup script - removes all unnecessary files for deployment
"""

import os
import shutil
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def cleanup_production():
    """Remove unnecessary files and directories for production deployment"""
    
    # Files to remove
    files_to_remove = [
        'debug_login.py',
        'start_eventlet_server.py', 
        'start_gunicorn.py',
        'start_waitress_server.py',
        'start_server.bat',
        'run_performance_test.bat',
        'restaurant-pos.service',
        'migrate_to_postgresql.py',
        'run_migration.py',
        'performance_monitor.py',
        'postgresql_optimizations.py',
        'deploy_to_render.py',
        'waiter_requests_edit_functions.js',
        'MIGRATION_TESTING.md',
        'RENDER_DEPLOYMENT_SUMMARY.md',
        'DEPLOYMENT_GUIDE.md'
    ]
    
    # Directories to remove
    dirs_to_remove = [
        'instance',
        '__pycache__',
        'logs'
    ]
    
    # Remove files
    for file_name in files_to_remove:
        if os.path.exists(file_name):
            try:
                os.remove(file_name)
                logger.info(f"Removed file: {file_name}")
            except Exception as e:
                logger.warning(f"Could not remove {file_name}: {e}")
    
    # Remove directories
    for dir_name in dirs_to_remove:
        if os.path.exists(dir_name):
            try:
                shutil.rmtree(dir_name)
                logger.info(f"Removed directory: {dir_name}")
            except Exception as e:
                logger.warning(f"Could not remove {dir_name}: {e}")
    
    # Clean up __pycache__ directories recursively
    for root, dirs, files in os.walk('.'):
        for dir_name in dirs[:]:  # Use slice to avoid modifying list during iteration
            if dir_name == '__pycache__':
                pycache_path = os.path.join(root, dir_name)
                try:
                    shutil.rmtree(pycache_path)
                    logger.info(f"Removed __pycache__: {pycache_path}")
                    dirs.remove(dir_name)  # Remove from dirs list
                except Exception as e:
                    logger.warning(f"Could not remove {pycache_path}: {e}")
    
    logger.info("Production cleanup completed")

if __name__ == '__main__':
    cleanup_production()
