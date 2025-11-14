#!/bin/bash

# Apply Render Deployment Fixes
# This script should be run in the Render environment after deployment

echo "🚀 Applying Render deployment fixes..."

# Make sure we're in the right directory
cd /opt/render/project/src

# Install required dependencies if not already installed
echo "📦 Installing dependencies..."
pip install psycopg2-binary

# Run the fix script
echo "🔧 Running database fixes..."
python fix_render_deployment_issues.py

# Check if the script ran successfully
if [ $? -eq 0 ]; then
    echo "✅ Render deployment fixes applied successfully!"
else
    echo "❌ Failed to apply fixes. Check the logs above."
    exit 1
fi

echo "🎉 All fixes completed!"
