import os
import uuid
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from supabase import create_client, Client
from typing import Dict, Any

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env file")

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
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Auth Header")
    
    token = authorization.split(" ")[1]
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
    
    safe_name = agent_name.lower().strip().replace(' ', '-')
    slug = f"{safe_name}-{user_id[:8]}"  

    try:
        agent_data = {
            "owner_id": user_id, 
            "slug": slug,
            "name": agent_name,
            "description": description,
            "is_public": True
        }
        
        existing_agent = supabase.table("agents").select("id").eq("slug", slug).execute()
        
        agent_id = None
        
        if existing_agent.data and len(existing_agent.data) > 0:
            print(f"Agent exists ({slug}), updating metadata...")
            agent_id = existing_agent.data[0]["id"]
            
            supabase.table("agents").update({
                "name": agent_name,
                "description": description
            }).eq("id", agent_id).execute()
            
        else:
            print(f"Creating new Agent ({slug})...")
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
        
        try:
            supabase.table("versions").insert(version_data).execute()
        except Exception as e:
            if "duplicate key" in str(e) or "unique constraint" in str(e):
                print(f"Version {version} already exists. Updating...")
                supabase.table("versions").update(version_data).eq("agent_id", agent_id).eq("version", version).execute()
            else:
                raise e
        
        return {
            "status": "published",
            "agent_id": agent_id,
            "slug": slug,
            "version": version,
            "url": f"https://charm.ai/agents/{slug}" 
        }

    except Exception as e:
        print(f"Database Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)