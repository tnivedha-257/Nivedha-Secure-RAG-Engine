# -*- coding: utf-8 -*-
"""
Created on Wed Apr 22 22:47:18 2026

@author: NIVEDHA T
"""

import os
import re
import threading
from fastapi import FastAPI, HTTPException, UploadFile, File
from groq import Groq 
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import sqlite3
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import numpy as np
import faiss



from sentence_transformers import SentenceTransformer
from rag.chunker import DocChunker   #import class
#from rag.indexer import build_vector_index   #imports function
import requests

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware


from fastapi import UploadFile
import shutil
from pathlib import Path

#from rag.retriever_factory import get_retriever
'''
from rag.citation_validator import validate_citations
from rag.hallucination_control import apply_confidence_filter
from rag.permission_gate import check_external_access
'''
from utils.text_cleanerV1 import clean_text

from models.model_config import VECTOR_BACKEND, INDEX_PATH

# JWT Configuration
SECRET_KEY = "NIVEDHA"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

EMBEDDING_MODEL = SentenceTransformer("all-MiniLM-L6-v2")

VECTOR_INDEX = None

INDEX_READY = False  #Used if query is given before the vector rebuilding is not completed after the app starts 

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Fixed admin user
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "$2b$12$ECVcg15s4/xFXOJDBQsaJuoewNVIsvGa9/u6T6NM62GgfwhuC6iIy"  
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ADMIN_PASSWORD_HASH = pwd_context.hash(ADMIN_PASSWORD)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  
UPLOAD_FOLDER = os.path.join(BASE_DIR, "doc_ingestion")  
os.makedirs(UPLOAD_FOLDER, exist_ok=True)  

DB_FILE = "nivi_SQLite_DB.db"    
DB_PATH_FILE = os.path.join(BASE_DIR, DB_FILE) 

FAISS_INDEX_PATH = os.path.join(BASE_DIR, "faiss.index") #

FAISS_LOCK = threading.Lock()  

# In[] # FASTAPI SERVER

app = FastAPI(
    title="Nivedha RAG Sysrem",
    version="1.0.0",
    description="RAG with authentication, chunking, FAISS retrieval"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="FastAPI_Client"), name="static")

app.mount("/uploads", StaticFiles(directory=UPLOAD_FOLDER), name="uploads")   #uploaded files will be saved in doc_ingestion


# In[] 

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def authenticate_admin(username: str, password: str):
    if username == ADMIN_USERNAME and verify_password(password, ADMIN_PASSWORD_HASH):
        return {"username": username}  # returns user info for token
    return None


def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


# In[] Data Base Tables

def get_db():
    return sqlite3.connect(DB_PATH_FILE, check_same_thread=False)


def init_db():
    conn = get_db() #connect DB file 
    cursor = conn.cursor()

    # Users table (existing)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # NEW: Chunk metadata table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            faiss_id INTEGER,
            source TEXT NOT NULL,
            path TEXT,
            page INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

init_db()     #Database is initialized

'''
Explanation
faiss_id : 525
source   : "Unit 1 AI & Python Complete.pdf"  only file name is stored
path     : "D:/.../doc_ingestion/Unit 1 AI & Python Complete.pdf"
text     : "Artificial Intelligence is..."
page     : 7
created_at : timestamp

Each real chunk will look like
{
"source": "Unit 1 AI & Python Complete.pdf",
"text": "Artificial Intelligence is...",
"page": 7
}

After embedding, FAISS contains
FAISS ID --> vector(one chunk text)
'''

# In[]

