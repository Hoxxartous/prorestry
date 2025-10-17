# 🔍 Migration Testing Guide

This guide explains how to test your PostgreSQL migration before deploying to production.

## 📋 Testing Scripts

### 1. **Quick Schema Test** (`quick_schema_test.py`)
**Purpose**: Validates models and configuration without requiring PostgreSQL
**When to use**: Before migration, during development

```bash
python quick_schema_test.py
```

**What it tests**:
- ✅ All Flask models can be imported
- ✅ Models have proper table definitions
- ✅ Model relationships are defined
- ✅ Enum classes are properly configured
- ✅ Database configuration is valid
- ✅ Required migration files exist
- ✅ PostgreSQL dependencies are installed

### 2. **Full Migration Test** (`test_migration.py`)
**Purpose**: Comprehensive testing with actual PostgreSQL database
**When to use**: After setting up PostgreSQL, before deployment

```bash
# Set your PostgreSQL URL
export DATABASE_URL="postgresql://username:password@host:port/database"

# Run comprehensive tests
python test_migration.py
```

**What it tests**:
- ✅ Database connections (SQLite → PostgreSQL)
- ✅ All Flask models map to database tables
- ✅ Table schemas match between databases
- ✅ Data migration is complete and accurate
- ✅ Foreign key relationships are preserved
- ✅ Database indexes are created
- ✅ Flask application starts with PostgreSQL

## 🚀 Testing Workflow

### Step 1: Quick Schema Validation
```bash
# Test models and configuration
python quick_schema_test.py
```

**Expected Output**:
```
🔍 Restaurant POS Quick Schema Test
✅ Successfully imported 14 models
✅ Model User → table 'users'
✅ Model Branch → table 'branches'
...
🎉 ALL SCHEMA TESTS PASSED!
```

### Step 2: Set Up PostgreSQL (for testing)
You can use:
- **Local PostgreSQL**: Install PostgreSQL locally
- **Docker**: `docker run --name postgres-test -e POSTGRES_PASSWORD=test -p 5432:5432 -d postgres`
- **Render Database**: Create a test database on Render

### Step 3: Run Migration
```bash
# Run the migration script
python migrate_to_postgresql.py
```

### Step 4: Full Migration Testing
```bash
# Set database URL
export DATABASE_URL="postgresql://username:password@localhost:5432/restaurant_pos"

# Run comprehensive tests
python test_migration.py
```

**Expected Output**:
```
🔍 Restaurant POS Migration Test Suite
✅ Connected to SQLite: restaurant_pos.db
✅ Connected to PostgreSQL: postgresql://***
✅ Model User → table 'users' exists in both databases
✅ Table 'users' schema matches (8 columns)
✅ Table 'users' data migrated: 5 rows
...
🎉 ALL TESTS PASSED! Migration is ready for deployment!
```

## 🔧 Troubleshooting

### Common Issues

#### **Import Errors**
```
❌ Model import failed: No module named 'app'
```
**Solution**: Run from the project root directory

#### **Database Connection Failed**
```
❌ Database connection failed: could not connect to server
```
**Solutions**:
- Check DATABASE_URL format
- Ensure PostgreSQL is running
- Verify credentials and permissions

#### **Missing Tables**
```
❌ Model Order table 'orders' missing in PostgreSQL
```
**Solutions**:
- Run migration script: `python migrate_to_postgresql.py`
- Check for migration errors
- Verify database permissions

#### **Schema Mismatch**
```
❌ Table 'users' missing columns in PostgreSQL: {'last_login'}
```
**Solutions**:
- Re-run migration with latest models
- Check model definitions
- Update migration script if needed

#### **Data Count Mismatch**
```
❌ Table 'orders' row count mismatch: SQLite=100, PostgreSQL=95
```
**Solutions**:
- Check for migration errors
- Verify data integrity constraints
- Re-run migration with error handling

## 📊 Test Results Interpretation

### ✅ **All Tests Passed**
- Migration is complete and verified
- Ready for production deployment
- All data and schema migrated successfully

### ⚠️ **Warnings Only**
- Migration is mostly successful
- Minor issues that don't affect functionality
- Safe to deploy with monitoring

### ❌ **Failed Tests**
- Critical issues detected
- **DO NOT DEPLOY** until fixed
- Review and fix all failed tests

## 🎯 Pre-Deployment Checklist

Before deploying to Render:

- [ ] ✅ Quick schema test passes
- [ ] ✅ Full migration test passes
- [ ] ✅ All models imported successfully
- [ ] ✅ All tables exist in PostgreSQL
- [ ] ✅ Data counts match between databases
- [ ] ✅ Flask app starts with PostgreSQL
- [ ] ✅ No critical errors in test results
- [ ] ✅ PostgreSQL optimizations applied
- [ ] ✅ Environment variables configured

## 🔍 Manual Verification

### Check Database Tables
```sql
-- Connect to PostgreSQL
psql postgresql://username:password@host:port/database

-- List all tables
\dt

-- Check table structure
\d users
\d orders

-- Verify data
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM orders;
```

### Test Application Queries
```python
# Test in Python shell
from app import create_app, db
from app.models import User, Order

app = create_app('production')
with app.app_context():
    print(f"Users: {User.query.count()}")
    print(f"Orders: {Order.query.count()}")
    
    # Test a complex query
    recent_orders = Order.query.filter(
        Order.created_at >= datetime.utcnow() - timedelta(days=7)
    ).count()
    print(f"Recent orders: {recent_orders}")
```

## 🚀 Success Indicators

Your migration is successful when:

1. **Quick Schema Test**: All models load and are properly defined
2. **Migration Test**: All tables, data, and relationships migrated
3. **Application Test**: Flask app starts and queries work
4. **Performance Test**: Database responds quickly to queries
5. **No Critical Errors**: All tests pass or show only warnings

## 📞 Getting Help

If tests fail:

1. **Check the logs**: Review detailed error messages
2. **Verify prerequisites**: Ensure all dependencies are installed
3. **Test step-by-step**: Run each test individually
4. **Check database permissions**: Ensure proper access rights
5. **Review migration scripts**: Look for any custom modifications needed

---

## 🎉 Ready for Deployment!

Once all tests pass, your Restaurant POS system is ready for high-performance deployment on Render with PostgreSQL!

Follow the main deployment guide in `DEPLOYMENT_GUIDE.md` to complete your production deployment.
