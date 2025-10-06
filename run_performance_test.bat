@echo off
echo ================================================================
echo RESTAURANT POS PERFORMANCE TESTING SUITE
echo ================================================================
echo.
echo Select a test to run:
echo 1. Realistic Cashier Load Test (ALL cashiers, 4 workers each) - RECOMMENDED
echo 2. Quick Cashier Test (ALL cashiers, 2 workers each)
echo 3. Stress Cashier Test (ALL cashiers, 8 workers each)
echo 4. Database Load Test (1000 orders, 20 workers)
echo 5. Custom Cashier Test
echo 6. Exit
echo.
set /p choice=Enter your choice (1-6): 

if "%choice%"=="1" goto realistic_test
if "%choice%"=="2" goto quick_cashier_test
if "%choice%"=="3" goto stress_cashier_test
if "%choice%"=="4" goto database_test
if "%choice%"=="5" goto custom_cashier_test
if "%choice%"=="6" goto exit
goto invalid

:realistic_test
echo.
echo ================================================================
echo Running Realistic Cashier Load Test
echo This test uses ALL cashiers from your database simultaneously
echo Each cashier gets 4 workers creating 50 orders each
echo ================================================================
python realistic_cashier_load_test.py --workers-per-cashier 4 --orders-per-cashier 50
goto end

:quick_cashier_test
echo.
echo ================================================================
echo Running Quick Cashier Test
echo ALL cashiers with 2 workers each, 25 orders per cashier
echo ================================================================
python realistic_cashier_load_test.py --workers-per-cashier 2 --orders-per-cashier 25
goto end

:stress_cashier_test
echo.
echo ================================================================
echo Running Stress Cashier Test
echo WARNING: This is a heavy load test!
echo ALL cashiers with 8 workers each, 100 orders per cashier
echo ================================================================
python realistic_cashier_load_test.py --workers-per-cashier 8 --orders-per-cashier 100
goto end

:database_test
echo.
echo ================================================================
echo Running Database Load Test (1000 orders, 20 workers)
echo This test directly inserts orders into the database for maximum performance
echo ================================================================
python working_load_test.py --orders 1000 --workers 20
goto end

:custom_cashier_test
echo.
set /p workers_per_cashier=Enter workers per cashier (default 4): 
set /p orders_per_cashier=Enter orders per cashier (default 50): 
if "%workers_per_cashier%"=="" set workers_per_cashier=4
if "%orders_per_cashier%"=="" set orders_per_cashier=50
echo.
echo ================================================================
echo Running Custom Cashier Test
echo Workers per cashier: %workers_per_cashier%
echo Orders per cashier: %orders_per_cashier%
echo ================================================================
python realistic_cashier_load_test.py --workers-per-cashier %workers_per_cashier% --orders-per-cashier %orders_per_cashier%
goto end

:invalid
echo Invalid choice. Please try again.
pause
cls
goto start

:end
echo.
echo ================================================================
echo Test completed! Check the generated JSON report for detailed results.
echo ================================================================
pause

:exit
echo Goodbye!
