#!/bin/bash
# Build script for Render deployment with PostgreSQL optimization

set -e  # Exit on any error

echo "🚀 Starting Restaurant POS build for Render deployment..."
echo "🐘 PostgreSQL + ⚡ Maximum Performance Configuration"

# Update pip and install dependencies
echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Verify PostgreSQL driver installation
echo "🔍 Verifying PostgreSQL driver..."
python -c "
try:
    import psycopg2
    print('✅ PostgreSQL driver (psycopg2) installed successfully')
except ImportError:
    try:
        import psycopg
        print('✅ PostgreSQL driver (psycopg) installed successfully')
    except ImportError:
        print('❌ No PostgreSQL driver found')
        exit(1)
"

# Verify eventlet installation for async performance
echo "🔍 Verifying async libraries..."
python -c "import eventlet; print('✅ Eventlet installed successfully')"

# Set up environment for production
export FLASK_ENV=production
export PYTHONUNBUFFERED=1

# Create necessary directories
echo "📁 Creating application directories..."
mkdir -p logs
mkdir -p instance
mkdir -p migrations

# Check if database needs initialization
if [ -n "$DATABASE_URL" ]; then
    echo "🗄️  Database URL detected, checking if database needs setup..."
    
    # Create a simple database check script to avoid eventlet conflicts
    python -c "
import os
import sys
os.environ['DEPLOYMENT_MODE'] = 'true'  # Skip eventlet monkey patching

try:
    from config import ProductionConfig
    from flask import Flask
    from flask_sqlalchemy import SQLAlchemy
    from sqlalchemy import inspect, text
    
    # Create minimal app for database check only
    app = Flask(__name__)
    app.config.from_object(ProductionConfig)
    db = SQLAlchemy()
    db.init_app(app)
    
    with app.app_context():
        # Check if database has tables
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()
        
        if len(existing_tables) > 0:
            print(f'✅ Database found with {len(existing_tables)} tables')
            print('   Will verify and update schema if needed')
            sys.exit(2)  # Database exists, run setup but skip full initialization
        else:
            print('🔧 Database is empty, full initialization needed')
            sys.exit(1)  # Database needs full initialization
            
except Exception as e:
    print(f'⚠️  Could not check database status: {e}')
    print('   Will attempt initialization on first run')
    sys.exit(0)  # Skip initialization, let app handle it
"
    
    # Check the exit code from the database check
    DB_CHECK_RESULT=$?
    
    if [ $DB_CHECK_RESULT -eq 1 ]; then
        echo "🚀 Running full database initialization (first-time setup)..."
        python deploy_to_render.py
    elif [ $DB_CHECK_RESULT -eq 2 ]; then
        echo "🔧 Running database schema verification (existing database)..."
        python deploy_to_render.py --existing-database
    else
        echo "✅ Database setup skipped - will be handled on startup"
    fi
else
    echo "⚠️  DATABASE_URL not set, skipping database setup"
    echo "   Database will be set up on first run"
fi

# Collect static files (if needed)
echo "📄 Preparing static files..."
# Add any static file collection here if needed

echo "✅ Build completed successfully!"
echo "🎯 Restaurant POS is ready for maximum performance deployment!"
