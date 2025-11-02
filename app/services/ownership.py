# app/services/ownership.py
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

def assert_lead_belongs_to_user(db: Session, lead_id: int, user_id: int):
    # Pas aan naar jouw Lead model; voorlopig “happy path”
    # lead = db.query(Lead).filter(Lead.id==lead_id, Lead.user_id==user_id).first()
    lead = True  # TODO: vervangen door echte query
    if not lead:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lead is not yours")