def store_chunks_in_db(chunks, faiss_ids):
    conn = get_db()      #connect DB file 
    cursor = conn.cursor()

    for chunk, fid in zip(chunks, faiss_ids):
        cursor.execute("""
            INSERT INTO document_chunks
            (faiss_id, source, path, text, page, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (
            fid,
            chunk["source"],
            f"{UPLOAD_FOLDER}/{chunk['source']}",
            chunk["text"],
            chunk.get("page", 0)
        ))

    conn.commit()
    conn.close()


def get_next_faiss_id():   
    conn = get_db()     #connect DB file 
    cursor = conn.cursor()

    cursor.execute("SELECT MAX(faiss_id) FROM document_chunks")
    result = cursor.fetchone()[0]
    #fetchone() returns a tuple (max_value,)
    conn.close()

    if result is None:
        return 0     

    return result + 1


def fetch_chunks_by_faiss_ids(faiss_ids):

    conn = get_db()     #connect DB file 
    cursor = conn.cursor()

    placeholders = ",".join(["?"] * len(faiss_ids))
    query = f"""
        SELECT faiss_id, text, source, page
        FROM document_chunks
        WHERE faiss_id IN ({placeholders})
    """

    cursor.execute(query, faiss_ids)
    rows = cursor.fetchall()
    
    '''
    rows will be list of tuples as given below
    [
        (101, "text1", "file1.pdf", 2),
        (205, "text2", "file2.pdf", 5),
    ]
    '''
    conn.close()

    results = []
    #{ faiss_id → row_data }
    id_to_row = {
        row[0]: {
            "faiss_id": row[0],
            "text": row[1],
            "source": row[2],
            "page": row[3]
        }
        for row in rows
    }
    
    results = [id_to_row[fid] for fid in faiss_ids if fid in id_to_row]  #reorder to preserve FAISS order

    return results


def retrieve_relevant_chunks(query, top_k=5):
    global VECTOR_INDEX, EMBEDDING_MODEL, INDEX_READY

    if not INDEX_READY or VECTOR_INDEX is None:
        raise HTTPException(status_code=503, detail="Index is still building")   # raise HTTPException
    if EMBEDDING_MODEL is None:
        raise HTTPException(status_code=500, detail="Embedding model not loaded")
    # Encode query
    query_embedding = EMBEDDING_MODEL.encode([query])
    query_embedding = np.array(query_embedding).astype("float32")

    # FAISS search
    with FAISS_LOCK:
        distances, indices = VECTOR_INDEX.search(query_embedding, top_k)
    print("FAISS distances:", distances)
    print("FAISS indices:", indices)

    faiss_ids = [int(i) for i in indices[0] if i != -1]
    #To avoid potential crash in empty FAISS search
    if indices is None or len(indices[0]) == 0:
        return []

    # Fetch metadata from SQLite
    retrieved_chunks = fetch_chunks_by_faiss_ids(faiss_ids)

    return retrieved_chunks


def rebuild_faiss_index():
    global VECTOR_INDEX, EMBEDDING_MODEL, INDEX_READY

    with FAISS_LOCK:   

        INDEX_READY = False

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT faiss_id, text
            FROM document_chunks
            ORDER BY faiss_id
        """)

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            VECTOR_INDEX = None
            INDEX_READY = True
        
            if os.path.exists(FAISS_INDEX_PATH):
                os.remove(FAISS_INDEX_PATH)
        
            print("No documents found. FAISS cleared and file removed.")
            return

        texts = [row[1] for row in rows]
        ids = [row[0] for row in rows]

        embeddings = EMBEDDING_MODEL.encode(texts)
        embeddings = np.array(embeddings).astype("float32")

        dimension = embeddings.shape[1]

        base_index = faiss.IndexFlatL2(dimension)
        VECTOR_INDEX = faiss.IndexIDMap(base_index)

        VECTOR_INDEX.add_with_ids(
            embeddings,
            np.array(ids, dtype="int64")
        )

        INDEX_READY = True

        print(f"FAISS index rebuilt with {len(texts)} chunks.")
        
        faiss.write_index(VECTOR_INDEX, FAISS_INDEX_PATH)
        print("FAISS index saved to disk.")

# In[]

@app.on_event("startup")
def startup_event():
    print("Server started successfully")
    threading.Thread(target=rebuild_faiss_index).start()

# In[]

