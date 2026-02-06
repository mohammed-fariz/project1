from google.oauth2.credentials import Credentials
from fastapi import HTTPException

def get_credentials(token: str):
    try:
        credentials = Credentials(token)
        return credentials
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid OAuth Token")
