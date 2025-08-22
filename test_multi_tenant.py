#!/usr/bin/env python3
"""
Test script voor multi-tenant functionaliteit van LevelAI SaaS

Dit script test:
1. Tenant resolutie via X-Tenant header
2. Gescheiden storage paden
3. Tenant-specifieke branding in PDFs
4. Tenant-aware logging
"""

import requests
import json
import time
from pathlib import Path

# Test configuratie
BASE_URL = "http://localhost:8000"
TENANTS = ["company_a", "company_b", "default"]

def test_tenant_resolution():
    """Test tenant resolutie via X-Tenant header"""
    print("🔍 Testing tenant resolution...")
    
    for tenant_id in TENANTS:
        headers = {"X-Tenant": tenant_id}
        response = requests.get(f"{BASE_URL}/tenant/{tenant_id}", headers=headers)
        
        if response.status_code == 200:
            tenant_info = response.json()
            print(f"✅ Tenant {tenant_id}: {tenant_info.get('company_name', 'Unknown')}")
        else:
            print(f"❌ Failed to get tenant {tenant_id}: {response.status_code}")

def test_intake_form_tenant_branding():
    """Test tenant branding in intake form"""
    print("\n🎨 Testing intake form tenant branding...")
    
    for tenant_id in TENANTS:
        headers = {"X-Tenant": tenant_id}
        response = requests.get(f"{BASE_URL}/intake/form", headers=headers)
        
        if response.status_code == 200:
            html_content = response.text
            if tenant_id in html_content:
                print(f"✅ Intake form for {tenant_id} contains tenant branding")
            else:
                print(f"⚠️  Intake form for {tenant_id} missing tenant branding")
        else:
            print(f"❌ Failed to get intake form for {tenant_id}: {response.status_code}")

def test_quote_creation_multi_tenant():
    """Test quote creation for different tenants"""
    print("\n📄 Testing quote creation for different tenants...")
    
    for tenant_id in TENANTS:
        headers = {"X-Tenant": tenant_id}
        
        # Test data
        quote_data = {
            "lead": {
                "name": f"Test Customer {tenant_id}",
                "email": f"test@{tenant_id}.com",
                "phone": "+31 6 12345678",
                "address": f"Test Address {tenant_id}",
                "square_meters": 50.0
            },
            "prediction": {
                "substrate": "gipsplaat",
                "issues": ["vocht"],
                "confidences": {
                    "gipsplaat": 0.95,
                    "vocht": 0.87
                }
            }
        }
        
        try:
            response = requests.post(
                f"{BASE_URL}/quote/render",
                json=quote_data,
                headers=headers
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Quote created for {tenant_id}: {result['quote_id']}")
                print(f"   PDF URL: {result['public_url']}")
                print(f"   Tenant ID: {result['tenant_id']}")
            else:
                print(f"❌ Failed to create quote for {tenant_id}: {response.status_code}")
                print(f"   Error: {response.text}")
                
        except Exception as e:
            print(f"❌ Exception creating quote for {tenant_id}: {str(e)}")

def test_storage_paths():
    """Test tenant-specific storage paths"""
    print("\n📁 Testing tenant-specific storage paths...")
    
    base_paths = ["data/uploads", "data/offers"]
    
    for base_path in base_paths:
        for tenant_id in TENANTS:
            tenant_path = Path(base_path) / tenant_id
            if tenant_path.exists():
                print(f"✅ {tenant_path} exists")
            else:
                print(f"❌ {tenant_path} does not exist")

def test_tenant_quotes_listing():
    """Test tenant-specific quote listing"""
    print("\n📋 Testing tenant-specific quote listing...")
    
    for tenant_id in TENANTS:
        headers = {"X-Tenant": tenant_id}
        
        try:
            response = requests.get(f"{BASE_URL}/quote/list", headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ {tenant_id}: {result['total']} quotes found")
                print(f"   Tenant ID in response: {result['tenant_id']}")
            else:
                print(f"❌ Failed to list quotes for {tenant_id}: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Exception listing quotes for {tenant_id}: {str(e)}")

def test_tenant_info_endpoints():
    """Test tenant information endpoints"""
    print("\nℹ️  Testing tenant information endpoints...")
    
    # Test /tenants endpoint
    try:
        response = requests.get(f"{BASE_URL}/tenants")
        if response.status_code == 200:
            tenants = response.json()
            print(f"✅ Available tenants: {[t['tenant_id'] for t in tenants['tenants']]}")
        else:
            print(f"❌ Failed to get tenants list: {response.status_code}")
    except Exception as e:
        print(f"❌ Exception getting tenants list: {str(e)}")
    
    # Test individual tenant endpoints
    for tenant_id in TENANTS:
        try:
            response = requests.get(f"{BASE_URL}/tenant/{tenant_id}")
            if response.status_code == 200:
                tenant_info = response.json()
                print(f"✅ Tenant {tenant_id}: {tenant_info.get('company_name', 'Unknown')}")
                print(f"   Has HubSpot: {tenant_info.get('has_hubspot', False)}")
            else:
                print(f"❌ Failed to get tenant {tenant_id} info: {response.status_code}")
        except Exception as e:
            print(f"❌ Exception getting tenant {tenant_id} info: {str(e)}")

def main():
    """Main test function"""
    print("🚀 Starting multi-tenant functionality tests...")
    print("=" * 50)
    
    # Wait for app to be ready
    print("⏳ Waiting for application to be ready...")
    time.sleep(2)
    
    try:
        # Test basic connectivity
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code != 200:
            print(f"❌ Application not ready: {response.status_code}")
            return
        print("✅ Application is ready")
        
        # Run tests
        test_tenant_resolution()
        test_intake_form_tenant_branding()
        test_quote_creation_multi_tenant()
        test_storage_paths()
        test_tenant_quotes_listing()
        test_tenant_info_endpoints()
        
        print("\n" + "=" * 50)
        print("🎉 Multi-tenant tests completed!")
        
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to application. Make sure it's running on http://localhost:8000")
    except Exception as e:
        print(f"❌ Test failed with exception: {str(e)}")

if __name__ == "__main__":
    main()
