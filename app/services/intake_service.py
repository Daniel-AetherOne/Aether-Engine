import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Tuple
from fastapi import UploadFile, HTTPException
import shutil
import logging

class IntakeService:
    """Service for handling intake form submissions and file uploads"""
    
    def __init__(self, upload_base_path: str = "data/uploads"):
        self.upload_base_path = Path(upload_base_path)
        self.upload_base_path.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
    
    def generate_lead_id(self) -> str:
        """Generate a unique lead ID"""
        return str(uuid.uuid4())
    
    def get_upload_directory(self, lead_id: str, tenant_id: str) -> Path:
        """Get the upload directory for a specific lead and tenant"""
        current_date = datetime.now()
        month_folder = current_date.strftime("%Y-%m")
        upload_dir = self.upload_base_path / tenant_id / month_folder / lead_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"Created upload directory for tenant {tenant_id}, lead {lead_id}: {upload_dir}")
        return upload_dir
    
    def validate_files(self, files: List[UploadFile]) -> None:
        """Validate uploaded files"""
        if not files:
            raise HTTPException(status_code=400, detail="At least one file must be uploaded")
        
        if len(files) > 5:
            raise HTTPException(status_code=400, detail="Maximum 5 files allowed")
        
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
        
        for file in files:
            if not file.filename:
                raise HTTPException(status_code=400, detail="Invalid filename")
            
            file_ext = Path(file.filename).suffix.lower()
            if file_ext not in allowed_extensions:
                raise HTTPException(
                    status_code=400, 
                    detail=f"File type {file_ext} not allowed. Allowed types: {', '.join(allowed_extensions)}"
                )
    
    async def save_files(self, files: List[UploadFile], lead_id: str, tenant_id: str) -> List[str]:
        """Save uploaded files and return list of saved filenames"""
        upload_dir = self.get_upload_directory(lead_id, tenant_id)
        saved_files = []
        
        for file in files:
            if file.filename:
                # Generate unique filename to avoid conflicts
                file_ext = Path(file.filename).suffix
                unique_filename = f"{uuid.uuid4()}{file_ext}"
                file_path = upload_dir / unique_filename
                
                # Save file
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                
                saved_files.append(unique_filename)
                self.logger.info(f"Saved file {unique_filename} for tenant {tenant_id}, lead {lead_id}")
        
        return saved_files
    
    def get_file_info(self, lead_id: str, tenant_id: str) -> Tuple[Path, List[Path]]:
        """Get upload directory and list of files for a lead and tenant"""
        upload_dir = self.upload_base_path
        current_date = datetime.now()
        month_folder = current_date.strftime("%Y-%m")
        lead_dir = upload_dir / tenant_id / month_folder / lead_id
        
        if not lead_dir.exists():
            return lead_dir, []
        
        files = list(lead_dir.glob("*"))
        return lead_dir, files
    
    def get_tenant_upload_stats(self, tenant_id: str) -> dict:
        """Get upload statistics for a specific tenant"""
        tenant_path = self.upload_base_path / tenant_id
        if not tenant_path.exists():
            return {"total_leads": 0, "total_files": 0, "total_size_mb": 0}
        
        total_leads = 0
        total_files = 0
        total_size = 0
        
        for month_dir in tenant_path.iterdir():
            if month_dir.is_dir():
                for lead_dir in month_dir.iterdir():
                    if lead_dir.is_dir():
                        total_leads += 1
                        for file_path in lead_dir.iterdir():
                            if file_path.is_file():
                                total_files += 1
                                total_size += file_path.stat().st_size
        
        return {
            "total_leads": total_leads,
            "total_files": total_files,
            "total_size_mb": round(total_size / (1024 * 1024), 2)
        }


