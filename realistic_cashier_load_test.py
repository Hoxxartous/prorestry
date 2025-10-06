#!/usr/bin/env python3
"""
Restaurant POS - Realistic Cashier Load Test
Simulates ALL cashiers from database creating orders simultaneously
Tests high load with actual user accounts and realistic order patterns
"""

import time
import threading
import statistics
import random
import json
import subprocess
import sys
import os
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Dict, Any
import queue

# Add the app directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

@dataclass
class OrderResult:
    cashier_id: int
    cashier_name: str
    order_id: int
    order_number: str
    response_time: float
    success: bool
    error: str = None
    timestamp: datetime = None

@dataclass
class CashierStats:
    cashier_id: int
    cashier_name: str
    total_orders: int
    successful_orders: int
    failed_orders: int
    avg_response_time: float
    total_amount: float

class RealisticCashierLoadTester:
    def __init__(self, workers_per_cashier=4, orders_per_cashier=50):
        self.workers_per_cashier = workers_per_cashier
        self.orders_per_cashier = orders_per_cashier
        self.results: List[OrderResult] = []
        self.server_process = None
        self.cashiers = []
        self.menu_items = []
        self.tables = []
        self.result_queue = queue.Queue()
        self.app = None  # Shared app instance
        self.db_lock = threading.Lock()  # Database access lock

    def start_server(self):
        """Start the waitress server"""
        print("🚀 Starting Restaurant POS server...")
        try:
            self.server_process = subprocess.Popen([
                sys.executable, "start_waitress_server.py", "--threads", "16"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            print("⏳ Waiting for server to initialize...")
            time.sleep(10)
            print("✅ Server started successfully!")
            return True
                
        except Exception as e:
            print(f"❌ Failed to start server: {e}")
            return False

    def stop_server(self):
        """Stop the server"""
        if self.server_process:
            print("🛑 Stopping server...")
            self.server_process.terminate()
            self.server_process.wait()
            print("✅ Server stopped")

    def load_test_data(self):
        """Load all cashiers, menu items, and tables from database"""
        try:
            from app import create_app, db
            from app.models import User, UserRole, MenuItem, Table
            from config import Config
            
            # Create shared app instance with minimal logging
            self.app = create_app(Config)
            self.app.config['LOG_TO_STDOUT'] = False  # Disable logging to prevent conflicts
            
            with self.app.app_context():
                # Load all cashiers
                cashiers = User.query.filter_by(role=UserRole.CASHIER, is_active=True).all()
                self.cashiers = [
                    {
                        'id': c.id,
                        'username': c.username,
                        'full_name': c.get_full_name(),
                        'branch_id': c.branch_id
                    }
                    for c in cashiers
                ]
                
                # Load menu items
                menu_items = MenuItem.query.filter_by(is_active=True).all()
                self.menu_items = [
                    {
                        'id': item.id,
                        'name': item.name,
                        'price': float(item.price),
                        'category_id': item.category_id
                    }
                    for item in menu_items
                ]
                
                # Load tables
                tables = Table.query.filter_by(is_active=True).all()
                self.tables = [
                    {
                        'id': table.id,
                        'table_number': table.table_number,
                        'branch_id': table.branch_id,
                        'capacity': table.capacity
                    }
                    for table in tables
                ]
                
                print(f"📊 Loaded {len(self.cashiers)} cashiers")
                print(f"🍽️  Loaded {len(self.menu_items)} menu items")
                print(f"🪑 Loaded {len(self.tables)} tables")
                
                return len(self.cashiers) > 0 and len(self.menu_items) > 0
                
        except Exception as e:
            print(f"❌ Failed to load test data: {e}")
            return False

    def create_realistic_order(self, cashier_data, order_sequence):
        """Create a realistic order for a specific cashier"""
        start_time = time.time()
        
        try:
            from app import db
            from app.models import Order, OrderItem, MenuItem, OrderStatus, ServiceType
            
            # Use shared app instance and database lock for thread safety
            with self.db_lock:
                with self.app.app_context():
                    # Generate realistic order
                    num_items = random.choices([1, 2, 3, 4, 5], weights=[10, 25, 35, 20, 10])[0]
                    selected_items = random.sample(self.menu_items, min(num_items, len(self.menu_items)))
                    
                    # Get cashier's branch tables
                    cashier_tables = [t for t in self.tables if t['branch_id'] == cashier_data['branch_id']]
                    selected_table = random.choice(cashier_tables) if cashier_tables else None
                    
                    # Generate order number
                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                    order_number = f"C{cashier_data['id']}-{timestamp}-{order_sequence:03d}"
                    
                    total_amount = 0
                    
                    # Create order
                    order = Order(
                        order_number=order_number,
                        total_amount=0,  # Will be calculated
                        cashier_id=cashier_data['id'],
                        branch_id=cashier_data['branch_id'],
                        table_id=selected_table['id'] if selected_table else None,
                        service_type=random.choice([ServiceType.ON_TABLE, ServiceType.TAKE_AWAY, ServiceType.DELIVERY]),
                        status=OrderStatus.PAID,  # Cashier orders are immediately paid
                        notes=f"Load test - Cashier: {cashier_data['full_name']} - Sequence: {order_sequence}",
                        paid_at=datetime.utcnow()
                    )
                    
                    # Add order items with realistic quantities and variations
                    for item_data in selected_items:
                        # Realistic quantity distribution
                        quantity = random.choices([1, 2, 3, 4], weights=[60, 25, 10, 5])[0]
                        
                        # Get actual menu item for current price
                        menu_item = MenuItem.query.get(item_data['id'])
                        if not menu_item:
                            continue
                        
                        item_total = menu_item.price * quantity
                        total_amount += item_total
                        
                        order_item = OrderItem(
                            menu_item_id=menu_item.id,
                            quantity=quantity,
                            unit_price=menu_item.price,
                            total_price=item_total,
                            notes=f"Cashier order - {random.choice(['Regular', 'Extra sauce', 'No onions', 'Hot', 'Mild'])}"
                        )
                        order.order_items.append(order_item)
                    
                    order.total_amount = total_amount
                    
                    # Save to database
                    db.session.add(order)
                    db.session.commit()
                    
                    response_time = time.time() - start_time
                    
                    return OrderResult(
                        cashier_id=cashier_data['id'],
                        cashier_name=cashier_data['full_name'],
                        order_id=order.id,
                        order_number=order_number,
                        response_time=response_time,
                        success=True,
                        timestamp=datetime.now()
                    )
                
        except Exception as e:
            response_time = time.time() - start_time
            return OrderResult(
                cashier_id=cashier_data['id'],
                cashier_name=cashier_data['full_name'],
                order_id=0,
                order_number="FAILED",
                response_time=response_time,
                success=False,
                error=str(e),
                timestamp=datetime.now()
            )

    def cashier_worker_thread(self, cashier_data, worker_id, orders_to_create):
        """Worker thread for a specific cashier"""
        results = []
        cashier_name = cashier_data['full_name']
        
        print(f"👤 Cashier {cashier_name} (Worker {worker_id}) started - {orders_to_create} orders")
        
        for sequence in range(orders_to_create):
            result = self.create_realistic_order(cashier_data, sequence + 1)
            results.append(result)
            
            if result.success:
                print(f"✅ {cashier_name} - Order {result.order_number}: {result.response_time:.3f}s")
            else:
                print(f"❌ {cashier_name} - Order failed: {result.error}")
            
            # Realistic delay between orders (cashiers don't create orders instantly)
            time.sleep(random.uniform(0.5, 2.0))
        
        return results

    def run_realistic_load_test(self):
        """Run comprehensive load test with all cashiers"""
        if not self.load_test_data():
            print("❌ Failed to load test data")
            return
        
        total_orders = len(self.cashiers) * self.orders_per_cashier
        total_workers = len(self.cashiers) * self.workers_per_cashier
        
        print("=" * 80)
        print("🧪 REALISTIC CASHIER LOAD TEST")
        print("=" * 80)
        print(f"👥 Active Cashiers: {len(self.cashiers)}")
        print(f"🔧 Workers per Cashier: {self.workers_per_cashier}")
        print(f"📊 Orders per Cashier: {self.orders_per_cashier}")
        print(f"🎯 Total Orders: {total_orders}")
        print(f"⚡ Total Workers: {total_workers}")
        print(f"🍽️  Menu Items Available: {len(self.menu_items)}")
        print(f"🪑 Tables Available: {len(self.tables)}")
        print("=" * 80)
        
        # Show cashier details
        print("\n📋 CASHIERS PARTICIPATING:")
        for i, cashier in enumerate(self.cashiers, 1):
            print(f"   {i}. {cashier['full_name']} (ID: {cashier['id']}, Branch: {cashier['branch_id']})")
        
        print(f"\n🚀 Starting {total_workers} workers across {len(self.cashiers)} cashiers...")
        print("=" * 80)
        
        start_time = time.time()
        
        # Create worker tasks for each cashier
        with ThreadPoolExecutor(max_workers=total_workers) as executor:
            futures = []
            
            for cashier in self.cashiers:
                # Create multiple workers per cashier for high concurrency
                for worker_id in range(self.workers_per_cashier):
                    future = executor.submit(
                        self.cashier_worker_thread,
                        cashier,
                        worker_id + 1,
                        self.orders_per_cashier // self.workers_per_cashier
                    )
                    futures.append(future)
            
            # Collect results
            for future in as_completed(futures):
                worker_results = future.result()
                self.results.extend(worker_results)
        
        total_duration = time.time() - start_time
        self.analyze_results(total_duration)

    def analyze_results(self, total_duration):
        """Comprehensive analysis of test results"""
        successful = [r for r in self.results if r.success]
        failed = [r for r in self.results if not r.success]
        
        print("\n" + "=" * 80)
        print("📊 COMPREHENSIVE LOAD TEST RESULTS")
        print("=" * 80)
        
        # Overall statistics
        print(f"🎯 Total Orders Attempted: {len(self.results)}")
        print(f"✅ Successful Orders: {len(successful)} ({len(successful)/len(self.results)*100:.1f}%)")
        print(f"❌ Failed Orders: {len(failed)} ({len(failed)/len(self.results)*100:.1f}%)")
        print(f"⏱️  Total Test Duration: {total_duration:.2f} seconds")
        print(f"🚀 Overall Throughput: {len(successful)/total_duration:.2f} orders/second")
        
        if successful:
            response_times = [r.response_time for r in successful]
            total_revenue = sum(float(r.order_number.split('-')[0]) if r.order_number != "FAILED" else 0 for r in successful)
            
            print(f"\n📈 RESPONSE TIME ANALYSIS:")
            print(f"   Average: {statistics.mean(response_times):.3f}s")
            print(f"   Median: {statistics.median(response_times):.3f}s")
            print(f"   Min: {min(response_times):.3f}s")
            print(f"   Max: {max(response_times):.3f}s")
            
            # Calculate percentiles
            sorted_times = sorted(response_times)
            p95_index = int(0.95 * len(sorted_times))
            p99_index = int(0.99 * len(sorted_times))
            
            print(f"   95th Percentile: {sorted_times[p95_index]:.3f}s")
            print(f"   99th Percentile: {sorted_times[p99_index]:.3f}s")
            
            # Performance rating
            avg_time = statistics.mean(response_times)
            if avg_time < 0.1:
                rating = "🟢 EXCELLENT"
            elif avg_time < 0.5:
                rating = "🟡 GOOD"
            elif avg_time < 1.0:
                rating = "🟠 FAIR"
            else:
                rating = "🔴 POOR"
            
            print(f"\n🏆 Overall Performance Rating: {rating}")
        
        # Per-cashier analysis
        self.analyze_per_cashier_performance()
        
        # Error analysis
        if failed:
            self.analyze_errors(failed)
        
        # System load analysis
        self.analyze_system_load(total_duration)
        
        # Save comprehensive report
        self.save_comprehensive_report(total_duration)

    def analyze_per_cashier_performance(self):
        """Analyze performance per cashier"""
        print(f"\n👥 PER-CASHIER PERFORMANCE ANALYSIS:")
        print("-" * 80)
        
        cashier_stats = {}
        
        for result in self.results:
            cashier_id = result.cashier_id
            if cashier_id not in cashier_stats:
                cashier_stats[cashier_id] = {
                    'name': result.cashier_name,
                    'total': 0,
                    'successful': 0,
                    'failed': 0,
                    'response_times': [],
                    'total_amount': 0
                }
            
            stats = cashier_stats[cashier_id]
            stats['total'] += 1
            
            if result.success:
                stats['successful'] += 1
                stats['response_times'].append(result.response_time)
            else:
                stats['failed'] += 1
        
        # Print cashier performance
        for cashier_id, stats in cashier_stats.items():
            success_rate = (stats['successful'] / stats['total'] * 100) if stats['total'] > 0 else 0
            avg_response = statistics.mean(stats['response_times']) if stats['response_times'] else 0
            
            print(f"   {stats['name']:<25} | Orders: {stats['successful']:3d}/{stats['total']:3d} | "
                  f"Success: {success_rate:5.1f}% | Avg Time: {avg_response:.3f}s")

    def analyze_errors(self, failed_results):
        """Analyze error patterns"""
        print(f"\n❌ ERROR ANALYSIS:")
        print("-" * 50)
        
        error_counts = {}
        cashier_errors = {}
        
        for result in failed_results:
            error = result.error or "Unknown error"
            error_counts[error] = error_counts.get(error, 0) + 1
            
            cashier = result.cashier_name
            if cashier not in cashier_errors:
                cashier_errors[cashier] = 0
            cashier_errors[cashier] += 1
        
        print("Error Types:")
        for error, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"   • {error}: {count} occurrences")
        
        if cashier_errors:
            print("\nErrors by Cashier:")
            for cashier, count in sorted(cashier_errors.items(), key=lambda x: x[1], reverse=True):
                print(f"   • {cashier}: {count} errors")

    def analyze_system_load(self, total_duration):
        """Analyze system load characteristics"""
        print(f"\n⚡ SYSTEM LOAD ANALYSIS:")
        print("-" * 50)
        
        # Calculate concurrent load over time
        if self.results:
            # Group results by time windows
            time_windows = {}
            start_time = min(r.timestamp for r in self.results if r.timestamp)
            
            for result in self.results:
                if result.timestamp:
                    window = int((result.timestamp - start_time).total_seconds() // 10) * 10  # 10-second windows
                    if window not in time_windows:
                        time_windows[window] = 0
                    time_windows[window] += 1
            
            if time_windows:
                peak_load = max(time_windows.values())
                avg_load = sum(time_windows.values()) / len(time_windows)
                
                print(f"   Peak Load: {peak_load} orders per 10-second window")
                print(f"   Average Load: {avg_load:.1f} orders per 10-second window")
                print(f"   Load Distribution: {len(time_windows)} time windows")
        
        # Database performance indicators
        successful_orders = len([r for r in self.results if r.success])
        print(f"   Database Writes: {successful_orders} successful transactions")
        print(f"   Write Rate: {successful_orders/total_duration:.2f} transactions/second")

    def save_comprehensive_report(self, total_duration):
        """Save detailed report to JSON file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"realistic_cashier_load_test_{timestamp}.json"
        
        successful = [r for r in self.results if r.success]
        response_times = [r.response_time for r in successful] if successful else []
        
        # Prepare cashier statistics
        cashier_stats = {}
        for result in self.results:
            cashier_id = result.cashier_id
            if cashier_id not in cashier_stats:
                cashier_stats[cashier_id] = {
                    'name': result.cashier_name,
                    'total_orders': 0,
                    'successful_orders': 0,
                    'failed_orders': 0,
                    'response_times': []
                }
            
            stats = cashier_stats[cashier_id]
            stats['total_orders'] += 1
            
            if result.success:
                stats['successful_orders'] += 1
                stats['response_times'].append(result.response_time)
            else:
                stats['failed_orders'] += 1
        
        # Calculate per-cashier averages
        for cashier_id, stats in cashier_stats.items():
            if stats['response_times']:
                stats['avg_response_time'] = statistics.mean(stats['response_times'])
            else:
                stats['avg_response_time'] = 0
            del stats['response_times']  # Remove raw data for cleaner JSON
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "test_type": "realistic_cashier_load_test",
            "configuration": {
                "total_cashiers": len(self.cashiers),
                "workers_per_cashier": self.workers_per_cashier,
                "orders_per_cashier": self.orders_per_cashier,
                "total_orders": len(self.results),
                "total_workers": len(self.cashiers) * self.workers_per_cashier,
                "menu_items_available": len(self.menu_items),
                "tables_available": len(self.tables)
            },
            "summary": {
                "successful_orders": len(successful),
                "failed_orders": len(self.results) - len(successful),
                "success_rate": len(successful) / len(self.results) * 100 if self.results else 0,
                "total_duration": total_duration,
                "orders_per_second": len(successful) / total_duration if total_duration > 0 else 0
            },
            "response_times": {
                "average": statistics.mean(response_times) if response_times else 0,
                "median": statistics.median(response_times) if response_times else 0,
                "min": min(response_times) if response_times else 0,
                "max": max(response_times) if response_times else 0,
                "p95": sorted(response_times)[int(0.95 * len(response_times))] if response_times else 0,
                "p99": sorted(response_times)[int(0.99 * len(response_times))] if response_times else 0
            },
            "cashier_performance": cashier_stats,
            "participating_cashiers": self.cashiers,
            "detailed_results": [
                {
                    "cashier_id": r.cashier_id,
                    "cashier_name": r.cashier_name,
                    "order_id": r.order_id,
                    "order_number": r.order_number,
                    "response_time": r.response_time,
                    "success": r.success,
                    "error": r.error,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None
                }
                for r in self.results
            ]
        }
        
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n📄 Comprehensive report saved to: {filename}")
        print("=" * 80)

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Realistic Cashier Load Test for Restaurant POS")
    parser.add_argument("--workers-per-cashier", type=int, default=4, help="Workers per cashier (default: 4)")
    parser.add_argument("--orders-per-cashier", type=int, default=50, help="Orders per cashier (default: 50)")
    parser.add_argument("--no-server", action="store_true", help="Don't start server")
    
    args = parser.parse_args()
    
    tester = RealisticCashierLoadTester(
        workers_per_cashier=args.workers_per_cashier,
        orders_per_cashier=args.orders_per_cashier
    )
    
    # Start server
    if not args.no_server:
        if not tester.start_server():
            print("❌ Failed to start server")
            return
    
    try:
        # Run comprehensive test
        tester.run_realistic_load_test()
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"❌ Test failed: {e}")
    finally:
        if not args.no_server:
            tester.stop_server()

if __name__ == "__main__":
    main()
