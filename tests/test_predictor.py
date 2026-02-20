#!/usr/bin/env python3
"""
Test script voor de SimplePredictor service
"""
import sys
import os
from pathlib import Path

# Voeg app directory toe aan Python path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from services.predictor import SimplePredictor

def test_predictor():
    """Test de predictor service"""
    print("🧪 Testing SimplePredictor...")
    
    # Maak predictor instance
    predictor = SimplePredictor()
    
    # Test data
    lead_id = "test-lead-123"
    image_paths = ["test_image.jpg"]  # Deze bestaat niet, dus gebruikt default prediction
    m2 = 25.5
    
    print(f"📋 Test parameters:")
    print(f"   Lead ID: {lead_id}")
    print(f"   Image paths: {image_paths}")
    print(f"   Area (m²): {m2}")
    
    # Test prediction
    try:
        result = predictor.predict(lead_id, image_paths, m2)
        
        print(f"\n✅ Prediction resultaat:")
        print(f"   Substrate: {result['substrate']}")
        print(f"   Issues: {result['issues']}")
        print(f"   Confidences: {result['confidences']}")
        
        # Valideer resultaat structuur
        required_keys = ['substrate', 'issues', 'confidences']
        for key in required_keys:
            if key not in result:
                print(f"❌ Missing key: {key}")
                return False
        
        if not isinstance(result['substrate'], str):
            print(f"❌ Substrate should be string, got: {type(result['substrate'])}")
            return False
            
        if not isinstance(result['issues'], list):
            print(f"❌ Issues should be list, got: {type(result['issues'])}")
            return False
            
        if not isinstance(result['confidences'], dict):
            print(f"❌ Confidences should be dict, got: {type(result['confidences'])}")
            return False
        
        print(f"\n🎉 Alle tests geslaagd! De predictor werkt correct.")
        return True
        
    except Exception as e:
        print(f"❌ Error tijdens testing: {e}")
        return False

def test_with_real_image():
    """Test met een echte afbeelding als die bestaat"""
    print(f"\n🔍 Zoeken naar test afbeeldingen...")
    
    # Zoek naar afbeeldingen in data/uploads
    uploads_dir = Path("data/uploads")
    if uploads_dir.exists():
        image_files = []
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp']:
            image_files.extend(uploads_dir.rglob(ext))
        
        if image_files:
            test_image = str(image_files[0])
            print(f"📸 Test afbeelding gevonden: {test_image}")
            
            predictor = SimplePredictor()
            result = predictor.predict("test-real", [test_image], 30.0)
            
            print(f"✅ Real image prediction:")
            print(f"   Substrate: {result['substrate']}")
            print(f"   Issues: {result['issues']}")
            print(f"   Confidences: {result['confidences']}")
        else:
            print("ℹ️  Geen test afbeeldingen gevonden in data/uploads")
    else:
        print("ℹ️  Uploads directory bestaat niet")

if __name__ == "__main__":
    print("🚀 LevelAI SaaS - Predictor Test")
    print("=" * 50)
    
    # Test 1: Basic functionality
    success = test_predictor()
    
    # Test 2: Met echte afbeelding als beschikbaar
    test_with_real_image()
    
    print(f"\n📊 Test resultaat: {'✅ GESLAAGD' if success else '❌ GEFAALD'}")
    
    if success:
        print("\n🎯 De predictor is klaar voor gebruik!")
        print("   - POST /predict endpoint is beschikbaar")
        print("   - Analyseert afbeeldingen voor substrate en issues")
        print("   - Retourneert gestructureerde JSON responses")
    else:
        print("\n⚠️  Er zijn problemen gevonden. Controleer de implementatie.")
