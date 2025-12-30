"""LLM-related Pydantic models

This module defines Pydantic models for the LLM (Large Language Model) abstraction layer,
which provides a unified interface for multiple AI providers (Anthropic, OpenAI, Ollama).

The abstraction layer allows MPMB-Copilot to:
- Switch between different LLM providers without code changes
- Support both cloud APIs and local models
- Handle streaming and non-streaming responses uniformly
- Track usage and costs across providers
- Enable provider-specific fallbacks and failovers

Supported providers:
- Anthropic (Claude): Cloud API, best quality for MPMB assistance
- OpenAI (GPT): Cloud API, alternative provider
- Ollama: Local models, cost-free but requires local GPU
"""
from typing import Optional, Literal
from pydantic import BaseModel, Field

class LLMProvider(BaseModel):
	"""LLM provider configuration model.

	Defines the configuration for a specific LLM provider, including
	authentication credentials and connection details.

	This model is typically loaded from environment variables or configuration
	files during application startup and used to initialize provider clients.

	Attributes:
		name: Provider identifier. Supported values:
			- "anthropic": Anthropic Claude API (claude.ai)
			- "openai": OpenAI GPT API (platform.openai.com)
			- "ollama": Local Ollama server for open-source models
		api_key: API authentication key. Required for cloud providers
			(Anthropic, OpenAI). Not used for Ollama. Should be loaded from
			environment variables (ANTHROPIC_API_KEY, OPENAI_API_KEY).
		base_url: Custom API endpoint URL. Optional for most cases:
			- Anthropic: Defaults to https://api.anthropic.com
			- OpenAI: Defaults to https://api.openai.com/v1
			- Ollama: Required, typically http://localhost:11434
		default_model: Default model to use when not specified in requests.
			Examples:
			- Anthropic: "claude-sonnet-4-5", "claude-opus-4"
			- OpenAI: "gpt-4", "gpt-3.5-turbo"
			- Ollama: "codellama", "mistral", "llama2"

	Example:
		>>> # Anthropic configuration
		>>> anthropic = LLMProvider(
		...     name="anthropic",
		...     api_key="sk-ant-api03-...",
		...     default_model="claude-sonnet-4-5"
		... )
		>>>
		>>> # Ollama local configuration
		>>> ollama = LLMProvider(
		...     name="ollama",
		...     base_url="http://localhost:11434",
		...     default_model="codellama"
		... )

	Note:
		API keys should NEVER be committed to version control. Always load
		from environment variables or secure configuration management systems.
	"""
	name: Literal["anthropic", "openai", "ollama"] = Field(
		...,
		description="Provider identifier (anthropic/openai/ollama)"
	)
	api_key: Optional[str] = Field(
		None,
		description="API authentication key (not needed for Ollama)"
	)
	base_url: Optional[str] = Field(
		None,
		description="Custom API endpoint (required for Ollama, optional for cloud providers)"
	)
	default_model: str = Field(
		...,
		description="Default model name to use for this provider"
	)

class LLMMessage(BaseModel):
	"""Single message in an LLM conversation.

	Represents one turn in a conversation, following the standard chat message
	format used by most modern LLM APIs.

	Messages are assembled into conversation histories and sent to the LLM
	to provide context for generating responses.

	Attributes:
		role: Message role identifier. Values:
			- "system": System instructions/prompts that guide behavior
				(e.g., "You are a helpful MPMB automation assistant")
			- "user": Messages from the human user
			- "assistant": Previous responses from the AI assistant
		content: The actual message text. For system messages, this is typically
			the system prompt. For user messages, this is the question/request.
			For assistant messages, this is the previous AI response.

	Example:
		>>> # System message
		>>> system = LLMMessage(
		...     role="system",
		...     content="You are an expert in MPMB JavaScript automation."
		... )
		>>>
		>>> # User message
		>>> user = LLMMessage(
		...     role="user",
		...     content="How do I add a custom spell to SpellsList?"
		... )
		>>>
		>>> # Assistant message (from conversation history)
		>>> assistant = LLMMessage(
		...     role="assistant",
		...     content="To add a spell, you need to modify SpellsList..."
		... )

	Note:
		The order of messages matters. Typical conversation structure:
		1. One system message (optional, but recommended)
		2. Alternating user/assistant messages from conversation history
		3. Final user message (the current query)
	"""
	role: Literal["system", "user", "assistant"] = Field(
		...,
		description="Message role (system/user/assistant)"
	)
	content: str = Field(
		...,
		description="Message content/text"
	)

