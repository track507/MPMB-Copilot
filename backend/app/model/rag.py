"""RAG-related Pydantic models

This module defines Pydantic models for the RAG (Retrieval-Augmented Generation)
pipeline, which enhances LLM responses with relevant code examples from the MPMB
source repository.

The RAG pipeline flow:
1. Indexing Phase:
   - Parse MPMB source files into CodeChunk objects
   - Generate embeddings via EmbeddingRequest/Response
   - Store vectors in Qdrant for similarity search

2. Retrieval Phase:
   - Embed user query
   - Search vector database for similar code chunks
   - Return VectorSearchResult objects ranked by relevance

3. Generation Phase:
   - Assemble retrieved chunks into RAGContext
   - Inject context into LLM system prompt
   - Generate response with relevant code examples
   - Track retrieval performance via RetrievalMetadata

This approach ensures the copilot provides accurate, source-backed answers about
MPMB automation rather than hallucinating incorrect API usage.
"""
from typing import Optional, Any
from pydantic import BaseModel, Field

class CodeChunk(BaseModel):
	"""Represents a semantic chunk of code extracted during indexing.

	Created during the indexing pipeline when MPMB source files are split into
	overlapping segments for embedding and retrieval. Each chunk represents a
	cohesive unit of code (typically a function, class, or logical section).

	The chunking strategy balances:
	- Semantic completeness (keeping related code together)
	- Context window limits (chunks must fit in embedding model)
	- Retrieval precision (smaller chunks = more targeted results)

	Attributes:
		content: The actual code text for this chunk. Typically 500-2000 characters
			depending on chunking configuration. Includes comments and context.
		source_file: Relative path to the source file this chunk came from,
			e.g., "src/common functions/SpellsList.js" or "additional content/Races.js"
		chunk_index: Zero-based index of this chunk within the source file.
			Used to reconstruct file order and handle overlapping chunks.
		start_line: Line number where this chunk begins in the source file (1-based).
			Useful for generating source links and displaying context.
		end_line: Line number where this chunk ends in the source file (1-based, inclusive).
			Together with start_line, defines the exact code location.
		metadata: Additional chunk metadata as a flexible dictionary. Common keys:
			{
				"function_name": "AddSpell",  # Extracted function/object name
				"chunk_type": "function",  # Type: function/class/comment/config
				"language": "javascript",  # Programming language
				"file_category": "spells",  # MPMB file category
				"has_comments": true,  # Whether chunk includes JSDoc
				"complexity": "medium",  # Estimated code complexity
				"api_references": ["SpellsList", "CurrentSpells"]  # Referenced APIs
			}

	Example:
		>>> chunk = CodeChunk(
		...     content='function AddSpell(spellObj) {\\n  SpellsList[spellObj.name] = spellObj;\\n  ...\\n}',
		...     source_file="src/common functions/SpellsList.js",
		...     chunk_index=3,
		...     start_line=45,
		...     end_line=62,
		...     metadata={
		...         "function_name": "AddSpell",
		...         "chunk_type": "function",
		...         "language": "javascript",
		...         "has_comments": True
		...     }
		... )

	Note:
		Chunks may overlap to preserve context at boundaries. For example, with
		200-character overlap, lines 55-62 of chunk_index=3 might also appear
		in lines 55-70 of chunk_index=4. This ensures function signatures aren't
		lost at chunk boundaries.

		Typical MPMB function sizes are 50-200 lines, so most functions fit
		within a single 1500-character chunk with full context.
	"""
	content: str = Field(
		...,
		description="Code text content for this chunk"
	)
	source_file: str = Field(
		...,
		description="Relative path to source file (e.g., 'src/common functions/SpellsList.js')"
	)
	chunk_index: int = Field(
		...,
		ge=0,
		description="Zero-based index of chunk within source file"
	)
	start_line: int = Field(
		...,
		ge=1,
		description="Starting line number in source file (1-based)"
	)
	end_line: int = Field(
		...,
		ge=1,
		description="Ending line number in source file (1-based, inclusive)"
	)
	metadata: dict[str, Any] = Field(
		default_factory=dict,
		description="Additional chunk metadata (function names, types, complexity, etc.)"
	)

