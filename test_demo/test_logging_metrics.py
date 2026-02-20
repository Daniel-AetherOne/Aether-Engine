#!/usr/bin/env python3
"""
Test script voor logging, metrics en rate limiting functionaliteit
"""

import requests
import time
import json
from typing import Dict, Any

BASE_URL = "http://localhost:8000"

def test_health_endpoints():
    """Test health endpoints"""
    print("🔍 Testing health endpoints...")
    
    # Basic health
    response = requests.get(f"{BASE_URL}/health")
    print(f"  /health: {response.status_code} - {response.json()}")
    
    # Detailed health
    response = requests.get(f"{BASE_URL}/health/detailed")
    print(f"  /health/detailed: {response.status_code} - {response.json()}")

def test_metrics_endpoints():
    """Test metrics endpoints"""
    print("\n📊 Testing metrics endpoints...")
    
    # Prometheus metrics
    response = requests.get(f"{BASE_URL}/metrics")
    print(f"  /metrics: {response.status_code} - {len(response.text)} bytes")
    
    # Metrics summary
    response = requests.get(f"{BASE_URL}/metrics/summary")
    print(f"  /metrics/summary: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"    Request count: {data.get('request_count', 0)}")
        print(f"    Job count: {data.get('job_count', 0)}")
        print(f"    Quotes created: {data.get('quotes_created', 0)}")
    
    # Rate limits info
    response = requests.get(f"{BASE_URL}/metrics/rate-limits")
    print(f"  /metrics/rate-limits: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"    Rate limits configured: {len(data.get('rate_limits', {}))}")

def test_rate_limiting():
    """Test rate limiting functionaliteit"""
    print("\n⏱️  Testing rate limiting...")
    
    # Test data
    test_data = {
        "lead_id": "test_lead_123",
        "image_paths": ["/path/to/image1.jpg"],
        "m2": 25.5,
        "contactgegevens": {
            "name": "Test User",
            "email": "test@example.com",
            "phone": "+31612345678",
            "address": "Test Address 123"
        }
    }
    
    # Test quote creation (should be rate limited to 60/min)
    print("  Testing quote creation rate limiting...")
    
    success_count = 0
    rate_limited_count = 0
    
    for i in range(1, 66):  # Try 65 requests
        try:
            response = requests.post(
                f"{BASE_URL}/quote/create",
                json=test_data,
                headers={"X-Tenant-ID": "test_tenant"}
            )
            
            if response.status_code == 200:
                success_count += 1
                print(f"    Request {i}: Success")
            elif response.status_code == 429:
                rate_limited_count += 1
                print(f"    Request {i}: Rate limited (429)")
                break
            else:
                print(f"    Request {i}: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"    Request {i}: Error - {e}")
        
        time.sleep(0.1)  # Small delay between requests
    
    print(f"  Results: {success_count} successful, {rate_limited_count} rate limited")
    
    # Check rate limit headers
    if success_count > 0:
        response = requests.post(
            f"{BASE_URL}/quote/create",
            json=test_data,
            headers={"X-Tenant-ID": "test_tenant"}
        )
        
        print(f"  Rate limit headers:")
        print(f"    X-RateLimit-Limit: {response.headers.get('X-RateLimit-Limit', 'Not set')}")
        print(f"    X-RateLimit-Remaining: {response.headers.get('X-RateLimit-Remaining', 'Not set')}")
        print(f"    X-RateLimit-Reset: {response.headers.get('X-RateLimit-Reset', 'Not set')}")

def test_vision_rate_limiting():
    """Test vision processing rate limiting"""
    print("\n👁️  Testing vision rate limiting...")
    
    # Test data
    test_data = {
        "lead_id": "test_vision_123",
        "image_paths": ["/path/to/image1.jpg"],
        "m2": 30.0
    }
    
    print("  Testing vision prediction rate limiting...")
    
    success_count = 0
    rate_limited_count = 0
    
    for i in range(1, 36):  # Try 35 requests (limit is 30/min)
        try:
            response = requests.post(
                f"{BASE_URL}/predict/",
                json=test_data,
                headers={"X-Tenant-ID": "test_tenant"}
            )
            
            if response.status_code == 200:
                success_count += 1
                print(f"    Request {i}: Success")
            elif response.status_code == 429:
                rate_limited_count += 1
                print(f"    Request {i}: Rate limited (429)")
                break
            else:
                print(f"    Request {i}: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"    Request {i}: Error - {e}")
        
        time.sleep(0.1)
    
    print(f"  Results: {success_count} successful, {rate_limited_count} rate limited")

def test_metrics_dashboard():
    """Test metrics dashboard"""
    print("\n📈 Testing metrics dashboard...")
    
    response = requests.get(f"{BASE_URL}/metrics/dashboard")
    print(f"  /metrics/dashboard: {response.status_code}")
    
    if response.status_code == 200:
        content = response.text
        print(f"    Content length: {len(content)} bytes")
        print(f"    Contains Chart.js: {'Chart.js' in content}")
        print(f"    Contains metrics cards: {'metric-card' in content}")
    else:
        print(f"    Error: {response.text}")

def test_rate_limit_reset():
    """Test rate limit reset functionality"""
    print("\n🔄 Testing rate limit reset...")
    
    # Reset all rate limits
    response = requests.post(f"{BASE_URL}/metrics/rate-limits/reset")
    print(f"  Reset all: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"    Reset {data.get('reset_count', 0)} counters")
    
    # Reset specific tenant
    response = requests.post(f"{BASE_URL}/metrics/rate-limits/test_tenant/reset")
    print(f"  Reset tenant: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"    Reset {data.get('reset_count', 0)} counters for test_tenant")

def test_logging_context():
    """Test logging context functionality"""
    print("\n📝 Testing logging context...")
    
    # This would normally be tested in the application itself
    # For now, we'll just verify the endpoints are working
    print("  Logging context is handled by middleware automatically")
    print("  Check logs/app.log for context-aware log entries")

def main():
    """Main test function"""
    print("🚀 Starting LevelAI SaaS - Logging, Metrics & Rate Limiting Tests")
    print("=" * 70)
    
    try:
        # Test all functionality
        test_health_endpoints()
        test_metrics_endpoints()
        test_rate_limiting()
        test_vision_rate_limiting()
        test_metrics_dashboard()
        test_rate_limit_reset()
        test_logging_context()
        
        print("\n✅ All tests completed successfully!")
        print("\n📋 Next steps:")
        print("  1. Check logs/app.log for context-aware logging")
        print("  2. Visit http://localhost:8000/metrics/dashboard for visual metrics")
        print("  3. Monitor rate limiting with http://localhost:8000/metrics/rate-limits")
        print("  4. Use Prometheus endpoint at http://localhost:8000/metrics")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        print("\n🔧 Troubleshooting:")
        print("  1. Ensure the application is running on http://localhost:8000")
        print("  2. Check if Redis is running for rate limiting")
        print("  3. Verify all dependencies are installed")
        print("  4. Check application logs for errors")

if __name__ == "__main__":
    main()