async def save_file(file: UploadFile):
    filename = Path(file.filename).name
    file_path = os.path.join(UPLOAD_FOLDER, filename)

    if os.path.exists(file_path):
        raise HTTPException(
            status_code=400,
            detail="File already exists. Please rename or delete the existing file."
        )

    with open(file_path, "wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            buffer.write(chunk)

    await file.seek(0)   # reset pointer (important)

    return file_path

# In[]

class UserRegister(BaseModel):
    username: str
    password: str

@app.post("/register")
def register(user: UserRegister):
    conn = get_db()
    cursor = conn.cursor()

    hashed_pw = hash_password(user.password)

    try:
        cursor.execute(
            "INSERT INTO users (username, hashed_password, created_at) VALUES (?, ?, ?)",
            (user.username, hashed_pw, datetime.now().isoformat())
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists")

    conn.close()
    return {"message": "User registered successfully"}


@app.post("/login")
@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    # --- Check hardcoded admin first ---
    if form_data.username == ADMIN_USERNAME and verify_password(form_data.password, ADMIN_PASSWORD_HASH):
        access_token = create_access_token(data={"sub": ADMIN_USERNAME})
        return {"access_token": access_token, "token_type": "bearer"}

    # --- Otherwise fallback to database users ---
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, hashed_password FROM users WHERE username = ?",
        (form_data.username,)
    )
    user = cursor.fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid credentials")

    user_id, username, hashed_password = user

    if not verify_password(form_data.password, hashed_password):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    access_token = create_access_token(data={"sub": username})
    return {"access_token": access_token, "token_type": "bearer"} 



@app.post("/upload")
async def upload_file(file: UploadFile = File(...),current_user: str = Depends(get_current_user)):   
    #registers the endpoint, upload → upload_file() in a routing table
    #Uses FAISS logic,SQLite logic, chunking logic
    #Single ingestion system. does chunking,embedding,FAISS update,DB storage

    global VECTOR_INDEX, EMBEDDING_MODEL

    file_path = await save_file(file)

    # Chunk documents
    chunker = DocChunker(doc_folder=UPLOAD_FOLDER)
    all_chunks = chunker.chunk_documents()

    # Only new file chunks
    new_chunks = [c for c in all_chunks if c["source"] == file.filename]

    if not new_chunks:
        return {"message": "No text extracted from document."}  
    #return the above to client which called this function as a JSON with message

    new_texts = [chunk["text"] for chunk in new_chunks]

    # Encode new chunks
    new_embeddings = EMBEDDING_MODEL.encode(new_texts)
    new_embeddings = np.array(new_embeddings).astype("float32")

    # Determine FAISS ids using SQLite
    start_id = get_next_faiss_id()
    faiss_ids = list(range(start_id, start_id + len(new_embeddings)))

   
    #Update FAISS FIRST
    with FAISS_LOCK:
        if VECTOR_INDEX is None:
            dimension = new_embeddings.shape[1]
            base_index = faiss.IndexFlatL2(dimension)
            VECTOR_INDEX = faiss.IndexIDMap(base_index)
    
        VECTOR_INDEX.add_with_ids(
            new_embeddings,
            np.array(faiss_ids, dtype="int64")
        )
        faiss.write_index(VECTOR_INDEX, FAISS_INDEX_PATH)            
        #Store metadata AFTER FAISS succeeds.
        store_chunks_in_db(new_chunks, faiss_ids)
        #return the following to client which called this function as a JSON with message
        return {
            "message": f"{file.filename} uploaded and indexed successfully",
            "chunks_added": len(new_chunks)
        }
        
@app.post("/admin/upload-document")
async def upload_document(
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user)
):
    try:
        return await upload_file(file)   # normal flow
    except Exception as e:
        # Always return a JSON with 'message' so client alert works
        return {"message": f"Upload failed: {str(e)}"}

# In[]  Admin API

@app.delete("/admin/delete-document")
def delete_document(filename: str,current_user: str = Depends(get_current_user)):

    filename = filename.strip()  

    conn = get_db()
    cursor = conn.cursor()

    # Check existence
    cursor.execute(
        "SELECT faiss_id FROM document_chunks WHERE TRIM(source)=?",
        (filename,)
    )

    rows = cursor.fetchall()

    if not rows:
        conn.close()
        raise HTTPException(status_code=404, detail="Document not found")

    cursor.execute(
        "DELETE FROM document_chunks WHERE TRIM(source)=?",
        (filename,)
    )

    conn.commit()
    conn.close()

    # Delete physical file
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    # Rebuild FAISS in background
    rebuild_faiss_index()
    
    '''
    #used for debugging. Found & was not converted to %26
    print(f"Incoming filename: [{filename}]")

    cursor.execute("SELECT DISTINCT source FROM document_chunks")
    all_sources = cursor.fetchall()

    print("DB sources:")
    for s in all_sources:
        print(f"[{s[0]}]")
    '''
    
    return {"message": f"{filename} removed from index"}



@app.delete("/admin/delete-folder")
def delete_folder(folder: str,current_user: str = Depends(get_current_user)):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM document_chunks WHERE source LIKE ?",
        (f"%{folder}%",)
    )
    
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    rebuild_faiss_index()

    return {"message": f"{folder} folder removed from index"}



@app.delete("/admin/reset-index")
def reset_index(confirm: bool = False,current_user: str = Depends(get_current_user)):    
    #confirm button will be displayed
    if not confirm:
        return {"message": "Set confirm=true to reset index"}

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM document_chunks")
    # delete ALL rows in document_chunks table

    conn.commit()
    conn.close()
  
    #delete the files in the UPLOAD dir doc_ingestion folder
    shutil.rmtree(UPLOAD_FOLDER)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    rebuild_faiss_index()

    return {"message": "Index reset completed"}



