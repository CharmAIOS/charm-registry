import os
import uuid
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from supabase import create_client, Client
from typing import Dict, Any

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in .env file")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="Charm Registry API")


class RepoInfo(BaseModel):
    url: str
    branch: str
    commit: str

class PushPayload(BaseModel):
    uac: Dict[str, Any]  
    repo: RepoInfo


async def verify_token(authorization: str = Header(...)):
    """
    驗證 Bearer Token 是否為有效的 UUID。
    MVP 階段：直接將 Token 視為 User ID。
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Auth Header")
    
    token = authorization.split(" ")[1]

    try:
        uuid.UUID(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Token must be a valid UUID")
    
    return token


@app.get("/")
def health_check():
    return {"status": "ok", "service": "Charm Registry"}

@app.post("/v1/agents")
def register_agent(payload: PushPayload, user_id: str = Depends(verify_token)):
    uac = payload.uac
    persona = uac.get("persona", {})
    
    agent_name = persona.get("name", "Untitled Agent")
    description = persona.get("description", "")
    version = uac.get("version", "0.0.1")
    
    slug = f"{agent_name.lower().replace(' ', '-')}-{str(uuid.uuid4())[:8]}"

    try:
        agent_data = {
            "owner_id": user_id, 
            "slug": slug,
            "name": agent_name,
            "description": description,
            "is_public": True
        }
        
        res_agent = supabase.table("agents").insert(agent_data).execute()
        
        if not res_agent.data:
            raise HTTPException(status_code=500, detail="Failed to create agent record")
            
        agent_id = res_agent.data[0]["id"]
        
        version_data = {
            "agent_id": agent_id,
            "version": version,
            "uac": uac,
            "repo_url": payload.repo.url,
            "commit_hash": payload.repo.commit,
            "branch": payload.repo.branch
        }
        
        supabase.table("versions").insert(version_data).execute()
        
        return {
            "status": "published",
            "agent_id": agent_id,
            "slug": slug,
            "url": f"https://charm.ai/agents/{slug}" 
        }

    except Exception as e:
        print(f"Database Error: {e}")
        if "duplicate key" in str(e):
             raise HTTPException(status_code=409, detail="Version already exists")
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
