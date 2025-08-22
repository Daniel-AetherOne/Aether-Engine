from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
import uuid

class QuoteItem(BaseModel):
    """Individual item in a quote"""
    description: str = Field(..., description="Item description")
    quantity: float = Field(..., gt=0, description="Quantity")
    unit_price: float = Field(..., ge=0, description="Price per unit")
    total: float = Field(..., ge=0, description="Total price for this item")
    
    @property
    def calculated_total(self) -> float:
        """Calculate total based on quantity and unit price"""
        return self.quantity * self.unit_price

class Quote(BaseModel):
    """Database model for storing quotes"""
    quote_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique quote identifier")
    lead_id: str = Field(..., description="Lead identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    customer_name: str = Field(..., description="Customer name")
    customer_email: str = Field(..., description="Customer email")
    project_description: str = Field(..., description="Project description")
    items: List[QuoteItem] = Field(..., description="List of quote items")
    subtotal: float = Field(..., description="Subtotal before tax")
    tax_rate: float = Field(0.21, description="Tax rate (default 21%)")
    tax_amount: float = Field(..., description="Tax amount")
    total: float = Field(..., description="Total amount including tax")
    notes: Optional[str] = Field(None, description="Additional notes")
    created_date: datetime = Field(default_factory=datetime.utcnow, description="Quote creation date")
    status: str = Field("draft", description="Quote status")
    pdf_path: Optional[str] = Field(None, description="Path to generated PDF")
    
    @property
    def calculated_subtotal(self) -> float:
        """Calculate subtotal from items"""
        return sum(item.total for item in self.items)
    
    @property
    def calculated_tax_amount(self) -> float:
        """Calculate tax amount"""
        return self.calculated_subtotal * self.tax_rate
    
    @property
    def calculated_total(self) -> float:
        """Calculate total including tax"""
        return self.calculated_subtotal + self.tax_amount

class QuoteRequest(BaseModel):
    """Request model for creating a quote"""
    lead_id: str = Field(..., description="Lead identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    customer_name: str = Field(..., description="Customer name")
    customer_email: str = Field(..., description="Customer email")
    project_description: str = Field(..., description="Project description")
    items: List[QuoteItem] = Field(..., description="List of quote items")
    notes: Optional[str] = Field(None, description="Additional notes")

class QuoteResponse(BaseModel):
    """Response model for quote creation"""
    quote_id: str = Field(..., description="Unique quote identifier")
    lead_id: str = Field(..., description="Lead identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    customer_name: str = Field(..., description="Customer name")
    customer_email: str = Field(..., description="Customer email")
    project_description: str = Field(..., description="Project description")
    items: List[QuoteItem] = Field(..., description="List of quote items")
    subtotal: float = Field(..., description="Subtotal before tax")
    tax_rate: float = Field(0.21, description="Tax rate (default 21%)")
    tax_amount: float = Field(..., description="Tax amount")
    total: float = Field(..., description="Total amount including tax")
    notes: Optional[str] = Field(None, description="Additional notes")
    created_date: datetime = Field(..., description="Quote creation date")
    status: str = Field("draft", description="Quote status")
    pdf_path: Optional[str] = Field(None, description="Path to generated PDF")
    
    @property
    def calculated_subtotal(self) -> float:
        """Calculate subtotal from items"""
        return sum(item.total for item in self.items)
    
    @property
    def calculated_tax_amount(self) -> float:
        """Calculate tax amount"""
        return self.calculated_subtotal * self.tax_rate
    
    @property
    def calculated_total(self) -> float:
        """Calculate total including tax"""
        return self.calculated_subtotal + self.tax_amount

class QuoteUpdate(BaseModel):
    """Model for updating a quote"""
    customer_name: Optional[str] = Field(None, description="Customer name")
    customer_email: Optional[str] = Field(None, description="Customer email")
    project_description: Optional[str] = Field(None, description="Project description")
    items: Optional[List[QuoteItem]] = Field(None, description="List of quote items")
    notes: Optional[str] = Field(None, description="Additional notes")
    status: Optional[str] = Field(None, description="Quote status")
