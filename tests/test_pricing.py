import unittest
import sys
import os
from pathlib import Path

# Voeg de app directory toe aan Python path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from services.pricing_engine import PricingEngine


class TestPricingEngine(unittest.TestCase):
    """Unit tests voor de PricingEngine class."""
    
    def setUp(self):
        """Setup voor elke test."""
        self.engine = PricingEngine()
    
    def test_gipsplaat_40m2(self):
        """Test case 1: Gipsplaat 40m² zonder issues."""
        result = self.engine.compute_price(40.0, "gipsplaat", [])
        
        # Verwachte berekening:
        # subtotal = 40 * 16.5 = 660.0
        # vat_amount = 660.0 * 0.21 = 138.6
        # total = 660.0 + 138.6 = 798.6
        
        self.assertEqual(result["subtotal"], 660.0)
        self.assertEqual(result["discount"], 0.0)
        self.assertEqual(result["vat_amount"], 138.6)
        self.assertEqual(result["total"], 798.6)
        self.assertIsInstance(result["aannames"], list)
        self.assertIsInstance(result["doorlooptijd"], str)
        
        # Controleer dat aannames gipsplaat-specifiek zijn
        self.assertTrue(any("gipsplaat" in aanname.lower() for aanname in result["aannames"]))
    
    def test_beton_12m2_met_vocht(self):
        """Test case 2: Beton 12m² met vocht issue."""
        result = self.engine.compute_price(12.0, "beton", ["vocht"])
        
        # Verwachte berekening:
        # subtotal = 12 * 22.0 = 264.0
        # vocht surcharge = 264.0 * 0.20 = 52.8
        # subtotal met surcharge = 264.0 + 52.8 = 316.8
        # vat_amount = 316.8 * 0.21 = 66.53
        # total = 316.8 + 66.53 = 383.33
        
        self.assertEqual(result["subtotal"], 316.8)
        self.assertEqual(result["discount"], 0.0)
        self.assertEqual(result["vat_amount"], 66.53)
        self.assertEqual(result["total"], 383.33)
        
        # Controleer dat aannames beton en vocht-specifiek zijn
        self.assertTrue(any("beton" in aanname.lower() for aanname in result["aannames"]))
        self.assertTrue(any("vocht" in aanname.lower() for aanname in result["aannames"]))
    
    def test_bestaand_8m2_min_total(self):
        """Test case 3: Bestaand 8m² - test minimum totaal regel."""
        result = self.engine.compute_price(8.0, "bestaand", [])
        
        # Verwachte berekening:
        # subtotal = 8 * 18.0 = 144.0
        # Maar minimum totaal is 250.0, dus subtotal wordt 250.0
        # vat_amount = 250.0 * 0.21 = 52.5
        # total = 250.0 + 52.5 = 302.5
        
        self.assertEqual(result["subtotal"], 250.0)  # Minimum totaal toegepast
        self.assertEqual(result["discount"], 0.0)
        self.assertEqual(result["vat_amount"], 52.5)
        self.assertEqual(result["total"], 302.5)
        
        # Controleer dat aannames bestaand-specifiek zijn
        self.assertTrue(any("bestaand" in aanname.lower() for aanname in result["aannames"]))
    
    def test_invalid_substrate(self):
        """Test ongeldig substrate."""
        with self.assertRaises(ValueError) as context:
            self.engine.compute_price(10.0, "ongeldig", [])
        
        self.assertIn("Ongeldig substrate", str(context.exception))
    
    def test_invalid_m2(self):
        """Test ongeldige m² waarde."""
        with self.assertRaises(ValueError) as context:
            self.engine.compute_price(-5.0, "gipsplaat", [])
        
        self.assertIn("m2 moet groter zijn dan 0", str(context.exception))
    
    def test_multiple_issues(self):
        """Test meerdere issues tegelijk."""
        result = self.engine.compute_price(15.0, "beton", ["vocht", "scheuren"])
        
        # Verwachte berekening:
        # subtotal = 15 * 22.0 = 330.0
        # vocht surcharge = 0.20, scheuren surcharge = 0.10
        # totaal surcharge = 0.30
        # subtotal met surcharge = 330.0 * 1.30 = 429.0
        # vat_amount = 429.0 * 0.21 = 90.09
        # total = 429.0 + 90.09 = 519.09
        
        self.assertEqual(result["subtotal"], 429.0)
        self.assertEqual(result["vat_amount"], 90.09)
        self.assertEqual(result["total"], 519.09)
        
        # Controleer dat beide issues in aannames voorkomen
        self.assertTrue(any("vocht" in aanname.lower() for aanname in result["aannames"]))
        self.assertTrue(any("scheuren" in aanname.lower() for aanname in result["aannames"]))


if __name__ == "__main__":
    unittest.main()
