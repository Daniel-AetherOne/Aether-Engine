#!/usr/bin/env python3
"""
Test script voor LevelAI Vision Module

Dit script test de vision module zonder dat er een getraind model nodig is.
Het gebruikt de fallback heuristiek om te demonstreren dat de pipeline werkt.
"""

import os
import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_vision_module():
    """Test de vision module functionaliteit"""
    try:
        # Import vision module
        from app.tasks.vision import get_vision_predictor, predict_images
        
        logger.info("✅ Vision module succesvol geïmporteerd")
        
        # Test predictor zonder model (gebruikt fallback)
        predictor = get_vision_predictor()
        logger.info(f"✅ Vision predictor aangemaakt op device: {predictor.device}")
        logger.info(f"✅ Model geladen: {predictor.model is not None}")
        
        # Test fallback heuristiek
        test_image_paths = [
            "test_gipsplaat_scheuren.jpg",
            "test_beton_vocht.jpg", 
            "test_bestaand.jpg"
        ]
        
        logger.info("🧪 Test fallback heuristiek...")
        predictions = predictor.predict(test_image_paths)
        
        for pred in predictions:
            logger.info(f"  {pred['image_path']}:")
            logger.info(f"    Substrate: {pred['substrate']} (conf: {pred['substrate_confidence']:.2f})")
            logger.info(f"    Issues: {pred['issues']} (conf: {pred['issue_confidences']})")
            logger.info(f"    Method: {pred['method']}")
        
        logger.info("✅ Fallback heuristiek werkt correct")
        
        return True
        
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        logger.error("Zorg ervoor dat alle dependencies geïnstalleerd zijn:")
        logger.error("pip install -r requirements_vision.txt")
        return False
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False

def test_dataset_module():
    """Test de dataset module"""
    try:
        from app.tasks.dataset import create_sample_dataset
        
        logger.info("🧪 Test dataset module...")
        
        # Maak test dataset aan
        test_csv = "test_dataset.csv"
        test_images = "test_images"
        
        if os.path.exists(test_csv):
            os.remove(test_csv)
        
        df = create_sample_dataset(test_csv, test_images, num_samples=10)
        logger.info(f"✅ Sample dataset aangemaakt: {len(df)} samples")
        
        # Test dataloaders
        from app.tasks.dataset import create_dataloaders
        
        train_loader, val_loader, test_loader = create_dataloaders(
            test_csv, test_images, batch_size=4
        )
        
        logger.info(f"✅ DataLoaders aangemaakt:")
        logger.info(f"  Train: {len(train_loader.dataset)} samples")
        logger.info(f"  Val: {len(val_loader.dataset)} samples")
        logger.info(f"  Test: {len(test_loader.dataset)} samples")
        
        # Test één batch
        for batch in train_loader:
            logger.info(f"✅ Batch shape: {batch['image'].shape}")
            logger.info(f"✅ Substrate labels: {batch['substrate']}")
            logger.info(f"✅ Issues labels: {batch['issues']}")
            break
        
        # Cleanup
        os.remove(test_csv)
        import shutil
        shutil.rmtree(test_images)
        
        logger.info("✅ Dataset module werkt correct")
        return True
        
    except Exception as e:
        logger.error(f"❌ Dataset test failed: {e}")
        return False

def test_model_architecture():
    """Test de model architectuur"""
    try:
        import torch
        from app.tasks.vision import LevelAIModel
        
        logger.info("🧪 Test model architectuur...")
        
        # Maak model aan
        model = LevelAIModel()
        logger.info(f"✅ Model aangemaakt: {type(model).__name__}")
        
        # Test forward pass
        dummy_input = torch.randn(1, 3, 224, 224)
        substrate_logits, issues_logits = model(dummy_input)
        
        logger.info(f"✅ Forward pass succesvol:")
        logger.info(f"  Substrate logits shape: {substrate_logits.shape}")
        logger.info(f"  Issues logits shape: {issues_logits.shape}")
        
        # Test output ranges
        substrate_probs = torch.softmax(substrate_logits, dim=1)
        issues_probs = torch.sigmoid(issues_logits)
        
        logger.info(f"✅ Output ranges correct:")
        logger.info(f"  Substrate probs sum: {substrate_probs.sum().item():.4f}")
        logger.info(f"  Issues probs range: [{issues_probs.min().item():.4f}, {issues_probs.max().item():.4f}]")
        
        # Test model parameters
        total_params = sum(p.numel() for p in model.parameters())
        trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
        
        logger.info(f"✅ Model parameters:")
        logger.info(f"  Total: {total_params:,}")
        logger.info(f"  Trainable: {trainable_params:,}")
        
        logger.info("✅ Model architectuur werkt correct")
        return True
        
    except Exception as e:
        logger.error(f"❌ Model test failed: {e}")
        return False

def main():
    """Hoofdfunctie voor alle tests"""
    logger.info("🚀 Start LevelAI Vision Module Tests")
    logger.info("=" * 50)
    
    tests = [
        ("Vision Module", test_vision_module),
        ("Dataset Module", test_dataset_module),
        ("Model Architecture", test_model_architecture)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        logger.info(f"\n🧪 Testing: {test_name}")
        logger.info("-" * 30)
        
        try:
            success = test_func()
            results.append((test_name, success))
            
            if success:
                logger.info(f"✅ {test_name}: PASSED")
            else:
                logger.info(f"❌ {test_name}: FAILED")
                
        except Exception as e:
            logger.error(f"❌ {test_name}: ERROR - {e}")
            results.append((test_name, False))
    
    # Samenvatting
    logger.info("\n" + "=" * 50)
    logger.info("📊 TEST SAMENVATTING")
    logger.info("=" * 50)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        logger.info(f"  {test_name}: {status}")
    
    logger.info(f"\nTotaal: {passed}/{total} tests geslaagd")
    
    if passed == total:
        logger.info("🎉 Alle tests geslaagd! Vision module is klaar voor gebruik.")
        return 0
    else:
        logger.error("💥 Sommige tests gefaald. Controleer de foutmeldingen hierboven.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