class EmbeddingRequest(BaseModel):
	"""Request to generate vector embeddings from text.

	Sent to the embedding service to convert text (code chunks or user queries)
	into high-dimensional vector representations for semantic similarity search.

	The embedding model transforms text into a numerical vector where semantically
	similar texts have similar vector representations (measured by cosine similarity).

	Attributes:
		texts: List of text strings to embed. Can be code chunks during indexing
			or user queries during retrieval. Batch processing multiple texts
			together is more efficient than individual requests.
		model: Optional embedding model to use. If None, uses the default configured
			model. Common options:
			- "text-embedding-3-small": OpenAI, 1536 dimensions, fast and cheap
			- "text-embedding-3-large": OpenAI, 3072 dimensions, higher quality
			- "voyage-code-2": Voyage AI, optimized for code (recommended for MPMB)
			- Custom sentence-transformers models via Ollama

	Example:
		>>> # Batch embed multiple code chunks during indexing
		>>> request = EmbeddingRequest(
		...     texts=[
		...         "function AddSpell(spellObj) { ... }",
		...         "function AddRace(raceObj) { ... }",
		...         "function AddClass(classObj) { ... }"
		...     ],
		...     model="voyage-code-2"
		... )
		>>>
		>>> # Embed user query for retrieval
		>>> query_request = EmbeddingRequest(
		...     texts=["How do I add a custom spell?"],
		...     model="voyage-code-2"
		... )

	Note:
		Batch size impacts performance:
		- Small batches (1-10): Lower latency, good for queries
		- Medium batches (10-50): Balanced, good for incremental indexing
		- Large batches (50-100): Maximum throughput, good for initial indexing

		Code-specific embedding models (like voyage-code-2) significantly
		outperform general-purpose models for code retrieval tasks.
	"""
	texts: list[str] = Field(
		...,
		min_length=1,
		description="List of texts to embed (code chunks or queries)"
	)
	model: Optional[str] = Field(
		None,
		description="Embedding model to use (default: configured model)"
	)

class EmbeddingResponse(BaseModel):
	"""Response containing generated vector embeddings.

	Returns the vector representations of the input texts, ready for storage
	in the vector database or for similarity search.

	Attributes:
		embeddings: List of embedding vectors, one per input text. Each vector
			is a list of floats representing the text in high-dimensional space.
			The order matches the input texts in EmbeddingRequest.
		model: The actual embedding model used to generate these vectors.
			Important for ensuring consistency - all vectors in a collection
			must use the same model and dimension.
		dimension: The dimensionality of each embedding vector (e.g., 1536, 3072).
			Determined by the model. Higher dimensions can capture more nuance
			but require more storage and compute.

	Example:
		>>> response = EmbeddingResponse(
		...     embeddings=[
		...         [0.023, -0.145, 0.889, ...],  # 1536 floats for text 1
		...         [-0.067, 0.234, -0.456, ...],  # 1536 floats for text 2
		...         [0.123, -0.089, 0.567, ...]   # 1536 floats for text 3
		...     ],
		...     model="voyage-code-2",
		...     dimension=1536
		... )

	Note:
		Vector storage requirements:
		- 1536 dimensions × 4 bytes (float32) = ~6KB per vector
		- 10,000 chunks = ~60MB of vector data
		- Qdrant uses compression and indexing to optimize storage

		Never mix embeddings from different models in the same collection -
		similarity scores become meaningless when vectors use different
		representations.
	"""
	embeddings: list[list[float]] = Field(
		...,
		description="List of embedding vectors (one per input text)"
	)
	model: str = Field(
		...,
		description="Model used to generate embeddings"
	)
	dimension: int = Field(
		...,
		gt=0,
		description="Dimensionality of each embedding vector"
	)