@app.get("/admin/list-documents")
def list_documents(current_user: str = Depends(get_current_user)):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT source, COUNT(*) as chunks
        FROM document_chunks
        GROUP BY source
    """)

    rows = cursor.fetchall()
    conn.close()

    docs = [{"document": r[0], "chunks": r[1]} for r in rows]

    return {"documents": docs}


# In[]

ALLOWED_MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile", 
    "mixtral-8x7b-32768",
    "allam-2-7b",
    "openai/gpt-oss-20B"
]

DEFAULT_MODEL = "allam-2-7b"

groq_client = Groq(api_key=os.getenv("Nivedha_Groq_API_Key"))  #API key is got from environment variable


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: Optional[str] = None
    messages: List[Message]
    temperature: Optional[float] = 0.7
    reference_style: Optional[str] = "both"

def contains_tamil(text: str) -> bool:
    return bool(re.search(r'[\u0B80-\u0BFF]', text))

# In[]

def has_retrieved_context(messages: List[Message]) -> bool:
    """
    Detects whether WebUI injected retrieved document context.
    Looks for common RAG markers like 'Source', 'Page', etc.
    """
    for m in messages:
        content = m.content.lower()
        if "source:" in content or "page" in content or "document:" in content:
            return True
    return False


def refusal_response(reason: str):
    return {
        "id": "chatcmpl-local",
        "object": "chat.completion",
        "created": int(datetime.now().timestamp()),
        "model": "control-layer",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": reason
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
    }


def apply_reference_style(assistant_message, references_map, style):
    
    # REMOVE existing inline references first
    assistant_message = re.sub(r"\([^)]*\.pdf[^)]*\)", "", assistant_message, flags=re.IGNORECASE)
    # REMOVE existing bibliography
    assistant_message = re.sub(r"References:.*", "", assistant_message, flags=re.IGNORECASE | re.DOTALL)

    # INLINE ONLY
    if style == "inline":
        for doc_marker, ref_text in references_map.items():
            assistant_message = assistant_message.replace(
                doc_marker, f"({ref_text})"
            )
    
    # LIST ONLY
    elif style == "list":
        used_markers = re.findall(r"\[Doc\d+\]", assistant_message)
    
        assistant_message = re.sub(r"\[Doc\d+\]", "", assistant_message)   # REMOVE INLINE MARKERS
    
        refs_list = []
        for doc_marker in used_markers:
            if doc_marker in references_map:
                ref = references_map[doc_marker]
                if ref not in refs_list:
                    refs_list.append(ref)
                    
        if not refs_list:
            refs_list = list(references_map.values())
        
        if refs_list:
            assistant_message = assistant_message.replace("References:", "")
            assistant_message += "<br><br><br><b>References:</b><br>"
            assistant_message += "<br>".join(f"- {r}" for r in refs_list)
    
    # BOTH
    elif style == "both":
        used_markers = re.findall(r"\[Doc\d+\]", assistant_message)
    
        for doc_marker, ref_text in references_map.items():
            assistant_message = assistant_message.replace(
                doc_marker, f"({ref_text})"
            )
    
        refs_list = []
        for doc_marker in used_markers:
            if doc_marker in references_map:
                ref = references_map[doc_marker]
                if ref not in refs_list:
                    refs_list.append(ref)
    
        if refs_list:
            assistant_message += "<br><br><br><b>References:</b><br>"
            assistant_message += "<br>".join(f"- {r}" for r in refs_list)
    
    # NONE
    elif style == "none":
        assistant_message = assistant_message.replace("References:", "")

    return assistant_message


def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

       

@app.get("/protected")
def protected_route(current_user: str = Depends(get_current_user)):
    return {"message": f"Hello {current_user}"}     

#root endpoint
@app.get("/")
def serve_ui():
    return FileResponse("FastAPI_Client/index.html")

@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": model,
                "object": "model",
                "created": 0,
                "owned_by": "groq"
            }
            for model in ALLOWED_MODELS
        ]
    }


@app.post("/v1/chat/completions")
async def chat_completion(request: ChatRequest):

    selected_model = request.model or DEFAULT_MODEL

    if selected_model not in ALLOWED_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{selected_model}' is not allowed."
        )

    user_message = request.messages[-1].content
    retrieved_chunks = retrieve_relevant_chunks(user_message, top_k=5)  # returns list of dicts
    print("Number of chunks:", len(retrieved_chunks))    
    context_parts = []
    for i, c in enumerate(retrieved_chunks, start=1):
        clean_text = c["text"].strip()
    
        context_parts.append(
            f"""
            [Doc{i}]
            Document: {c['source']}
            Page: {c['page']}
            Content:
            {clean_text}
            """
        )
            
    '''
    for i, c in enumerate(retrieved_chunks, start=1):
        clean_text = c['text'].replace("[", "").replace("]", "")
        context_parts.append(
            f"[Doc{i}] {clean_text}"
            #f"Source [Doc{i}] | Document: {c['source']} | Page: {c['page']}\n{clean_text}"
        )
    '''
    
    
    rag_context = "\n\n".join(context_parts)
    
    references_map = {}
    for i, c in enumerate(retrieved_chunks, start=1):
        references_map[f"[Doc{i}]"] = (
            f"<a href='/uploads/{c['source']}#page={c['page']}' target='_blank'>"
            f"{c['source']} — Page {c['page']}</a>"
        )     
        

    if not retrieved_chunks:
        print("🚫 BLOCKED BEFORE LLM CALL — No retrieved evidence detected.")
        return refusal_response(
            "The answer is not found in the local documents provided by Nivedha."
        )

    #Language handling
    if contains_tamil(user_message):
        system_prompt = "You are a helpful AI assistant. Always respond only in Tamil."
    else:
        system_prompt = "You are a helpful AI assistant. Answer ONLY using the provided document context. If the answer is not in the context, say the information is not available in the documents."

    style = request.reference_style or "both"  

    if style == "none":
        citation_instruction = "STRICTLY DO NOT include any citations or markers."
        rules_text = """
