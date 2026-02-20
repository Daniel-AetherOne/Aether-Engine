# LevelAI Vision Module

Een PyTorch-gebaseerde computer vision module voor LevelAI die automatisch substrate types en issues detecteert in afbeeldingen.

## 🎯 Functionaliteit

- **Substrate Classificatie**: Detecteert 3 types (gipsplaat, beton, bestaand) met softmax output
- **Issues Detectie**: Multi-label detectie van scheuren en vocht met sigmoid output
- **Fallback Heuristiek**: Werkt ook zonder getraind model via filename-based heuristiek
- **FastAPI Integration**: Volledig geïntegreerd in de LevelAI SaaS platform

## 🏗️ Architectuur

```
EfficientNet-B0 Backbone
         ↓
    Shared Features
         ↓
┌─────────────────┬─────────────────┐
│ Substrate Head  │   Issues Head   │
│   (Softmax)     │   (Sigmoid)     │
│                 │                 │
│ - gipsplaat     │ - scheuren      │
│ - beton         │ - vocht         │
│ - bestaand      │                 │
└─────────────────┴─────────────────┘
```

## 📁 Bestandsstructuur

```
app/tasks/
├── vision.py          # Hoofdmodule met model en predictor
├── dataset.py         # Dataset en dataloader implementatie
└── ...

train.py               # Training script
test_vision.py         # Test script
requirements_vision.txt # PyTorch dependencies
VISION_README.md       # Deze documentatie
```

## 🚀 Installatie

### 1. Dependencies installeren

```bash
pip install -r requirements_vision.txt
```

### 2. Test de installatie

```bash
python test_vision.py
```

## 🎓 Training

### 1. Dataset voorbereiden

Je dataset moet een CSV bestand hebben met deze kolommen:
- `image_path`: Relatief pad naar afbeelding
- `substrate`: Een van [gipsplaat, beton, bestaand]
- `issues_csv`: Komma-gescheiden issues (scheuren, vocht)

Voorbeeld:
```csv
image_path,substrate,issues_csv
image1.jpg,gipsplaat,scheuren
image2.jpg,beton,vocht
image3.jpg,bestaand,
```

### 2. Training starten

```bash
# Met bestaande dataset
python train.py --csv data/dataset.csv --images data/images/ --epochs 50

# Of maak een sample dataset aan voor testing
python train.py --csv data/dataset.csv --images data/images/ --epochs 10 --create-sample --num-samples 300
```

### 3. Training parameters

- `--epochs`: Aantal training epochs (default: 50)
- `--batch-size`: Batch size (default: 32)
- `--lr`: Learning rate (default: 0.001)
- `--output-dir`: Output directory voor model (default: models/)

## 🔍 Inference

### 1. Via Python API

```python
from app.tasks.vision import predict_images

# Voorspel voor één of meerdere afbeeldingen
predictions = predict_images([
    "path/to/image1.jpg",
    "path/to/image2.jpg"
])

for pred in predictions:
    print(f"Substrate: {pred['substrate']} (conf: {pred['substrate_confidence']:.2f})")
    print(f"Issues: {pred['issues']} (conf: {pred['issue_confidences']})")
```

### 2. Via FastAPI Endpoint

```bash
# Upload afbeeldingen
curl -X POST "http://localhost:8000/predict/vision" \
     -H "accept: application/json" \
     -H "Content-Type: multipart/form-data" \
     -F "files=@image1.jpg" \
     -F "files=@image2.jpg"

# Check model status
curl "http://localhost:8000/predict/vision/status"
```

## 📊 Acceptatie Criteria

Het model moet voldoen aan deze criteria:
- ✅ **Substrate Accuracy**: > 70% op test set
- ✅ **Issues F1 Score**: Acceptabele score op multi-label classificatie
- ✅ **Fallback Functionaliteit**: Werkt altijd via heuristiek als model niet beschikbaar is

## 🧪 Testing

### 1. Unit Tests

```bash
python test_vision.py
```

### 2. Integration Test

```bash
# Start FastAPI server
uvicorn app.main:app --reload

# Test vision endpoint
curl -X POST "http://localhost:8000/predict/vision" \
     -F "files=@test_image.jpg"
```

## 🔧 Configuratie

### Model Parameters

Het model kan aangepast worden in `app/tasks/vision.py`:

```python
class LevelAIModel(nn.Module):
    def __init__(self, 
                 num_substrates: int = 3, 
                 num_issues: int = 2, 
                 backbone_name: str = "efficientnet_b0"):
        # ...
```

### Data Augmentation

Augmentatie parameters zijn te vinden in `app/tasks/dataset.py`:

```python
def _get_train_transforms(self):
    return transforms.Compose([
        transforms.Resize((256, 256)),
        transforms.RandomCrop(224),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomRotation(degrees=15),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.1),
        # ...
    ])
```

## 📈 Monitoring

### Training Metrics

Het training script genereert:
- Training/validation loss curves
- Substrate accuracy over tijd
- Issues F1 score over tijd
- Best model checkpoint
- Training configuratie

### Inference Metrics

De FastAPI endpoint geeft:
- Prediction confidence scores
- Gebruikte methode (PyTorch model vs heuristiek)
- Processing tijd
- Error handling met fallback

## 🚨 Troubleshooting

### Veelvoorkomende problemen

1. **CUDA out of memory**: Verlaag batch size of gebruik CPU
2. **Import errors**: Installeer alle dependencies uit `requirements_vision.txt`
3. **Model niet laden**: Controleer of het model bestand bestaat en toegankelijk is
4. **Dataset errors**: Valideer CSV formaat en image paths

### Debug mode

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Of in FastAPI
import logging
logging.getLogger("app.tasks.vision").setLevel(logging.DEBUG)
```

## 🔮 Toekomstige Verbeteringen

- [ ] Support voor meer backbone modellen (ResNet, ViT)
- [ ] Multi-scale inference voor verschillende image sizes
- [ ] Ensemble methods voor betere accuracy
- [ ] Real-time video processing
- [ ] Integration met externe ML platforms (MLflow, Weights & Biases)

## 📞 Support

Voor vragen of problemen:
1. Check de logs voor error details
2. Run `test_vision.py` om de setup te valideren
3. Controleer of alle dependencies correct geïnstalleerd zijn
4. Raadpleeg de PyTorch en TIMM documentatie

---

**LevelAI Vision Module** - Powered by PyTorch & EfficientNet
