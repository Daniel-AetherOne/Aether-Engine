#!/usr/bin/env python3
"""
Test script voor Celery implementatie
"""
import requests
import time
import json
from pathlib import Path

# API base URL
BASE_URL = "http://localhost:8000"

def test_quote_create():
    """Test quote create endpoint"""
    print("Testing quote create endpoint...")
    
    # Test data
    test_data = {
        "lead_id": f"test_lead_{int(time.time())}",
        "image_paths": ["/tmp/test_image.jpg"],
        "m2": 45.5,
        "contactgegevens": {
            "name": "Test Klant",
            "email": "test@example.com",
            "phone": "+31 6 12345678",
            "address": "Teststraat 123, 1234 AB Amsterdam"
        }
    }
    
    # Maak request
    response = requests.post(
        f"{BASE_URL}/quote/create",
        json=test_data,
        headers={"X-Tenant-ID": "demo"}
    )
    
    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.json()}")
    
    if response.status_code == 201:
        status_id = response.json()["status_id"]
        print(f"Quote creation started with status_id: {status_id}")
        return status_id
    else:
        print("Quote creation failed")
        return None

def test_job_status(status_id):
    """Test job status endpoint"""
    print(f"\nTesting job status for {status_id}...")
    
    # Poll job status
    max_attempts = 30
    attempt = 0
    
    while attempt < max_attempts:
        response = requests.get(
            f"{BASE_URL}/jobs/{status_id}",
            headers={"X-Tenant-ID": "demo"}
        )
        
        if response.status_code == 200:
            job_info = response.json()
            print(f"Job status: {job_info['status']}")
            print(f"Current step: {job_info.get('step', 'N/A')}")
            
            if job_info['status'] == 'completed':
                print("Job completed successfully!")
                if job_info.get('public_url'):
                    print(f"Public URL: {job_info['public_url']}")
                break
            elif job_info['status'] == 'failed':
                print(f"Job failed: {job_info.get('error', 'Unknown error')}")
                break
        else:
            print(f"Failed to get job status: {response.status_code}")
            break
        
        attempt += 1
        time.sleep(2)  # Wacht 2 seconden tussen polls
    
    if attempt >= max_attempts:
        print("Timeout waiting for job completion")

def test_concurrent_requests():
    """Test 5 gelijktijdige aanvragen"""
    print("\nTesting 5 concurrent requests...")
    
    import threading
    import time
    
    results = []
    
    def make_request(request_num):
        start_time = time.time()
        
        test_data = {
            "lead_id": f"concurrent_lead_{request_num}_{int(time.time())}",
            "image_paths": ["/tmp/test_image.jpg"],
            "m2": 45.5,
            "contactgegevens": {
                "name": f"Concurrent Klant {request_num}",
                "email": f"concurrent{request_num}@example.com",
                "phone": "+31 6 12345678",
                "address": f"Concurrentstraat {request_num}, 1234 AB Amsterdam"
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/quote/create",
            json=test_data,
            headers={"X-Tenant-ID": "demo"}
        )
        
        end_time = time.time()
        response_time = (end_time - start_time) * 1000  # Convert to milliseconds
        
        results.append({
            "request_num": request_num,
            "status_code": response.status_code,
            "response_time_ms": response_time,
            "status_id": response.json().get("status_id") if response.status_code == 201 else None
        })
        
        print(f"Request {request_num}: {response.status_code} in {response_time:.2f}ms")
    
    # Start 5 gelijktijdige threads
    threads = []
    for i in range(5):
        thread = threading.Thread(target=make_request, args=(i+1,))
        threads.append(thread)
        thread.start()
    
    # Wacht tot alle threads klaar zijn
    for thread in threads:
        thread.join()
    
    # Analyseer resultaten
    print("\nConcurrent request results:")
    successful_requests = [r for r in results if r["status_code"] == 201]
    avg_response_time = sum(r["response_time_ms"] for r in successful_requests) / len(successful_requests) if successful_requests else 0
    
    print(f"Successful requests: {len(successful_requests)}/5")
    print(f"Average response time: {avg_response_time:.2f}ms")
    
    # Check of alle response times onder 200ms zijn
    slow_requests = [r for r in successful_requests if r["response_time_ms"] > 200]
    if slow_requests:
        print(f"Warning: {len(slow_requests)} requests were slower than 200ms")
    else:
        print("✓ All requests were faster than 200ms")

def main():
    """Main test function"""
    print("LevelAI SaaS - Celery Implementation Test")
    print("=" * 50)
    
    # Test 1: Enkele quote create
    status_id = test_quote_create()
    
    if status_id:
        # Test 2: Job status polling
        test_job_status(status_id)
    
    # Test 3: Gelijktijdige aanvragen
    test_concurrent_requests()
    
    print("\nTest completed!")

if __name__ == "__main__":
    main()