- Do NOT include any citation markers like [Doc1].
- Do NOT include any References section.
"""
    elif style == "inline":
        citation_instruction = "Include inline citation markers like [Doc1]."
        rules_text = """
- Use ONLY the markers [Doc1], [Doc2], etc.
- Do NOT write document names yourself.
- Do NOT invent citations.
- Do NOT include any References section.
"""
    elif style == "list":
        citation_instruction = "STRICTLY DO NOT include any inline citation markers like [Doc1]."
        rules_text = """
- Do NOT include any inline citation markers like [Doc1].
- Do NOT write document names yourself.
- Do NOT invent citations.
- Do NOT include any References section.
"""
    elif style == "both":
        citation_instruction = "STRICTLY include citation markers like [Doc1], [Doc2] in every factual sentence."
        rules_text = """
- Use ONLY the markers [Doc1], [Doc2], etc.
- Do NOT write document names yourself.
- Do NOT invent citations.
"""

    #Inject retrieved context as system message
    system_prompt = f"""
    You are a document-grounded AI assistant.
    
    Answer the question ONLY using the provided context.
    
    {citation_instruction}
    
    Rules:
    {rules_text}
    
    If the answer is not present in the context, say the information is not available.
    
    Context:
    {rag_context}
    """
    
    '''
    #old prompt where citations were not displayed as per check box selection
    system_prompt = f"""
    You are a document-grounded AI assistant.
    
    Answer the question ONLY using the provided context.
    
    Citation Rules:
    1. Every factual statement MUST include a citation marker.
    2. Use ONLY the markers [Doc1], [Doc2], etc.
    3. Copy the marker EXACTLY as written.
    4. Do NOT write document names yourself.
    5. Do NOT invent citations.
    
    If the answer is not present in the context, say the information is not available.
    
    Context:
    {rag_context}
    """
    '''
  
    #final_messages = [{"role": "system", "content": system_prompt}] 
    final_messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]   
    
    
    
    for m in request.messages:
        final_messages.append({
            "role": m.role.lower(),
            "content": m.content
        })
    print("MODEL:", selected_model)
    print("SENDING TO GROQ:", final_messages) 

    try:
        response = groq_client.chat.completions.create(
            model=selected_model,
            messages=final_messages,
            temperature=0.7,
        )

        assistant_message = response.choices[0].message.content
    
        if assistant_message is None:
            assistant_message = ""
        
        # Determine reference style: inline, list, or both
        #style = request.dict().get("reference_style", "both").lower()
        style = (request.reference_style or "both").lower()
        if style not in ["inline", "list", "both", "none"]:
            style = "both"
        assistant_message = apply_reference_style(assistant_message, references_map, style)
  
               
    except Exception as e:
        print("FULL ERROR:", e)
        raise
    
    
    return {
        "id": "chatcmpl-local",
        "object": "chat.completion",
        "created": int(datetime.now().timestamp()),
        "model": selected_model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": assistant_message
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
    }




