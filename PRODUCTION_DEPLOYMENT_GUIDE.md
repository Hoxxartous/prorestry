# Restaurant POS - Production Deployment Guide

## 🚀 Render Free Plan Deployment with PostgreSQL

This guide will help you deploy your Restaurant POS system to Render's free plan with PostgreSQL database.

### ✅ Pre-Migration Checklist

Your app has been optimized for production with the following changes:

- ✅ **SQLite removed**: All SQLite dependencies and files removed
- ✅ **PostgreSQL optimized**: Connection pooling configured for free plan
- ✅ **Concurrency optimized**: Single worker with eventlet for maximum efficiency
- ✅ **Memory optimized**: Minimal resource usage for free plan
- ✅ **Production ready**: All development files removed

### 📋 Deployment Steps

#### 1. Create PostgreSQL Database on Render

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click "New" → "PostgreSQL"
3. Configure:
   - **Name**: `restaurant-pos-postgres`
   - **Database Name**: `restaurant_pos`
   - **User**: `restaurant_user`
   - **Plan**: `Free`
4. Click "Create Database"
5. **Save the DATABASE_URL** - you'll need it for the web service

#### 2. Create Web Service on Render

1. Click "New" → "Web Service"
2. Connect your GitHub repository
3. Configure:
   - **Name**: `restaurant-pos`
   - **Runtime**: `Python 3`
   - **Build Command**: `chmod +x build.sh && ./build.sh`
   - **Start Command**: `gunicorn --config gunicorn.conf.py wsgi:app`
   - **Plan**: `Free`

#### 3. Set Environment Variables

Add these environment variables in Render:

```bash
# Required Variables
FLASK_ENV=production
FLASK_APP=wsgi.py
SECRET_KEY=your-super-secret-key-here-change-this
DATABASE_URL=postgresql://username:password@hostname:port/database_name

# Application Settings
TIMEZONE=Asia/Qatar
CURRENCY=QAR
LOG_LEVEL=INFO
LOG_TO_STDOUT=1

# Performance Optimizations
PYTHONUNBUFFERED=1
MALLOC_ARENA_MAX=2
PYTHONHASHSEED=random

# Security (for HTTPS)
SESSION_COOKIE_SECURE=True
REMEMBER_COOKIE_SECURE=True
```

**Important**: Replace `DATABASE_URL` with the actual URL from your PostgreSQL database.

#### 4. Deploy

1. Click "Create Web Service"
2. Render will automatically build and deploy your app
3. The build process will:
   - Install dependencies
   - Set up PostgreSQL connection
   - Initialize database with default data
   - Start the application

### 🔄 Data Migration (If You Have Existing Data)

If you have existing data in SQLite that you want to migrate:

1. **Before deployment**, run the migration script locally:
   ```bash
   # Set your Render PostgreSQL URL
   export DATABASE_URL="your-render-postgresql-url"
   
   # Run migration
   python migrate_data_to_postgresql.py
   ```

2. This will copy all data from your SQLite database to PostgreSQL

### 🎯 Free Plan Optimizations

Your app is optimized for Render's free plan:

- **Single Worker**: Uses 1 worker to minimize memory usage
- **Eventlet**: Async worker for handling multiple connections efficiently  
- **Connection Pooling**: 2 connections max, 3 overflow for PostgreSQL
- **Memory Efficient**: Removed unnecessary dependencies
- **Fast Startup**: Preloaded app for faster response times

### 🔧 Multi-User Concurrency Features

Your app supports multiple users simultaneously:

- **Async WebSocket Support**: Real-time updates for all users
- **Database Connection Pooling**: Efficient database access
- **Session Management**: Proper user session handling
- **Branch Isolation**: Multi-branch support with data isolation

### 📊 Default Data

The app will initialize with:

- **Default Branch**: "Main Branch" 
- **Super User**: Username `admin`, Password `admin123`
- **Sample Categories**: Appetizers, Main Courses, Beverages, Desserts
- **Sample Menu Items**: Various food items with prices
- **Tables**: Table 1-10 with different capacities

### 🔐 Security Notes

1. **Change Default Password**: Login and change the admin password immediately
2. **Secret Key**: Use a strong, unique SECRET_KEY in production
3. **HTTPS**: Render provides HTTPS automatically
4. **Database**: PostgreSQL connection is encrypted

### 🚨 Troubleshooting

#### Build Fails
- Check that all environment variables are set
- Verify DATABASE_URL format is correct
- Check build logs for specific errors

#### Database Connection Issues
- Verify DATABASE_URL is correct
- Check PostgreSQL database is running
- Ensure database allows connections from Render

#### Performance Issues
- Monitor memory usage in Render dashboard
- Check database connection pool settings
- Review application logs

### 📈 Monitoring

Monitor your app:
- **Render Dashboard**: View logs, metrics, and performance
- **Database Metrics**: Monitor PostgreSQL usage
- **Application Logs**: Check for errors and performance issues

### 🔄 Updates and Maintenance

To update your app:
1. Push changes to your GitHub repository
2. Render will automatically redeploy
3. Database schema changes will be applied automatically

### 💡 Tips for Free Plan

1. **Sleep Mode**: Free plan apps sleep after 15 minutes of inactivity
2. **Cold Starts**: First request after sleep may be slower
3. **Database Limits**: Free PostgreSQL has connection and storage limits
4. **Upgrade Path**: Easy upgrade to paid plans for more resources

### 🎉 Success!

Once deployed, your Restaurant POS will be available at:
`https://your-app-name.onrender.com`

Login with:
- **Username**: `admin`
- **Password**: `admin123`

**Remember to change the default password immediately!**

---

## 📞 Support

If you encounter issues:
1. Check Render build and runtime logs
2. Verify all environment variables are set correctly
3. Ensure PostgreSQL database is accessible
4. Review this guide for common solutions
