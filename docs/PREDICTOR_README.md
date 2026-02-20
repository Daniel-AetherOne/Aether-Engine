# LevelAI SaaS - Simple Predictor

## Overzicht

De SimplePredictor is een tijdelijke, heuristische oplossing voor het voorspellen van substrate type en het detecteren van issues in afbeeldingen, zonder dat er een getraind ML-model nodig is. Dit stelt je in staat om end-to-end te kunnen offreren terwijl je wacht op een getraind model.

## Functionaliteit

### Substrate Detectie
De predictor analyseert afbeeldingen op basis van:
- **Contrast**: Verschil tussen lichte en donkere gebieden
- **Ruis**: Niveau van beeldruis en texture variatie
- **Edge Density**: Dichtheid van randen (Canny edge detection)
- **Texture Variance**: Lokale variatie in pixelwaarden

**Mogelijke substrate types:**
- `gipsplaat` - Droge muur met lage contrast en edge density
- `beton` - Hoge contrast en edge density
- `bestaand` - Bestaande ondergrond met gemengde eigenschappen

### Issue Detectie
De predictor detecteert:
- **Scheuren**: Via Canny edge detection en morfologische operaties
- **Vocht**: Via HSV kleuranalyse voor donkere, verzadigde gebieden

## API Gebruik

### Endpoint
```
POST /predict
```

### Request Body
```json
{
  "lead_id": "unique-lead-identifier",
  "image_paths": ["path/to/image1.jpg", "path/to/image2.jpg"],
  "m2": 25.5
}
```

### Response
```json
{
  "substrate": "gipsplaat",
  "issues": ["scheuren"],
  "confidences": {
    "substrate": 0.69,
    "scheuren": 1.0,
    "vocht": 0.15
  }
}
```

## Implementatie Details

### Bestandsstructuur
```
app/
├── services/
│   └── predictor.py          # SimplePredictor service
├── routers/
│   └── predict.py            # API endpoint
└── models/
    └── predict.py            # Pydantic modellen
```

### Kern Functies

#### `SimplePredictor.predict(lead_id, image_paths, m2)`
Hoofdfunctie die de analyse uitvoert en resultaten retourneert.

#### `_analyze_substrate(image_path)`
Analyseert een afbeelding om het substrate type te bepalen.

#### `_analyze_issues(image_path)`
Detecteert issues in de afbeelding.

#### `_detect_cracks(gray_image)`
Specifieke functie voor scheurdetectie via edge analysis.

#### `_detect_moisture(color_image)`
Specifieke functie voor vochtdetectie via HSV kleuranalyse.

## Technische Details

### Afhankelijkheden
- **Pillow (PIL)**: Afbeelding verwerking
- **OpenCV (cv2)**: Computer vision algoritmes
- **NumPy**: Numerieke berekeningen

### Algoritmes
1. **Contrast Berekening**: Standaarddeviatie van pixelwaarden
2. **Ruis Detectie**: Vergelijking met Gaussian blur
3. **Edge Detection**: Canny algoritme voor randdetectie
4. **Texture Analyse**: Lokale variantie berekening
5. **Kleur Analyse**: HSV kleurruimte conversie

### Drempelwaarden
- **Scheuren**: Confidence > 0.4
- **Vocht**: Confidence > 0.3
- **Substrate**: Dynamische drempels op basis van feature scores

## Testen

### Lokale Test
```bash
# Test de predictor service
python test_predictor.py

# Test de API endpoint
python test_api.py

# Maak test afbeelding
python create_test_image.py
```

### API Test
```bash
# Start de server
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Test endpoint
curl -X POST "http://localhost:8000/predict" \
  -H "Content-Type: application/json" \
  -d '{
    "lead_id": "test-123",
    "image_paths": ["data/uploads/test/test_wall_with_cracks.jpg"],
    "m2": 25.5
  }'
```

## Voorbeelden

### Interieurfoto Analyse
Voor een willekeurige interieurfoto retourneert de service:
```json
{
  "substrate": "bestaand",
  "issues": ["scheuren"],
  "confidences": {
    "substrate": 0.65,
    "scheuren": 0.6,
    "vocht": 0.2
  }
}
```

### Beton Analyse
Voor een betonnen muur:
```json
{
  "substrate": "beton",
  "issues": [],
  "confidences": {
    "substrate": 0.8,
    "scheuren": 0.2,
    "vocht": 0.15
  }
}
```

## Beperkingen

1. **Geen ML**: Gebruikt alleen heuristische regels
2. **Eerste Afbeelding**: Analyseert alleen de eerste afbeelding in de lijst
3. **Eenvoudige Drempels**: Geen geavanceerde patroonherkenning
4. **Kleurgevoelig**: Resultaten kunnen variëren bij verschillende belichting

## Toekomstige Verbeteringen

1. **ML Model Integratie**: Vervang heuristiek door getrainde modellen
2. **Multi-Image Analyse**: Combineer resultaten van meerdere afbeeldingen
3. **Confidence Calibration**: Verbeter betrouwbaarheid van confidence scores
4. **Meer Issue Types**: Uitbreiding naar andere problemen (schimmel, verfschade, etc.)
5. **Real-time Processing**: Ondersteuning voor video streams

## Troubleshooting

### Veelvoorkomende Problemen

1. **404 Error**: Controleer of de route correct is geregistreerd
2. **Import Errors**: Zorg dat alle dependencies zijn geïnstalleerd
3. **Image Not Found**: Valideer dat afbeeldingsformaten correct zijn
4. **Memory Issues**: Grote afbeeldingen kunnen geheugenproblemen veroorzaken

### Debug Tips

1. Controleer server logs voor error details
2. Gebruik `test_predictor.py` voor service testing
3. Valideer afbeeldingsformaten (JPG, PNG, BMP ondersteund)
4. Test met verschillende afbeeldingsgroottes

## Conclusie

De SimplePredictor biedt een werkende oplossing voor end-to-end offrering zonder ML-dependencies. Hoewel de resultaten "gokkerig" zijn, geven ze een redelijke indicatie van substrate type en issues, wat voldoende is voor tijdelijke gebruik totdat een getraind model beschikbaar is.
