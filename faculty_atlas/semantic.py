"""Optional local semantic ranking; no LLM provider or query rewriting."""
import hashlib
import os

def rank(con,root,rows,statement):
    os.environ.setdefault('FASTEMBED_CACHE_PATH',str((root/'embedding-cache').resolve()))
    try:
        import numpy as np
        from .scout import embeddings as emb
        # fastembed imports lazily in the reused upstream embedding module.
        query=emb.embed_one(statement)
    except ImportError as exc:
        raise RuntimeError('Install local embeddings with uv sync --extra semantic') from exc
    for row in rows:
        text='\n'.join([row.get('interests_ai') or '',*(r['text'] for r in row['interests_source'])])
        if not text.strip():
            row['semantic_score']=None
            continue
        digest=hashlib.sha256(text.encode()).hexdigest()
        cached=con.execute('SELECT content_hash,embedding FROM semantic_embeddings WHERE professor_id=? AND model=?',(row['id'],emb._MODEL_NAME)).fetchone()
        if cached and cached['content_hash']==digest:
            vec=np.frombuffer(cached['embedding'],dtype=np.float32)
        else:
            vec=emb.embed_one(text)
            with con:
                con.execute('INSERT OR REPLACE INTO semantic_embeddings VALUES(?,?,?,?)',(row['id'],emb._MODEL_NAME,digest,vec.tobytes()))
        row['semantic_score']=float(np.dot(query,vec))
    return sorted(rows,key=lambda r: -(r['semantic_score'] if r['semantic_score'] is not None else -2))
