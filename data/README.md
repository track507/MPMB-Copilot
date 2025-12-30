# Data Directory

This directory contains local data files that are NOT committed to git.

## Structure

- **mpmb_source/** - Clone of MPMB Character Sheet repository
  - Clone from: <https://github.com/morepurplemorebetter/MPMBs-Character-Record-Sheet>
  - Not committed (too large, external dependency)

- **chunked_output/** - Generated chunks from ``chunk_mpmb.py``
  - JSON files with code chunks for RAG indexing
  - Regenerate with: ``python scripts/chunk_mpmb.py``

- **adobe_docs/** - Adobe JavaScript documentation
  - Scraped/downloaded PDF reference docs
  - Not committed (can re-download)

- **index_cache/** - Cached embeddings
  - Vector embeddings for faster indexing
  - Regenerate when needed

- **uploads/** - User-uploaded files
  - Runtime user uploads (session-specific)
  - Not committed (user data)

## Setup

To set up this directory:

```bash
# Clone MPMB repository
cd data
git clone https://github.com/morepurplemorebetter/MPMBs-Character-Record-Sheet.git mpmb_source

# Create other directories
mkdir chunked_output adobe_docs index_cache uploads

# Run chunking script
cd ..
python scripts/chunk_mpmb.py
```
