# Render Environment Setup Guide

## Your PostgreSQL Database Information
Based on what you provided:
- **Database Name**: `restaurant_pos_postgres`
- **Port**: `5432`
- **Username**: `restaurant_pos_postgres_user`

## Environment Variables to Set in Render

Go to your Render web service dashboard and add these environment variables:

### Required Variables

```bash
# Flask Configuration
FLASK_ENV=production
FLASK_APP=wsgi.py
SECRET_KEY=your-super-secret-key-here-change-this-to-something-random

# Database URL - Replace with your actual values from Render PostgreSQL dashboard
DATABASE_URL=postgresql://restaurant_pos_postgres_user:YOUR_PASSWORD@YOUR_HOST:5432/restaurant_pos_postgres

# Application Settings
TIMEZONE=Asia/Qatar
CURRENCY=QAR
LOG_LEVEL=INFO
LOG_TO_STDOUT=1

# Performance Optimizations
PYTHONUNBUFFERED=1
MALLOC_ARENA_MAX=2
PYTHONHASHSEED=random

# Security Settings
SESSION_COOKIE_SECURE=True
REMEMBER_COOKIE_SECURE=True
```

## How to Get Your Complete DATABASE_URL

1. Go to your Render Dashboard
2. Click on your PostgreSQL database (`restaurant_pos_postgres`)
3. In the database dashboard, you'll see connection details:
   - **Hostname**: Something like `dpg-xxxxx-a.oregon-postgres.render.com`
   - **Password**: The password you set or was generated
   - **Database**: `restaurant_pos_postgres`
   - **Username**: `restaurant_pos_postgres_user`
   - **Port**: `5432`

4. Your DATABASE_URL should look like this:
   ```
   postgresql://restaurant_pos_postgres_user:YOUR_PASSWORD@dpg-xxxxx-a.oregon-postgres.render.com:5432/restaurant_pos_postgres
   ```

## Important Notes

1. **Replace YOUR_PASSWORD**: Use the actual password from your PostgreSQL dashboard
2. **Replace YOUR_HOST**: Use the actual hostname from your PostgreSQL dashboard
3. **SECRET_KEY**: Generate a strong random secret key for production

## Example of Complete DATABASE_URL

If your PostgreSQL details are:
- Host: `dpg-abc123-a.oregon-postgres.render.com`
- Password: `mySecretPassword123`

Then your DATABASE_URL would be:
```
postgresql://restaurant_pos_postgres_user:mySecretPassword123@dpg-abc123-a.oregon-postgres.render.com:5432/restaurant_pos_postgres
```

## After Setting Environment Variables

1. **Redeploy** your web service
2. The build should now succeed
3. Your app will automatically initialize the database with default data
4. You can login with: `admin` / `admin123`

## Troubleshooting

If you still get connection errors:
1. Verify the DATABASE_URL is exactly as shown in your PostgreSQL dashboard
2. Make sure the PostgreSQL database is running
3. Check that the password doesn't contain special characters that need URL encoding
4. Ensure the database name matches exactly: `restaurant_pos_postgres`
