#!/usr/bin/env python3
"""
LevelAI Vision Module Demo

Dit script demonstreert de functionaliteit van de vision module
zonder dat er een getraind model nodig is.
"""

import os
import sys
import logging
from pathlib import Path
import json

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_demo_images():
    """Maak demo afbeeldingen aan voor testing"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import random
        
        demo_dir = Path("demo_images")
        demo_dir.mkdir(exist_ok=True)
        
        # Demo afbeeldingen met verschillende substrate types en issues
        demo_configs = [
            {"name": "gipsplaat_scheuren.jpg", "substrate": "gipsplaat", "issues": ["scheuren"], "color": "white"},
            {"name": "gipsplaat_vocht.jpg", "substrate": "gipsplaat", "issues": ["vocht"], "color": "lightblue"},
            {"name": "beton_scheuren.jpg", "substrate": "beton", "issues": ["scheuren"], "color": "gray"},
            {"name": "beton_vocht.jpg", "substrate": "beton", "issues": ["vocht"], "color": "blue"},
            {"name": "bestaand_geen.jpg", "substrate": "bestaand", "issues": [], "color": "beige"},
            {"name": "gipsplaat_beide.jpg", "substrate": "gipsplaat", "issues": ["scheuren", "vocht"], "color": "lightgray"},
        ]
        
        created_images = []
        
        for config in demo_configs:
            # Maak afbeelding aan
            img = Image.new('RGB', (400, 300), config["color"])
            draw = ImageDraw.Draw(img)
            
            # Voeg tekst toe
            try:
                # Probeer een font te laden, anders gebruik default
                font = ImageFont.truetype("arial.ttf", 20)
            except:
                font = ImageFont.load_default()
            
            # Teken substrate type
            draw.text((20, 20), f"Substrate: {config['substrate']}", fill="black", font=font)
            
            # Teken issues
            issues_text = f"Issues: {', '.join(config['issues']) if config['issues'] else 'geen'}"
            draw.text((20, 50), issues_text, fill="black", font=font)
            
            # Voeg wat visuele elementen toe
            if "scheuren" in config["issues"]:
                # Teken scheuren
                for i in range(3):
                    x1 = random.randint(50, 350)
                    y1 = random.randint(100, 250)
                    x2 = x1 + random.randint(-50, 50)
                    y2 = y1 + random.randint(-50, 50)
                    draw.line([(x1, y1), (x2, y2)], fill="black", width=3)
            
            if "vocht" in config["issues"]:
                # Teken vocht vlekken
                for i in range(5):
                    x = random.randint(50, 350)
                    y = random.randint(100, 250)
                    radius = random.randint(10, 30)
                    draw.ellipse([x-radius, y-radius, x+radius, y+radius], fill="blue", outline="darkblue")
            
            # Sla afbeelding op
            image_path = demo_dir / config["name"]
            img.save(image_path)
            created_images.append(str(image_path))
            
            logger.info(f"Demo afbeelding aangemaakt: {config['name']}")
        
        return created_images
        
    except ImportError:
        logger.warning("PIL niet beschikbaar, maak eenvoudige demo afbeeldingen aan...")
        
        # Fallback: maak lege bestanden aan
        demo_dir = Path("demo_images")
        demo_dir.mkdir(exist_ok=True)
        
        demo_files = [
            "gipsplaat_scheuren.jpg",
            "gipsplaat_vocht.jpg", 
            "beton_scheuren.jpg",
            "beton_vocht.jpg",
            "bestaand_geen.jpg",
            "gipsplaat_beide.jpg"
        ]
        
        created_images = []
        for filename in demo_files:
            file_path = demo_dir / filename
            with open(file_path, 'w') as f:
                f.write("demo_image")
            created_images.append(str(file_path))
            logger.info(f"Demo bestand aangemaakt: {filename}")
        
        return created_images

def demo_vision_predictions():
    """Demonstreer vision predictions"""
    try:
        from app.tasks.vision import predict_images, get_vision_predictor
        
        logger.info("🔍 Vision predictions demonstreren...")
        
        # Maak demo afbeeldingen aan
        demo_images = create_demo_images()
        
        if not demo_images:
            logger.error("Geen demo afbeeldingen kunnen aanmaken")
            return False
        
        # Maak voorspellingen
        logger.info(f"Voorspellingen maken voor {len(demo_images)} demo afbeeldingen...")
        predictions = predict_images(demo_images)
        
        # Toon resultaten
        logger.info("\n📊 Voorspelling Resultaten:")
        logger.info("=" * 60)
        
        for i, pred in enumerate(predictions):
            logger.info(f"\n🖼️  Afbeelding {i+1}: {Path(pred['image_path']).name}")
            logger.info(f"   Substrate: {pred['substrate']} (confidence: {pred['substrate_confidence']:.2f})")
            logger.info(f"   Issues: {', '.join(pred['issues'])}")
            logger.info(f"   Issue confidences: {[f'{conf:.2f}' for conf in pred['issue_confidences']]}")
            logger.info(f"   Methode: {pred['method']}")
        
        # Statistieken
        substrates = [p['substrate'] for p in predictions]
        methods = [p['method'] for p in predictions]
        
        logger.info("\n📈 Statistieken:")
        logger.info(f"   Totaal afbeeldingen: {len(predictions)}")
        logger.info(f"   Unieke substrates: {set(substrates)}")
        logger.info(f"   PyTorch model gebruikt: {methods.count('pytorch_model')}")
        logger.info(f"   Heuristiek gebruikt: {methods.count('heuristic_fallback')}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Demo failed: {e}")
        return False

def demo_fastapi_integration():
    """Demonstreer FastAPI integratie"""
    try:
        logger.info("\n🌐 FastAPI integratie demonstreren...")
        
        # Check of FastAPI beschikbaar is
        try:
            from fastapi import FastAPI
            from app.routers.predict import router as predict_router
            
            logger.info("✅ FastAPI en predict router beschikbaar")
            
            # Toon beschikbare endpoints
            logger.info("📋 Beschikbare vision endpoints:")
            logger.info("   POST /predict/vision - Upload afbeeldingen voor voorspelling")
            logger.info("   GET  /predict/vision/status - Check model status")
            
            # Simuleer een request (zonder daadwerkelijk server te starten)
            logger.info("\n💡 Gebruik voorbeeld:")
            logger.info("   curl -X POST 'http://localhost:8000/predict/vision' \\")
            logger.info("        -F 'files=@demo_images/gipsplaat_scheuren.jpg'")
            
            return True
            
        except ImportError:
            logger.warning("⚠️ FastAPI niet beschikbaar, skip FastAPI demo")
            return False
            
    except Exception as e:
        logger.error(f"❌ FastAPI demo failed: {e}")
        return False

def demo_training_workflow():
    """Demonstreer training workflow"""
    try:
        logger.info("\n🎓 Training workflow demonstreren...")
        
        # Check of training dependencies beschikbaar zijn
        try:
            import torch
            import timm
            from app.tasks.vision import LevelAIModel
            from app.tasks.dataset import create_sample_dataset
            
            logger.info("✅ Training dependencies beschikbaar")
            
            # Maak een klein sample dataset aan
            logger.info("📊 Sample dataset aanmaken...")
            sample_csv = "demo_training_data.csv"
            sample_images = "demo_training_images"
            
            if os.path.exists(sample_csv):
                os.remove(sample_csv)
            
            df = create_sample_dataset(sample_csv, sample_images, num_samples=20)
            logger.info(f"✅ Sample dataset aangemaakt: {len(df)} samples")
            
            # Toon dataset statistieken
            substrate_counts = df['substrate'].value_counts()
            logger.info("📊 Dataset verdeling:")
            for substrate, count in substrate_counts.items():
                logger.info(f"   {substrate}: {count} samples")
            
            # Test model architectuur
            logger.info("\n🏗️ Model architectuur testen...")
            model = LevelAIModel()
            
            # Test forward pass
            dummy_input = torch.randn(1, 3, 224, 224)
            substrate_logits, issues_logits = model(dummy_input)
            
            logger.info(f"✅ Model forward pass succesvol:")
            logger.info(f"   Substrate output: {substrate_logits.shape}")
            logger.info(f"   Issues output: {issues_logits.shape}")
            
            # Cleanup
            os.remove(sample_csv)
            import shutil
            shutil.rmtree(sample_images)
            
            logger.info("\n💡 Training starten met:")
            logger.info("   python train.py --csv data/dataset.csv --images data/images/ --epochs 10 --create-sample")
            
            return True
            
        except ImportError as e:
            logger.warning(f"⚠️ Training dependencies niet beschikbaar: {e}")
            logger.info("Installeer met: pip install -r requirements_vision.txt")
            return False
            
    except Exception as e:
        logger.error(f"❌ Training demo failed: {e}")
        return False

def main():
    """Hoofdfunctie voor de demo"""
    logger.info("🚀 LevelAI Vision Module Demo")
    logger.info("=" * 50)
    
    demos = [
        ("Vision Predictions", demo_vision_predictions),
        ("FastAPI Integration", demo_fastapi_integration),
        ("Training Workflow", demo_training_workflow)
    ]
    
    results = []
    
    for demo_name, demo_func in demos:
        logger.info(f"\n🎬 Demo: {demo_name}")
        logger.info("-" * 30)
        
        try:
            success = demo_func()
            results.append((demo_name, success))
            
            if success:
                logger.info(f"✅ {demo_name}: SUCCESS")
            else:
                logger.info(f"❌ {demo_name}: FAILED")
                
        except Exception as e:
            logger.error(f"❌ {demo_name}: ERROR - {e}")
            results.append((demo_name, False))
    
    # Samenvatting
    logger.info("\n" + "=" * 50)
    logger.info("📊 DEMO SAMENVATTING")
    logger.info("=" * 50)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for demo_name, success in results:
        status = "✅ SUCCESS" if success else "❌ FAILED"
        logger.info(f"  {demo_name}: {status}")
    
    logger.info(f"\nTotaal: {passed}/{total} demo's geslaagd")
    
    if passed == total:
        logger.info("\n🎉 Alle demo's geslaagd! De vision module is klaar voor gebruik.")
        logger.info("\n📚 Volgende stappen:")
        logger.info("   1. Installeer dependencies: pip install -r requirements_vision.txt")
        logger.info("   2. Test de module: python test_vision.py")
        logger.info("   3. Start training: python train.py --create-sample --epochs 10")
        logger.info("   4. Start FastAPI server: uvicorn app.main:app --reload")
        return 0
    else:
        logger.error("\n💥 Sommige demo's gefaald. Controleer de foutmeldingen hierboven.")
        logger.info("\n🔧 Mogelijke oplossingen:")
        logger.info("   1. Installeer ontbrekende dependencies")
        logger.info("   2. Check of alle bestanden correct zijn aangemaakt")
        logger.info("   3. Run test_vision.py voor debugging")
        return 1

if __name__ == "__main__":
    sys.exit(main())