class VectorSearchResult(BaseModel):
	"""Single result from vector similarity search.

	Represents one code chunk retrieved from Qdrant that matches the user's
	query, ranked by semantic similarity.

	Results are ordered by score (highest first) and typically limited to
	top-k most relevant chunks (e.g., top 5-10) to fit within LLM context windows.

	Attributes:
		id: Unique identifier for this chunk in the vector database. Corresponds
			to DocumentChunk.qdrant_id in PostgreSQL for metadata lookup.
		score: Similarity score between query and this chunk (0.0-1.0).
			Higher scores indicate stronger semantic similarity. Typical ranges:
			- 0.8-1.0: Highly relevant, exact or near-exact match
			- 0.6-0.8: Relevant, related concepts and similar code patterns
			- 0.4-0.6: Somewhat relevant, may contain useful context
			- <0.4: Likely not relevant, consider filtering out
		content: The actual code text of the retrieved chunk. This is what gets
			injected into the LLM prompt as context.
		metadata: Additional metadata about the chunk from the vector database.
			Includes fields from CodeChunk.metadata plus storage metadata:
			{
				"source_file": "src/common functions/SpellsList.js",
				"start_line": 45,
				"end_line": 62,
				"function_name": "AddSpell",
				"chunk_type": "function",
				"chunk_index": 3
			}

	Example:
		>>> result = VectorSearchResult(
		...     id="550e8400-e29b-41d4-a716-446655440000",
		...     score=0.87,
		...     content='function AddSpell(spellObj) {\\n  SpellsList[spellObj.name] = spellObj;\\n  ...\\n}',
		...     metadata={
		...         "source_file": "src/common functions/SpellsList.js",
		...         "start_line": 45,
		...         "end_line": 62,
		...         "function_name": "AddSpell"
		...     }
		... )

	Note:
		Score interpretation depends on the embedding model and similarity metric:
		- Cosine similarity (most common): 0.0-1.0, higher is better
		- Euclidean distance: Lower is better (inverted for consistency)

		Setting a similarity threshold (e.g., 0.5) filters out low-quality results
		that might confuse the LLM with irrelevant context.
	"""
	id: str = Field(
		...,
		description="Unique chunk ID in vector database (matches DocumentChunk.qdrant_id)"
	)
	score: float = Field(
		...,
		ge=0.0,
		le=1.0,
		description="Similarity score (0.0-1.0, higher = more relevant)"
	)
	content: str = Field(
		...,
		description="Retrieved code chunk text"
	)
	metadata: dict[str, Any] = Field(
		...,
		description="Chunk metadata (source file, line numbers, function names, etc.)"
	)

class RAGContext(BaseModel):
	"""Assembled context for LLM prompt generation.

	Combines the user's query with retrieved code chunks into a structured
	format ready for injection into the LLM system prompt.

	This model represents the final output of the retrieval phase, containing
	everything needed to generate an informed response.

	Attributes:
		query: The original user query that triggered the retrieval.
			Used to maintain context and for prompt formatting.
		retrieved_chunks: List of VectorSearchResult objects ranked by relevance.
			These are the code examples that will be provided to the LLM as context.
			Typically limited to top 5-10 results to preserve context window space.
		total_tokens: Estimated total tokens consumed by the retrieved chunks plus
			query. Used to ensure we don't exceed LLM context limits. Calculated
			using rough heuristic (~4 chars per token for code).
		context_window_used: Percentage of available context window consumed by
			the retrieved context (0.0-1.0). Helps balance between providing
			enough context and leaving room for the response. Target: <0.6 to
			leave room for long responses.

	Example:
		>>> context = RAGContext(
		...     query="How do I add a custom spell to MPMB?",
		...     retrieved_chunks=[
		...         VectorSearchResult(id="...", score=0.89, content="function AddSpell...", metadata={...}),
		...         VectorSearchResult(id="...", score=0.82, content="SpellsList['Fireball'] = {...}", metadata={...}),
		...         VectorSearchResult(id="...", score=0.75, content="// Spell object structure...", metadata={...})
		...     ],
		...     total_tokens=2340,
		...     context_window_used=0.45
		... )

	Note:
		Context window management is critical:
		- Claude 3.5 Sonnet: 200k context, use <50% for RAG context
		- GPT-4 Turbo: 128k context, use <40% for RAG context
		- Leave enough room for conversation history and response generation

		If context_window_used exceeds 0.6, consider:
		- Reducing top_k (retrieve fewer chunks)
		- Increasing similarity threshold (filter out marginal results)
		- Truncating chunk content to key portions
	"""
	query: str = Field(
		...,
		description="Original user query"
	)
	retrieved_chunks: list[VectorSearchResult] = Field(
		...,
		description="Retrieved code chunks ranked by relevance (top-k results)"
	)
	total_tokens: int = Field(
		...,
		ge=0,
		description="Estimated tokens in retrieved context (chunks + query)"
	)
	context_window_used: float = Field(
		...,
		ge=0.0,
		le=1.0,
		description="Percentage of LLM context window used by retrieved context (0.0-1.0)"
	)

