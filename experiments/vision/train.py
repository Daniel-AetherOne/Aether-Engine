#!/usr/bin/env python3
"""
LevelAI Vision Model Training Script

Dit script traint een PyTorch model voor substrate en issues classificatie.
Het model gebruikt een EfficientNet backbone met twee heads:
- Head 1: Substrate classificatie (gipsplaat, beton, bestaand) - softmax
- Head 2: Issues classificatie (scheuren, vocht) - sigmoid

Gebruik:
    python train.py --csv data/dataset.csv --images data/images/ --epochs 50
"""

import argparse
import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.optim.lr_scheduler import ReduceLROnPlateau
import numpy as np
from sklearn.metrics import accuracy_score, f1_score, classification_report
import logging
from pathlib import Path
import json
from datetime import datetime
import matplotlib.pyplot as plt

# Import onze modules
from app.tasks.vision import LevelAIModel
from app.tasks.dataset import create_dataloaders, create_sample_dataset

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def train_epoch(model, train_loader, criterion_substrate, criterion_issues, optimizer, device):
    """Train één epoch"""
    model.train()
    running_loss = 0.0
    substrate_correct = 0
    substrate_total = 0
    
    for batch_idx, batch in enumerate(train_loader):
        images = batch['image'].to(device)
        substrate_labels = batch['substrate'].to(device)
        issues_labels = batch['issues'].to(device)
        
        # Forward pass
        optimizer.zero_grad()
        substrate_logits, issues_logits = model(images)
        
        # Bereken losses
        loss_substrate = criterion_substrate(substrate_logits, substrate_labels)
        loss_issues = criterion_issues(issues_logits, issues_labels)
        
        # Total loss (gewogen gemiddelde)
        total_loss = 0.6 * loss_substrate + 0.4 * loss_issues
        
        # Backward pass
        total_loss.backward()
        optimizer.step()
        
        # Statistics
        running_loss += total_loss.item()
        
        # Substrate accuracy
        _, predicted_substrate = torch.max(substrate_logits, 1)
        substrate_correct += (predicted_substrate == substrate_labels).sum().item()
        substrate_total += substrate_labels.size(0)
        
        if batch_idx % 10 == 0:
            logger.info(f"Batch {batch_idx}/{len(train_loader)}, Loss: {total_loss.item():.4f}")
    
    epoch_loss = running_loss / len(train_loader)
    epoch_acc = substrate_correct / substrate_total
    
    return epoch_loss, epoch_acc

def validate_epoch(model, val_loader, criterion_substrate, criterion_issues, device):
    """Validate één epoch"""
    model.eval()
    running_loss = 0.0
    substrate_correct = 0
    substrate_total = 0
    
    all_substrate_preds = []
    all_substrate_labels = []
    all_issues_preds = []
    all_issues_labels = []
    
    with torch.no_grad():
        for batch in val_loader:
            images = batch['image'].to(device)
            substrate_labels = batch['substrate'].to(device)
            issues_labels = batch['issues'].to(device)
            
            # Forward pass
            substrate_logits, issues_logits = model(images)
            
            # Bereken losses
            loss_substrate = criterion_substrate(substrate_logits, substrate_labels)
            loss_issues = criterion_issues(issues_logits, issues_labels)
            total_loss = 0.6 * loss_substrate + 0.4 * loss_issues
            
            running_loss += total_loss.item()
            
            # Substrate predictions
            _, predicted_substrate = torch.max(substrate_logits, 1)
            substrate_correct += (predicted_substrate == substrate_labels).sum().item()
            substrate_total += substrate_labels.size(0)
            
            # Issues predictions (multi-label)
            issues_probs = torch.sigmoid(issues_logits)
            predicted_issues = (issues_probs > 0.5).float()
            
            # Collect voor metrics
            all_substrate_preds.extend(predicted_substrate.cpu().numpy())
            all_substrate_labels.extend(substrate_labels.cpu().numpy())
            all_issues_preds.extend(predicted_issues.cpu().numpy())
            all_issues_labels.extend(issues_labels.cpu().numpy())
    
    epoch_loss = running_loss / len(val_loader)
    substrate_acc = substrate_correct / substrate_total
    
    # Issues F1 score (micro-averaged)
    issues_f1 = f1_score(all_issues_labels, all_issues_preds, average='micro', zero_division=0)
    
    return epoch_loss, substrate_acc, issues_f1

def save_training_plots(train_losses, val_losses, train_accs, val_accs, val_f1s, save_dir):
    """Sla training plots op"""
    os.makedirs(save_dir, exist_ok=True)
    
    # Loss plot
    plt.figure(figsize=(12, 4))
    
    plt.subplot(1, 3, 1)
    plt.plot(train_losses, label='Train Loss')
    plt.plot(val_losses, label='Val Loss')
    plt.title('Training and Validation Loss')
    plt.xlabel('Epoch')
    plt.ylabel('Loss')
    plt.legend()
    plt.grid(True)
    
    # Substrate accuracy plot
    plt.subplot(1, 3, 2)
    plt.plot(train_accs, label='Train Acc')
    plt.plot(val_accs, label='Val Acc')
    plt.title('Substrate Accuracy')
    plt.xlabel('Epoch')
    plt.ylabel('Accuracy')
    plt.legend()
    plt.grid(True)
    
    # Issues F1 plot
    plt.subplot(1, 3, 3)
    plt.plot(val_f1s, label='Val F1')
    plt.title('Issues F1 Score')
    plt.xlabel('Epoch')
    plt.ylabel('F1 Score')
    plt.legend()
    plt.grid(True)
    
    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, 'training_plots.png'), dpi=300, bbox_inches='tight')
    plt.close()

