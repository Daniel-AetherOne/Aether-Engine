import torch
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
import pandas as pd
import numpy as np
from PIL import Image
import os
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class LevelAIDataset(Dataset):
    """LevelAI dataset voor substrate en issues classificatie"""
    
    def __init__(self, csv_file: str, image_dir: str, transform=None, mode: str = "train"):
        """
        Args:
            csv_file: Pad naar CSV bestand met kolommen [image_path, substrate, issues_csv]
            image_dir: Directory met afbeeldingen
            transform: Optional transform pipeline
            mode: "train", "val", of "test"
        """
        self.df = pd.read_csv(csv_file)
        self.image_dir = image_dir
        self.mode = mode
        
        # Klassen definities
        self.substrate_classes = ["gipsplaat", "beton", "bestaand"]
        self.issue_classes = ["scheuren", "vocht"]
        
        # Default transforms
        if transform is None:
            if mode == "train":
                self.transform = self._get_train_transforms()
            else:
                self.transform = self._get_val_transforms()
        else:
            self.transform = transform
        
        # Valideer dataset
        self._validate_dataset()
        
        logger.info(f"Dataset geladen: {len(self.df)} samples, mode: {mode}")
    
    def _validate_dataset(self):
        """Valideer dataset integriteit"""
        # Controleer of alle afbeeldingen bestaan
        missing_images = []
        for idx, row in self.df.iterrows():
            image_path = os.path.join(self.image_dir, row['image_path'])
            if not os.path.exists(image_path):
                missing_images.append(row['image_path'])
        
        if missing_images:
            logger.warning(f"Missing images: {len(missing_images)}")
            # Verwijder rijen met ontbrekende afbeeldingen
            self.df = self.df[~self.df['image_path'].isin(missing_images)].reset_index(drop=True)
        
        # Controleer substrate classes
        invalid_substrates = self.df[~self.df['substrate'].isin(self.substrate_classes)]
        if not invalid_substrates.empty:
            logger.warning(f"Invalid substrate classes: {invalid_substrates['substrate'].unique()}")
    
    def _get_train_transforms(self):
        """Training transforms met augmentatie"""
        return transforms.Compose([
            transforms.Resize((256, 256)),
            transforms.RandomCrop(224),
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.RandomRotation(degrees=15),
            transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.1),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                               std=[0.229, 0.224, 0.225])
        ])
    
    def _get_val_transforms(self):
        """Validation transforms zonder augmentatie"""
        return transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                               std=[0.229, 0.224, 0.225])
        ])
    
    def _parse_issues(self, issues_csv: str) -> List[str]:
        """Parse issues CSV string naar lijst van issues"""
        if pd.isna(issues_csv) or issues_csv == "":
            return []
        
        # Split op komma's en strip whitespace
        issues = [issue.strip() for issue in str(issues_csv).split(',')]
        # Filter lege strings
        issues = [issue for issue in issues if issue]
        return issues
    
    def _encode_substrate(self, substrate: str) -> int:
        """Encode substrate naar integer index"""
        try:
            return self.substrate_classes.index(substrate)
        except ValueError:
            logger.warning(f"Unknown substrate: {substrate}, using 'bestaand' as default")
            return self.substrate_classes.index("bestaand")
    
    def _encode_issues(self, issues: List[str]) -> torch.Tensor:
        """Encode issues naar multi-label tensor"""
        # Multi-label encoding: [scheuren, vocht]
        encoding = torch.zeros(len(self.issue_classes), dtype=torch.float32)
        
        for issue in issues:
            if issue in self.issue_classes:
                idx = self.issue_classes.index(issue)
                encoding[idx] = 1.0
        
        return encoding
    
    def __len__(self):
        return len(self.df)
    
    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        
        # Laad afbeelding
        image_path = os.path.join(self.image_dir, row['image_path'])
        try:
            image = Image.open(image_path).convert('RGB')
        except Exception as e:
            logger.error(f"Error loading image {image_path}: {e}")
            # Return dummy image bij fout
            image = Image.new('RGB', (224, 224), color='gray')
        
        # Apply transforms
        if self.transform:
            image = self.transform(image)
        
        # Encode labels
        substrate = self._encode_substrate(row['substrate'])
        issues = self._encode_issues(self._parse_issues(row['issues_csv']))
        
        return {
            'image': image,
            'substrate': torch.tensor(substrate, dtype=torch.long),
            'issues': issues,
            'image_path': row['image_path']
        }