class RetrievalMetadata(BaseModel):
	"""Metadata tracking the RAG retrieval process performance.

	Captures metrics about the retrieval phase for monitoring, debugging, and
	optimization. This data helps identify when retrieval quality is poor or
	when performance tuning is needed.

	Stored with each message to enable analysis of retrieval effectiveness
	and correlation between retrieval quality and response quality.

	Attributes:
		query: The query that was embedded and searched for. Useful for analyzing
			which types of queries retrieve well vs poorly.
		top_k: How many results were requested from the vector search.
			More results provide better coverage but consume more context.
		similarity_threshold: Minimum similarity score required for results.
			Results below this score are filtered out. Higher thresholds mean
			more selective but higher-quality retrievals.
		results_found: Actual number of results returned that met the threshold.
			If significantly lower than top_k, the threshold may be too strict
			or the query is very specific/novel.
		retrieval_time_ms: Time taken for the entire retrieval process in milliseconds.
			Includes query embedding, vector search, and result formatting.
			Helps identify performance bottlenecks.

	Example:
		>>> metadata = RetrievalMetadata(
		...     query="How do I add a custom spell?",
		...     top_k=10,
		...     similarity_threshold=0.5,
		...     results_found=7,
		...     retrieval_time_ms=145.3
		... )
		>>>
		>>> # Poor retrieval - may need to lower threshold
		>>> poor = RetrievalMetadata(
		...     query="implement quantum spell effects",
		...     top_k=10,
		...     similarity_threshold=0.7,
		...     results_found=1,  # Only 1 result found
		...     retrieval_time_ms=132.8
		... )

	Note:
		Performance benchmarks:
		- Good retrieval: 50-200ms (depends on corpus size and hardware)
		- Slow retrieval: >500ms (may need index optimization or better hardware)
		- Query embedding: ~20-50ms
		- Vector search: ~10-100ms
		- Result processing: ~10-50ms

		Retrieval quality indicators:
		- results_found ≈ top_k: Query matches existing content well
		- results_found << top_k: Very specific query or threshold too high
		- results_found = 0: No relevant content or threshold too strict

		Use this metadata to build analytics dashboards showing:
		- Average retrieval quality over time
		- Slow queries that need optimization
		- Queries with poor recall (low results_found)
	"""
	query: str = Field(
		...,
		description="Query text that was searched"
	)
	top_k: int = Field(
		...,
		gt=0,
		description="Number of results requested from search"
	)
	similarity_threshold: float = Field(
		...,
		ge=0.0,
		le=1.0,
		description="Minimum similarity score for results (0.0-1.0)"
	)
	results_found: int = Field(
		...,
		ge=0,
		description="Actual number of results returned above threshold"
	)
	retrieval_time_ms: float = Field(
		...,
		ge=0.0,
		description="Total retrieval time in milliseconds"
	)
