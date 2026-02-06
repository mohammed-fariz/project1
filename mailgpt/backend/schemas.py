from pydantic import BaseModel, EmailStr, Field


class EmailRequest(BaseModel):
    to: EmailStr
    subject: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1)
