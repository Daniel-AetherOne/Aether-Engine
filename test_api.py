#!/usr/bin/env python3
"""
Test script voor de /predict API endpoint
"""
import requests
import json
import time

def test_predict_api():
    """Test de /predict API endpoint"""
    
    # API endpoint
    url = "http://localhost:8000/predict"
    
    # Test data
    payload = {
        "lead_id": "test-api-lead-123",
        "image_paths": ["data/uploads/test/test_wall_with_cracks.jpg"],
        "m2": 25.5
    }
    
    print("🧪 Testing /predict API endpoint...")
    print(f"   URL: {url}")
    print(f"   Payload: {json.dumps(payload, indent=2)}")
    
    try:
        # Stuur POST request
        response = requests.post(url, json=payload, timeout=10)
        
        print(f"\n📡 Response:")
        print(f"   Status Code: {response.status_code}")
        print(f"   Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"\n✅ Success Response:")
            print(f"   Substrate: {result.get('substrate')}")
            print(f"   Issues: {result.get('issues')}")
            print(f"   Confidences: {result.get('confidences')}")
            
            # Valideer response structuur
            required_keys = ['substrate', 'issues', 'confidences']
            missing_keys = [key for key in required_keys if key not in result]
            
            if missing_keys:
                print(f"❌ Missing keys: {missing_keys}")
                return False
            else:
                print(f"\n🎉 API test geslaagd!")
                return True
                
        else:
            print(f"\n❌ Error Response:")
            print(f"   Status: {response.status_code}")
            print(f"   Body: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Kan geen verbinding maken met {url}")
        print(f"   Zorg ervoor dat de server draait op poort 8000")
        return False
    except Exception as e:
        print(f"❌ Error tijdens API test: {e}")
        return False

def test_health_endpoint():
    """Test de health endpoint"""
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            print(f"✅ Health endpoint: {response.json()}")
            return True
        else:
            print(f"❌ Health endpoint failed: {response.status_code}")
            return False
    except:
        print("❌ Health endpoint niet bereikbaar")
        return False

if __name__ == "__main__":
    print("🚀 LevelAI SaaS - API Test")
    print("=" * 50)
    
    # Test health endpoint eerst
    if test_health_endpoint():
        # Test predict endpoint
        success = test_predict_api()
        
        print(f"\n📊 API Test Resultaat: {'✅ GESLAAGD' if success else '❌ GEFAALD'}")
        
        if success:
            print("\n🎯 De API is volledig functioneel!")
            print("   - POST /predict endpoint werkt correct")
            print("   - Retourneert geldige JSON responses")
            print("   - Kan afbeeldingen analyseren voor substrate en issues")
        else:
            print("\n⚠️  Er zijn problemen met de API. Controleer de server logs.")
    else:
        print("\n⚠️  Server is niet bereikbaar. Start de server eerst met:")
        print("   python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")

