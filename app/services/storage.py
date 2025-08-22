import os
import boto3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from botocore.exceptions import ClientError, NoCredentialsError
import logging

logger = logging.getLogger(__name__)

class Storage(ABC):
    """Abstracte Storage interface voor bestandsopslag."""
    
    @abstractmethod
    def save_bytes(self, tenant_id: str, key: str, data: bytes) -> str:
        """
        Sla bytes op onder de gegeven key voor een tenant.
        
        Args:
            tenant_id: Tenant identifier
            key: Bestandssleutel (pad)
            data: Bestandsdata als bytes
            
        Returns:
            De opgeslagen key
        """
        pass
    
    @abstractmethod
    def public_url(self, tenant_id: str, key: str) -> str:
        """
        Genereer een publieke URL voor een bestand.
        
        Args:
            tenant_id: Tenant identifier
            key: Bestandssleutel
            
        Returns:
            Publieke URL naar het bestand
        """
        pass
    
    @abstractmethod
    def exists(self, tenant_id: str, key: str) -> bool:
        """
        Controleer of een bestand bestaat.
        
        Args:
            tenant_id: Tenant identifier
            key: Bestandssleutel
            
        Returns:
            True als het bestand bestaat, anders False
        """
        pass
    
    @abstractmethod
    def delete(self, tenant_id: str, key: str) -> bool:
        """
        Verwijder een bestand.
        
        Args:
            tenant_id: Tenant identifier
            key: Bestandssleutel
            
        Returns:
            True als verwijdering succesvol was, anders False
        """
        pass


class LocalStorage(Storage):
    """Lokale bestandsopslag implementatie."""
    
    def __init__(self, base_path: str = "data"):
        """
        Initialiseer LocalStorage.
        
        Args:
            base_path: Basis pad voor bestandsopslag
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def save_bytes(self, tenant_id: str, key: str, data: bytes) -> str:
        """Sla bytes op in lokale bestandsstructuur."""
        # Maak tenant-specifieke directory structuur
        file_path = self.base_path / tenant_id / key
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Schrijf bestand
        with open(file_path, 'wb') as f:
            f.write(data)
        
        logger.info(f"Bestand opgeslagen: {file_path}")
        return key
    
    def public_url(self, tenant_id: str, key: str) -> str:
        """Genereer lokale bestandspad URL."""
        # Voor lokale opslag, retourneer een relatief pad dat door de webserver kan worden geserveerd
        return f"/files/{tenant_id}/{key}"
    
    def exists(self, tenant_id: str, key: str) -> bool:
        """Controleer of bestand bestaat in lokale opslag."""
        file_path = self.base_path / tenant_id / key
        return file_path.exists()
    
    def delete(self, tenant_id: str, key: str) -> bool:
        """Verwijder bestand uit lokale opslag."""
        try:
            file_path = self.base_path / tenant_id / key
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Bestand verwijderd: {file_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Fout bij verwijderen van bestand {key}: {e}")
            return False


class S3Storage(Storage):
    """Amazon S3 bestandsopslag implementatie."""
    
    def __init__(self, bucket: str, region: str = "eu-west-1", 
                 aws_access_key_id: Optional[str] = None, 
                 aws_secret_access_key: Optional[str] = None):
        """
        Initialiseer S3Storage.
        
        Args:
            bucket: S3 bucket naam
            region: AWS regio
            aws_access_key_id: AWS access key (optioneel, gebruikt credentials uit environment)
            aws_secret_access_key: AWS secret key (optioneel, gebruikt credentials uit environment)
        """
        self.bucket = bucket
        self.region = region
        
        # S3 client initialiseren
        session_kwargs = {}
        if aws_access_key_id and aws_secret_access_key:
            session_kwargs.update({
                'aws_access_key_id': aws_access_key_id,
                'aws_secret_access_key': aws_secret_access_key
            })
        
        self.s3_client = boto3.client('s3', region_name=region, **session_kwargs)
        
        # Controleer of bucket bestaat
        try:
            self.s3_client.head_bucket(Bucket=bucket)
            logger.info(f"S3 bucket {bucket} is toegankelijk")
        except (ClientError, NoCredentialsError) as e:
            logger.error(f"Kan geen toegang krijgen tot S3 bucket {bucket}: {e}")
            raise
    
    def save_bytes(self, tenant_id: str, key: str, data: bytes) -> str:
        """Upload bytes naar S3."""
        # S3 key met tenant prefix
        s3_key = f"{tenant_id}/{key}"
        
        try:
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=data,
                ContentType=self._get_content_type(key)
            )
            logger.info(f"Bestand geüpload naar S3: {s3_key}")
            return key
        except Exception as e:
            logger.error(f"Fout bij uploaden naar S3: {e}")
            raise RuntimeError(f"S3 upload mislukt: {e}")
    
    def public_url(self, tenant_id: str, key: str) -> str:
        """Genereer publieke S3 URL."""
        # Voor MVP: unsigned URL (kan later worden uitgebreid met signed URLs)
        s3_key = f"{tenant_id}/{key}"
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{s3_key}"
    
    def exists(self, tenant_id: str, key: str) -> bool:
        """Controleer of bestand bestaat in S3."""
        try:
            s3_key = f"{tenant_id}/{key}"
            self.s3_client.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            logger.error(f"Fout bij controleren van S3 object: {e}")
            return False
        except Exception as e:
            logger.error(f"Onverwachte fout bij controleren van S3 object: {e}")
            return False
    
    def delete(self, tenant_id: str, key: str) -> bool:
        """Verwijder bestand uit S3."""
        try:
            s3_key = f"{tenant_id}/{key}"
            self.s3_client.delete_object(Bucket=self.bucket, Key=s3_key)
            logger.info(f"Bestand verwijderd uit S3: {s3_key}")
            return True
        except Exception as e:
            logger.error(f"Fout bij verwijderen uit S3: {e}")
            return False
    
    def _get_content_type(self, key: str) -> str:
        """Bepaal content type op basis van bestandsextensie."""
        ext = Path(key).suffix.lower()
        content_types = {
            '.html': 'text/html',
            '.pdf': 'application/pdf',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.txt': 'text/plain',
            '.json': 'application/json'
        }
        return content_types.get(ext, 'application/octet-stream')


def get_storage() -> Storage:
    """
    Factory functie om de juiste storage backend te retourneren.
    
    Returns:
        Storage implementatie gebaseerd op STORAGE_BACKEND environment variable
    """
    storage_backend = os.getenv("STORAGE_BACKEND", "local").lower()
    
    if storage_backend == "s3":
        bucket = os.getenv("S3_BUCKET")
        region = os.getenv("S3_REGION", "eu-west-1")
        aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        
        if not bucket:
            raise ValueError("S3_BUCKET environment variable is vereist voor S3 storage")
        
        return S3Storage(
            bucket=bucket,
            region=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key
        )
    
    elif storage_backend == "local":
        base_path = os.getenv("LOCAL_STORAGE_PATH", "data")
        return LocalStorage(base_path=base_path)
    
    else:
        raise ValueError(f"Onbekende storage backend: {storage_backend}")