class LLMRequest(BaseModel):
	"""Request to generate a completion from an LLM provider.

	Encapsulates all parameters needed to generate an LLM response, including
	conversation history, model selection, and generation parameters.

	This model is provider-agnostic and gets translated to provider-specific
	API formats by the LLM service layer.

	Attributes:
		messages: Conversation history as a list of LLMMessage objects.
			Should include system prompt, conversation history, and current query.
		model: Specific model to use for this request. Overrides the provider's
			default_model. Use provider-specific model names.
		temperature: Controls randomness in generation (0.0-2.0):
			- 0.0: Deterministic, focused responses (good for code)
			- 0.2-0.5: Slightly creative but reliable (recommended for MPMB)
			- 0.7-1.0: More creative and varied responses
			- 1.5-2.0: Very creative, potentially unpredictable
		max_tokens: Maximum number of tokens to generate in the response.
			Limits response length. Typical values:
			- 500-1000: Short answers and code snippets
			- 2000-4000: Detailed explanations (recommended)
			- 8000+: Very long responses or complex code
		stream: If True, response is streamed as LLMStreamChunk objects.
			If False, returns complete LLMResponse. Streaming provides better
			UX for long responses but requires SSE handling.
		system_prompt: Optional system prompt to prepend to messages.
			If provided, automatically adds a system message at the start.
			Useful for applying RAG context or custom instructions.

	Example:
		>>> # Standard request with RAG context
		>>> request = LLMRequest(
		...     messages=[
		...         LLMMessage(role="user", content="How do I add a race?")
		...     ],
		...     model="claude-sonnet-4-5",
		...     temperature=0.2,
		...     max_tokens=2000,
		...     stream=False,
		...     system_prompt="You are an MPMB expert. Context: [RAG chunks...]"
		... )
		>>>
		>>> # Streaming request for real-time response
		>>> streaming = LLMRequest(
		...     messages=[
		...         LLMMessage(role="user", content="Explain spell automation")
		...     ],
		...     model="gpt-4",
		...     temperature=0.3,
		...     max_tokens=4000,
		...     stream=True
		... )

	Note:
		Token limits vary by provider:
		- Claude 3.5 Sonnet: 200k context, 8k output
		- GPT-4 Turbo: 128k context, 4k output
		- Ollama models: Varies by model (typically 2k-8k)

		For MPMB copilot, 2000-4000 tokens usually provides enough detail
		for code examples and explanations without hitting limits.
	"""
	messages: list[LLMMessage] = Field(
		...,
		description="Conversation history including system, user, and assistant messages"
	)
	model: str = Field(
		...,
		description="Model name to use (provider-specific)"
	)
	temperature: float = Field(
		0.2,
		ge=0.0,
		le=2.0,
		description="Sampling temperature (0.0=deterministic, 2.0=creative)"
	)
	max_tokens: int = Field(
		4000,
		gt=0,
		description="Maximum tokens to generate in response"
	)
	stream: bool = Field(
		False,
		description="Enable streaming response (returns LLMStreamChunk objects)"
	)
	system_prompt: Optional[str] = Field(
		None,
		description="Optional system prompt to prepend (adds system message)"
	)

