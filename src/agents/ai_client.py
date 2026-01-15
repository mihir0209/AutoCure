"""
AI Client Provider for Groq and Cerebras.
Provides unified interface for AI inference using OpenAI-compatible APIs.
"""

import os
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import httpx

from utils.logger import setup_colored_logger

logger = setup_colored_logger("ai_client")


@dataclass
class ChatMessage:
    """Represents a chat message"""
    role: str  # 'system', 'user', 'assistant'
    content: str


@dataclass
class ChatCompletion:
    """Represents a chat completion response"""
    content: str
    model: str
    usage: Dict[str, int]
    finish_reason: str


class AIClient:
    """
    Unified AI Client for Groq and Cerebras APIs.
    Uses OpenAI-compatible endpoints.
    """
    
    PROVIDERS = {
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "default_model": "llama-3.3-70b-versatile",
            "models": [
                "llama-3.3-70b-versatile",
                "llama-3.1-70b-versatile", 
                "llama-3.1-8b-instant",
                "mixtral-8x7b-32768",
                "gemma2-9b-it",
            ]
        },
        "cerebras": {
            "base_url": "https://api.cerebras.ai/v1",
            "default_model": "llama3.1-8b",
            "models": [
                "llama3.1-8b",
                "llama3.1-70b",
            ]
        }
    }
    
    def __init__(
        self,
        provider: str = "groq",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 3,
    ):
        """
        Initialize AI Client.
        
        Args:
            provider: 'groq' or 'cerebras'
            api_key: API key (or uses environment variable)
            model: Model to use (or uses provider default)
            base_url: Custom base URL (or uses provider default)
            timeout: Request timeout in seconds
            max_retries: Number of retries on failure
        """
        self.provider = provider.lower()
        
        if self.provider not in self.PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}. Supported: {list(self.PROVIDERS.keys())}")
        
        provider_config = self.PROVIDERS[self.provider]
        
        # Set API key
        if api_key:
            self.api_key = api_key
        else:
            env_var = f"{self.provider.upper()}_API_KEY"
            self.api_key = os.getenv(env_var, "")
        
        if not self.api_key:
            logger.warning(f"No API key provided for {provider}. Set {env_var} environment variable.")
        
        # Set model
        self.model = model or provider_config["default_model"]
        
        # Set base URL
        self.base_url = base_url or provider_config["base_url"]
        
        self.timeout = timeout
        self.max_retries = max_retries
        
        logger.info(f"AI Client initialized: {self.provider} / {self.model}")
    
    async def chat_completion(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> ChatCompletion:
        """
        Generate a chat completion.
        
        Args:
            messages: List of chat messages
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters to pass to the API
            
        Returns:
            ChatCompletion object with the response
        """
        url = f"{self.base_url}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    
                    return ChatCompletion(
                        content=data["choices"][0]["message"]["content"],
                        model=data["model"],
                        usage=data.get("usage", {}),
                        finish_reason=data["choices"][0].get("finish_reason", "stop"),
                    )
                    
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error (attempt {attempt + 1}): {e.response.status_code}")
                if attempt == self.max_retries - 1:
                    raise
            except httpx.RequestError as e:
                logger.error(f"Request error (attempt {attempt + 1}): {e}")
                if attempt == self.max_retries - 1:
                    raise
            except Exception as e:
                logger.error(f"Unexpected error (attempt {attempt + 1}): {e}")
                if attempt == self.max_retries - 1:
                    raise
        
        raise Exception("Max retries exceeded")
    
    async def generate_fix(
        self,
        error_context: str,
        source_code: str,
        file_path: str,
    ) -> Dict[str, Any]:
        """
        Generate a fix for the given error.
        
        Args:
            error_context: Error message and stack trace
            source_code: The source code with the bug
            file_path: Path to the file
            
        Returns:
            Dictionary with fixed_code and explanation
        """
        system_prompt = """You are an expert software engineer specializing in debugging and fixing code.
Your task is to analyze errors and generate fixes for buggy code.

When fixing code:
1. Identify the root cause of the error
2. Provide a minimal fix that resolves the issue
3. Maintain the original code style and structure
4. Add appropriate error handling where needed
5. Do not change unrelated code

Respond in the following JSON format:
{
    "fixed_code": "// The complete fixed source code",
    "explanation": "Brief explanation of what was wrong and how you fixed it",
    "confidence": 0.85,
    "changes_summary": ["List of specific changes made"]
}"""

        user_prompt = f"""Please fix the following code that is causing an error.

**File:** {file_path}

**Error:**
```
{error_context}
```

**Current Source Code:**
```javascript
{source_code}
```

Provide the complete fixed code with your fix applied. Respond with valid JSON only."""

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
        
        completion = await self.chat_completion(
            messages=messages,
            temperature=0.3,  # Lower temperature for more consistent fixes
            max_tokens=8192,
        )
        
        # Parse the JSON response
        try:
            import json
            # Try to extract JSON from the response
            content = completion.content.strip()
            
            # Handle markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            return json.loads(content)
        except json.JSONDecodeError:
            # If JSON parsing fails, return raw content
            return {
                "fixed_code": completion.content,
                "explanation": "AI generated fix (parsing failed)",
                "confidence": 0.5,
                "changes_summary": ["Unable to parse structured response"]
            }
    
    async def generate_tests(
        self,
        source_code: str,
        file_path: str,
        error_type: str,
    ) -> str:
        """
        Generate test cases for the fixed code.
        
        Args:
            source_code: The fixed source code
            file_path: Path to the file
            error_type: Type of error that was fixed
            
        Returns:
            Test code as string
        """
        system_prompt = """You are an expert software engineer specializing in test-driven development.
Generate comprehensive test cases to validate that a bug fix works correctly.

Focus on:
1. Testing the specific fix that was applied
2. Edge cases that could cause similar errors
3. Both positive (valid input) and negative (invalid input) test cases
4. Testing boundary conditions

Use Node.js built-in test runner (node:test) format."""

        user_prompt = f"""Generate test cases for the following code that was fixed for a {error_type}.

**File:** {file_path}

**Source Code:**
```javascript
{source_code}
```

Generate test cases that:
1. Verify the fix works with valid inputs
2. Test edge cases (null, undefined, empty values)
3. Test boundary conditions
4. Verify error handling

Provide only the test code, no explanations."""

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
        
        completion = await self.chat_completion(
            messages=messages,
            temperature=0.4,
            max_tokens=4096,
        )
        
        content = completion.content.strip()
        
        # Extract code from markdown blocks if present
        if "```javascript" in content:
            content = content.split("```javascript")[1].split("```")[0]
        elif "```js" in content:
            content = content.split("```js")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        return content
    
    async def analyze_test_failure(
        self,
        test_output: str,
        source_code: str,
        previous_fix_explanation: str,
    ) -> Dict[str, Any]:
        """
        Analyze why tests failed and suggest improvements.
        
        Args:
            test_output: Output from test execution
            source_code: Current source code
            previous_fix_explanation: Explanation of the previous fix attempt
            
        Returns:
            Analysis with suggested improvements
        """
        system_prompt = """You are an expert software engineer analyzing test failures.
Analyze why the tests failed and provide an improved fix.

Respond in JSON format:
{
    "analysis": "Why the tests failed",
    "improved_fix": "// The improved source code",
    "explanation": "What's different in this fix",
    "confidence": 0.85
}"""

        user_prompt = f"""The previous fix didn't pass all tests.

**Previous fix explanation:** {previous_fix_explanation}

**Test Output:**
```
{test_output}
```

**Current Source Code:**
```javascript
{source_code}
```

Analyze the failures and provide an improved fix. Respond with valid JSON only."""

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
        
        completion = await self.chat_completion(
            messages=messages,
            temperature=0.3,
            max_tokens=8192,
        )
        
        try:
            import json
            content = completion.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            return json.loads(content)
        except json.JSONDecodeError:
            return {
                "analysis": "Unable to parse analysis",
                "improved_fix": completion.content,
                "explanation": "AI generated improved fix",
                "confidence": 0.5
            }
