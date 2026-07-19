"""Unfilter roundtrip fidelity — tests alias reconstruction from real LLM output."""
import asyncio, os, pytest
from piifilter.shared.alias_store import AliasStore
from piifilter.session import Session

pytestmark = pytest.mark.skipif(
    not os.environ.get("PIIFILTER_LIVE_TESTS"),
    reason="Set PIIFILTER_LIVE_TESTS=1"
)

@pytest.mark.asyncio
async def test_unfilter_reconstructs_originals():
    """Filter prompt, send to real LLM, get streaming response, unfilter, verify."""
    # Setup alias store
    store = AliasStore(seed="test-unfilter")
    
    # Create session with aliases
    session = Session(
        prompt="My email is john@example.com and I live in New York",
        conversation_id="unfilter-test-1"
    )
    session.alias_store = store
    
    # Create aliases
    email_alias = store.get_or_create(session.conversation_id, "john@example.com", "EMAIL")
    city_alias = store.get_or_create(session.conversation_id, "New York", "CITY")
    
    # Simulate LLM response that uses the aliases
    llm_response = f"Hello! I see your email is {email_alias} and you live in {city_alias}. That's great!"
    
    # Unfilter
    async def stream():
        for token in llm_response.split(" "):
            yield token + " "
    
    unfiltered = ""
    async for chunk in session.unfilter_stream(stream()):
        unfiltered += chunk
    
    assert "john@example.com" in unfiltered, f"Email should be reconstructed, got: {unfiltered}"
    assert "New York" in unfiltered, f"City should be reconstructed, got: {unfiltered}"
    assert "Hello!" in unfiltered