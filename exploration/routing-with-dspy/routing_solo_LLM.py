
import os
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv()

load_dotenv()
key = os.getenv('OPENAI_API_KEY')

common_llm = ChatOpenAI(model="gpt-4o", api_key = key, temperature=0)

DESTINATIONS = {
    "search_internet": "internet_search",
    "search_github": "github_search",
    "search_atlassian": "atlassian_search",
    "general_ai_response": "general",
    "email_assistant": "email_assistant",
    "search_google_maps": "google_maps_search",
    "search_knowledge_base": "knowledge_base_search",
    "search_sqlite": "sqlite_search",
    "unknown": "unknown",
    "reset_mode": "general",
}


def route_request(user_query: str, common_llm: ChatOpenAI):
    """
    Routes user input to the appropriate destination based on content analysis.
    """

    # For all other cases, determine the appropriate destination
    return _determine_destination(user_query, common_llm)

def _determine_destination(user_query: str, llm: ChatOpenAI):
    """
    Helper function to determine the appropriate destination for user input.
    
    Args:
        state: Current application state
        llm: Language model for classification
        
    Returns:
        Updated state with destination set
    """
    prompt = _build_routing_prompt(user_query)
    result = llm.invoke(prompt)
    
    # Process and validate the model's response
    raw_destination = result.content.strip().lower()
    destination = _validate_destination(raw_destination)
    
    
    return destination


def _build_routing_prompt(user_input: str) -> str:
    """
    Constructs a clear prompt for the routing LLM.
    
    Args:
        user_input: The user's message
        
    Returns:
        A formatted prompt string
    """
    # Get valid destination options (excluding reset_mode)
    valid_options = [mode for mode in DESTINATIONS.keys() if mode != 'reset_mode']
    options_list = ', '.join(valid_options)
    
    # Multi-line prompt for better readability
    prompt = f"""You are a chatbot classifier. Analyze this user input: "{user_input}"

Your task is to classify this input into exactly ONE of these categories:
{options_list}

Respond with ONLY the category name, nothing else. For example:
- For search queries about the web: "search_internet"
- For questions about coding repositories: "search_github"
- For JIRA or Atlassian questions: "search_atlassian"
- For questions about the internal sqlite DB: "search_sqlite" the name is Chinook_Sqlite.db
- For help with emails or email drafting: "email_assistant"
- For general knowledge questions: "general_ai_response"
- For location or map queries: "search_google_maps"
- For questions about the internal knowledge base. This is a ChromaDB collection and is about our users and their interactions with our product: "search_knowledge_base"
- For queries that don't fit any category: "unknown"

Classification:"""
    
    return prompt


def _validate_destination(raw_destination: str) -> str:
    """
    Validates and sanitizes the destination returned by the LLM.
    
    Args:
        raw_destination: The raw destination string from the LLM
        
    Returns:
        A validated destination string
    """
    # Check if the raw destination is a valid key in DESTINATIONS
    if raw_destination in DESTINATIONS:
        return raw_destination
    
    # Log invalid destinations for debugging
    print(f"Warning: Invalid destination '{raw_destination}', defaulting to 'unknown'")
    
    # Try to find a close match (optional)
    for valid_dest in DESTINATIONS.keys():
        if valid_dest in raw_destination:
            print(f"Found partial match: '{valid_dest}'")
            return valid_dest
    
    # Default fallback
    return "unknown"

test_user_query = "Show me my latest commits on the main branch in GitHub."
print(route_request(test_user_query, common_llm))
