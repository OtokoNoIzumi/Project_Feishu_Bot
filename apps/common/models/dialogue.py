from typing import List, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field

class DialogueMessage(BaseModel):
    id: str = Field(..., description="Unique message ID")
    role: Literal['user', 'assistant']
    title: Optional[str] = Field(None, description="Short title for message card")
    subtitle: Optional[str] = Field(None, description="Subtitle with energy/weight info")
    content: str
    timestamp: datetime
    attachments: List[str] = Field(default_factory=list, description="List of file URIs")
    linked_card_id: Optional[str] = Field(None, description="ID of the ResultCard stimulated by this message")

class Dialogue(BaseModel):
    id: str = Field(..., description="Unique dialogue ID (UUID)")
    user_id: str
    title: str = Field(..., description="Dialogue title or summary")
    user_title: Optional[str] = Field(None, description="Custom user-defined title")
    messages: List[DialogueMessage] = Field(default_factory=list)
    card_ids: List[str] = Field(default_factory=list, description="List of ResultCard IDs created within this dialogue")
    created_at: datetime
    updated_at: datetime

class ResultCard(BaseModel):
    id: str = Field(..., description="Unique card ID (UUID)")
    dialogue_id: str
    user_id: Optional[str] = None
    mode: Literal['diet', 'keep']
    user_title: Optional[str] = Field(None, description="Custom user-defined title")
    source_user_note: Optional[str] = Field(None, description="Original user input for analysis")
    image_uris: List[str] = Field(default_factory=list, description="Original image file URIs")
    image_hashes: List[str] = Field(default_factory=list)
    
    versions: List[dict] = Field(default_factory=list, description="Analysis result versions")
    current_version: int = 1
    
    status: Literal['analyzing', 'draft', 'saved', 'error'] = 'draft'
    saved_record_id: Optional[str] = None
    
    created_at: datetime
    updated_at: datetime
    
    is_demo: bool = False