def create_dataloaders(csv_file: str, image_dir: str, batch_size: int = 32, 
                      train_split: float = 0.7, val_split: float = 0.15,
                      num_workers: int = 4, seed: int = 42) -> Tuple[DataLoader, DataLoader, DataLoader]:
    """
    Maak train/val/test dataloaders aan
    
    Args:
        csv_file: Pad naar CSV bestand
        image_dir: Directory met afbeeldingen
        batch_size: Batch size voor dataloaders
        train_split: Percentage voor training (0.0 - 1.0)
        val_split: Percentage voor validation (0.0 - 1.0)
        num_workers: Aantal workers voor dataloading
        seed: Random seed voor reproducibiliteit
    
    Returns:
        Tuple van (train_loader, val_loader, test_loader)
    """
    # Set random seed
    torch.manual_seed(seed)
    np.random.seed(seed)
    
    # Laad volledige dataset
    full_dataset = LevelAIDataset(csv_file, image_dir, mode="train")
    
    # Bereken splits
    total_size = len(full_dataset)
    train_size = int(train_split * total_size)
    val_size = int(val_split * total_size)
    test_size = total_size - train_size - val_size
    
    # Split dataset
    train_dataset, val_dataset, test_dataset = torch.utils.data.random_split(
        full_dataset, [train_size, val_size, test_size]
    )
    
    # Maak datasets aan met juiste transforms
    train_dataset = LevelAIDataset(csv_file, image_dir, mode="train")
    val_dataset = LevelAIDataset(csv_file, image_dir, mode="val")
    test_dataset = LevelAIDataset(csv_file, image_dir, mode="val")  # Gebruik val transforms voor test
    
    # Pas splits toe
    train_dataset.df = train_dataset.df.iloc[:train_size].reset_index(drop=True)
    val_dataset.df = val_dataset.df.iloc[train_size:train_size+val_size].reset_index(drop=True)
    test_dataset.df = test_dataset.df.iloc[train_size+val_size:].reset_index(drop=True)
    
    # Maak dataloaders
    train_loader = DataLoader(
        train_dataset, 
        batch_size=batch_size, 
        shuffle=True, 
        num_workers=num_workers,
        pin_memory=True
    )
    
    val_loader = DataLoader(
        val_dataset, 
        batch_size=batch_size, 
        shuffle=False, 
        num_workers=num_workers,
        pin_memory=True
    )
    
    test_loader = DataLoader(
        test_dataset, 
        batch_size=batch_size, 
        shuffle=False, 
        num_workers=num_workers,
        pin_memory=True
    )
    
    logger.info(f"DataLoaders aangemaakt:")
    logger.info(f"  Train: {len(train_loader.dataset)} samples")
    logger.info(f"  Val: {len(val_loader.dataset)} samples")
    logger.info(f"  Test: {len(test_loader.dataset)} samples")
    
    return train_loader, val_loader, test_loader

def create_sample_dataset(csv_file: str, image_dir: str, num_samples: int = 100):
    """
    Maak een sample dataset aan voor testing
    
    Args:
        csv_file: Pad naar CSV bestand
        image_dir: Directory met afbeeldingen
        num_samples: Aantal sample records
    """
    import random
    
    # Maak image directory aan als deze niet bestaat
    os.makedirs(image_dir, exist_ok=True)
    
    # Sample data
    substrates = ["gipsplaat", "beton", "bestaand"]
    issues_combinations = [
        [],
        ["scheuren"],
        ["vocht"],
        ["scheuren", "vocht"]
    ]
    
    # Genereer sample records
    records = []
    for i in range(num_samples):
        substrate = random.choice(substrates)
        issues = random.choice(issues_combinations)
        
        # Maak dummy image bestand
        image_filename = f"sample_{i:04d}.jpg"
        image_path = os.path.join(image_dir, image_filename)
        
        # Maak dummy image aan
        dummy_image = Image.new('RGB', (224, 224), color=random.choice(['white', 'gray', 'lightblue']))
        dummy_image.save(image_path)
        
        # Maak record
        record = {
            'image_path': image_filename,
            'substrate': substrate,
            'issues_csv': ','.join(issues) if issues else ''
        }
        records.append(record)
    
    # Sla CSV op
    df = pd.DataFrame(records)
    df.to_csv(csv_file, index=False)
    
    logger.info(f"Sample dataset aangemaakt: {csv_file}")
    logger.info(f"  {len(records)} samples")
    logger.info(f"  Images opgeslagen in: {image_dir}")
    
    return df