def main():
    parser = argparse.ArgumentParser(description='Train LevelAI Vision Model')
    parser.add_argument('--csv', type=str, required=True, help='Pad naar CSV dataset bestand')
    parser.add_argument('--images', type=str, required=True, help='Directory met afbeeldingen')
    parser.add_argument('--epochs', type=int, default=50, help='Aantal training epochs')
    parser.add_argument('--batch-size', type=int, default=32, help='Batch size')
    parser.add_argument('--lr', type=float, default=0.001, help='Learning rate')
    parser.add_argument('--output-dir', type=str, default='models', help='Output directory voor model')
    parser.add_argument('--create-sample', action='store_true', help='Maak sample dataset aan')
    parser.add_argument('--num-samples', type=int, default=300, help='Aantal samples voor sample dataset')
    
    args = parser.parse_args()
    
    # Maak output directory aan
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Check of dataset bestaat, anders maak sample aan
    if not os.path.exists(args.csv) and args.create_sample:
        logger.info(f"Dataset {args.csv} niet gevonden, maak sample dataset aan...")
        create_sample_dataset(args.csv, args.images, args.num_samples)
    elif not os.path.exists(args.csv):
        logger.error(f"Dataset {args.csv} niet gevonden. Gebruik --create-sample om een sample dataset aan te maken.")
        return
    
    # Device setup
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Using device: {device}")
    
    # Maak dataloaders aan
    logger.info("DataLoaders aanmaken...")
    train_loader, val_loader, test_loader = create_dataloaders(
        args.csv, args.images, batch_size=args.batch_size
    )
    
    # Model initialisatie
    logger.info("Model initialiseren...")
    model = LevelAIModel().to(device)
    
    # Loss functions
    criterion_substrate = nn.CrossEntropyLoss()
    criterion_issues = nn.BCEWithLogitsLoss()
    
    # Optimizer en scheduler
    optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    scheduler = ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=5, verbose=True)
    
    # Training loop
    logger.info("Training starten...")
    best_val_f1 = 0.0
    best_model_path = None
    
    train_losses = []
    val_losses = []
    train_accs = []
    val_accs = []
    val_f1s = []
    
    for epoch in range(args.epochs):
        logger.info(f"\nEpoch {epoch+1}/{args.epochs}")
        
        # Train
        train_loss, train_acc = train_epoch(
            model, train_loader, criterion_substrate, criterion_issues, optimizer, device
        )
        
        # Validate
        val_loss, val_acc, val_f1 = validate_epoch(
            model, val_loader, criterion_substrate, criterion_issues, device
        )
        
        # Scheduler step
        scheduler.step(val_loss)
        
        # Log metrics
        logger.info(f"Train Loss: {train_loss:.4f}, Train Acc: {train_acc:.4f}")
        logger.info(f"Val Loss: {val_loss:.4f}, Val Acc: {val_acc:.4f}, Val F1: {val_f1:.4f}")
        
        # Store metrics
        train_losses.append(train_loss)
        val_losses.append(val_loss)
        train_accs.append(train_acc)
        val_accs.append(val_acc)
        val_f1s.append(val_f1)
        
        # Save best model
        if val_f1 > best_val_f1:
            best_val_f1 = val_f1
            best_model_path = os.path.join(args.output_dir, 'levelai_vision_model.pth')
            
            torch.save(model.state_dict(), best_model_path)
            logger.info(f"Nieuw best model opgeslagen: {best_model_path}")
            
            # Sla ook training config op
            config = {
                'epoch': epoch + 1,
                'best_val_f1': best_val_f1,
                'best_val_acc': val_acc,
                'model_architecture': 'LevelAIModel',
                'backbone': 'efficientnet_b0',
                'substrate_classes': ['gipsplaat', 'beton', 'bestaand'],
                'issue_classes': ['scheuren', 'vocht'],
                'training_date': datetime.now().isoformat()
            }
            
            config_path = os.path.join(args.output_dir, 'training_config.json')
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
    
    # Training plots
    logger.info("Training plots opslaan...")
    save_training_plots(train_losses, val_losses, train_accs, val_accs, val_f1s, args.output_dir)
    
    # Final evaluation
    logger.info("\nFinal evaluation op test set...")
    test_loss, test_acc, test_f1 = validate_epoch(
        model, test_loader, criterion_substrate, criterion_issues, device
    )
    
    logger.info(f"Test Results:")
    logger.info(f"  Substrate Accuracy: {test_acc:.4f}")
    logger.info(f"  Issues F1 Score: {test_f1:.4f}")
    
    # Sla final results op
    final_results = {
        'test_substrate_accuracy': test_acc,
        'test_issues_f1': test_f1,
        'best_val_f1': best_val_f1,
        'total_epochs': args.epochs,
        'model_path': best_model_path
    }
    
    results_path = os.path.join(args.output_dir, 'final_results.json')
    with open(results_path, 'w') as f:
        json.dump(final_results, f, indent=2)
    
    logger.info(f"\nTraining voltooid!")
    logger.info(f"Best model opgeslagen: {best_model_path}")
    logger.info(f"Best validation F1: {best_val_f1:.4f}")
    logger.info(f"Test substrate accuracy: {test_acc:.4f}")
    
    # Check acceptatie criteria
    if test_acc > 0.7:
        logger.info("✅ Acceptatie criterium gehaald: Substrate accuracy > 70%")
    else:
        logger.warning("⚠️ Acceptatie criterium niet gehaald: Substrate accuracy < 70%")
    
    if test_f1 > 0.5:
        logger.info("✅ Issues F1 score acceptabel")
    else:
        logger.warning("⚠️ Issues F1 score laag, overweeg meer training data")

if __name__ == "__main__":
    main()
