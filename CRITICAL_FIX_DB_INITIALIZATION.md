# Critical Fix: Database Initialization at Module Import

## Problem
The system was not returning responses and couldn't see the database because of **module-level database initialization** that was causing startup failures.

## Root Cause
Two files were calling `get_db_service()` at module import time (when the file is first imported):

1. **`app/services/rag_service.py`** (line 6):
   ```python
   db_service = get_db_service()  # ❌ Called at import time
   ```

2. **`app/services/embedding_service.py`** (line 14):
   ```python
   db_service = get_db_service()  # ❌ Called at import time
   ```

### Why This Breaks Everything

When Python imports these modules:
1. The `get_db_service()` function is called immediately
2. This tries to connect to the database
3. If the database isn't ready, connection fails
4. The entire module fails to load
5. Any code that imports these modules crashes
6. The Flask app can't start
7. **Result: No responses, can't see DB**

## Fix Applied

### 1. Fixed `app/services/rag_service.py`
- ✅ Removed module-level `db_service = get_db_service()`
- ✅ Changed `query_semantic_memory()` to call `get_db_service()` inside the function (lazy initialization)
- ✅ Updated `RAGService` class to use lazy initialization with `_get_db()` method

### 2. Fixed `app/services/embedding_service.py`
- ✅ Removed module-level `db_service = get_db_service()`
- ✅ Updated `EmbeddingService` class to use lazy initialization with `_get_db()` method
- ✅ Database connection now happens only when actually needed

## Impact

**Before Fix:**
- ❌ Service fails to start if DB isn't ready
- ❌ Import errors crash the application
- ❌ No responses from the system
- ❌ Can't see/access database

**After Fix:**
- ✅ Service starts even if DB connection fails initially
- ✅ Database connection happens only when needed
- ✅ Graceful error handling
- ✅ System can respond even if RAG/embeddings fail

## Verification

1. **Check logs for import errors:**
   ```bash
   docker compose logs inception-app | grep -i "import\|error\|failed"
   ```

2. **Verify service starts:**
   ```bash
   docker compose ps
   # Should show "Up" status
   ```

3. **Test database connection:**
   ```bash
   docker compose logs inception-app | grep -i "database\|db_service"
   # Should show successful connection messages
   ```

4. **Test RAG functionality:**
   - Send a message that should trigger RAG
   - Check logs for: `"RAG query returned X results"`
   - Should work without crashing

## Files Modified

1. ✅ `app/services/rag_service.py` - Removed module-level DB init
2. ✅ `app/services/embedding_service.py` - Removed module-level DB init

## Status: ✅ FIXED

The system should now start properly and handle database connections gracefully.