class LLMResponse(BaseModel):
	"""Complete response from an LLM provider (non-streaming).

	Contains the generated completion along with metadata about token usage,
	model used, and generation details for tracking and cost calculation.

	Attributes:
		content: The generated text response from the LLM
		model: Actual model used for generation (may differ from requested
			if fallback occurred)
		provider: Which provider generated this response (anthropic/openai/ollama)
		usage: Token usage statistics as a dictionary with keys:
			- "prompt_tokens": Tokens in the input (messages + system prompt)
			- "completion_tokens": Tokens in the generated response
			- "total_tokens": Sum of prompt_tokens + completion_tokens
		stop_reason: Why generation stopped. Common values:
			- "end_turn": Natural completion (assistant finished response)
			- "max_tokens": Hit the max_tokens limit (response truncated)
			- "stop_sequence": Encountered a stop sequence
			- None: Unknown or not provided by provider
		latency_ms: Time taken to generate the response in milliseconds.
			Includes API request time, generation time, and network latency.

	Example:
		>>> response = LLMResponse(
		...     content="To add a spell to MPMB, you need to...",
		...     model="claude-sonnet-4-5",
		...     provider="anthropic",
		...     usage={
		...         "prompt_tokens": 1250,
		...         "completion_tokens": 340,
		...         "total_tokens": 1590
		...     },
		...     stop_reason="end_turn",
		...     latency_ms=2340
		... )

	Note:
		Token costs vary by provider and model:
		- Claude Sonnet 4.5: ~$3/$15 per 1M input/output tokens
		- GPT-4 Turbo: ~$10/$30 per 1M input/output tokens
		- Ollama: Free (local compute costs only)

		Track usage field to monitor costs and optimize context window usage.
	"""
	content: str = Field(
		...,
		description="Generated text response from the LLM"
	)
	model: str = Field(
		...,
		description="Model that generated the response"
	)
	provider: str = Field(
		...,
		description="Provider that generated the response (anthropic/openai/ollama)"
	)
	usage: dict[str, int] = Field(
		...,
		description="Token usage stats (prompt_tokens, completion_tokens, total_tokens)"
	)
	stop_reason: Optional[str] = Field(
		None,
		description="Why generation stopped (end_turn/max_tokens/stop_sequence)"
	)
	latency_ms: int = Field(
		...,
		description="Total response time in milliseconds"
	)

class LLMStreamChunk(BaseModel):
	"""Single chunk from a streaming LLM response.

	When stream=True in LLMRequest, the response is delivered incrementally
	as a series of LLMStreamChunk objects via Server-Sent Events (SSE).

	This enables real-time display of the response as it's being generated,
	improving perceived performance for long responses.

	Attributes:
		content: Partial response text for this chunk. Successive chunks
			should be concatenated to build the complete response.
		done: Whether this is the final chunk in the stream. When True,
			no more chunks will follow and the stream is complete.
		model: Model name, only included in the final chunk (when done=True).
			None for intermediate chunks.
		finish_reason: Why the stream ended, only in final chunk (when done=True).
			Same values as LLMResponse.stop_reason. None for intermediate chunks.

	Example:
		>>> # First chunk (partial response)
		>>> chunk1 = LLMStreamChunk(
		...     content="To add a spell",
		...     done=False
		... )
		>>>
		>>> # Middle chunk
		>>> chunk2 = LLMStreamChunk(
		...     content=" to the SpellsList",
		...     done=False
		... )
		>>>
		>>> # Final chunk
		>>> final = LLMStreamChunk(
		...     content=" object, you need to...",
		...     done=True,
		...     model="claude-sonnet-4-5",
		...     finish_reason="end_turn"
		... )

	Note:
		Streaming workflow:
		1. Client initiates SSE connection
		2. Server sends chunks as they're generated
		3. Client concatenates chunk.content values
		4. When done=True, display is complete

		Chunks typically arrive every 50-200ms depending on model and
		network conditions. Empty chunks (content="") may occur between
		larger chunks.

		Token usage is not included in streaming responses - calculate
		on the server side after stream completes if needed.
	"""
	content: str = Field(
		...,
		description="Partial response text for this chunk"
	)
	done: bool = Field(
		False,
		description="Whether this is the final chunk in the stream"
	)
	model: Optional[str] = Field(
		None,
		description="Model name (only in final chunk when done=True)"
	)
	finish_reason: Optional[str] = Field(
		None,
		description="Stream completion reason (only in final chunk when done=True)"
	)
