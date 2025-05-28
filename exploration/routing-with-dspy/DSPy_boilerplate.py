
import dspy
from dotenv import load_dotenv
import os
import random
from typing import List, Dict, Tuple
from dspy.evaluate import Evaluate
from dspy.teleprompt import BootstrapFewShot
import logging

# Set up logging for better debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
key = os.getenv('OPENAI_API_KEY')

class MCPRouterConfig:
    """Configuration class for MCP Router to centralize all constants and mappings."""
    
    # Valid MCP server identifiers - this should be your single source of truth
    VALID_MCPS = [
        'github_mcp', 
        'jira_mcp', 
        'salesforce_mcp', 
        'calendar_mcp', 
        'general_fallback'
    ]
    
    # Human-readable descriptions for each MCP
    MCP_DESCRIPTIONS = {
        'github_mcp': 'GitHub operations (repos, PRs, commits, issues)',
        'jira_mcp': 'Jira project management (tasks, issues, assignments)',
        'salesforce_mcp': 'Salesforce CRM (accounts, opportunities, cases)',
        'calendar_mcp': 'Calendar management (meetings, scheduling)',
        'general_fallback': 'General AI assistant for other queries'
    }
    
    @classmethod
    def get_valid_mcps_string(cls) -> str:
        """Get a formatted string of valid MCPs for the signature description."""
        return "', '".join(cls.VALID_MCPS)

class MCPServerRouter(dspy.Signature):
    """Routes a user query to the appropriate MCP server based on intent and capabilities."""
    
    user_query = dspy.InputField(desc="The user's natural language query requiring routing to an appropriate service.")
    
    # Use consistent field naming with training data
    target_mcp = dspy.OutputField(
        desc=f"The MCP server identifier that can best handle this query. Must be exactly one of: '{MCPRouterConfig.get_valid_mcps_string()}'. "
             f"Choose based on query intent: {MCPRouterConfig.MCP_DESCRIPTIONS}"
    )

class MCPRouterTrainer:
    """Handles training data management and model compilation for MCP routing."""
    
    def __init__(self, api_key: str):
        """Initialize the trainer with API configuration."""
        if api_key is None:
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable or pass api_key parameter.")
        
        # Initialize the language model
        self.lm = dspy.LM('openai/gpt-4o-mini', api_key=api_key)
        dspy.configure(lm=self.lm)
        
        # Initialize base router
        self.base_router = dspy.Predict(MCPServerRouter)
        self.compiled_router = None
        
    def create_training_data(self) -> List[dspy.Example]:
        """Create and return structured training examples."""
        raw_data = [
            # GitHub MCP examples
            {"user_query": "Show me my latest commits on the main branch in GitHub.", "target_mcp": "github_mcp"},
            {"user_query": "List all open pull requests in the backend repository.", "target_mcp": "github_mcp"},
            {"user_query": "Review pull request #102 from user_xyz.", "target_mcp": "github_mcp"},
            {"user_query": "Compare branches 'feature/new-ui' and 'develop' in GitHub.", "target_mcp": "github_mcp"},
            {"user_query": "Check if my latest pull request was merged on GitHub.", "target_mcp": "github_mcp"},
            {"user_query": "Create a new branch from main for the authentication feature.", "target_mcp": "github_mcp"},
            
            # Jira MCP examples
            {"user_query": "Create a new issue in Jira for bug tracking.", "target_mcp": "jira_mcp"},
            {"user_query": "Assign task JRA-456 to me in the Jira project.", "target_mcp": "jira_mcp"},
            {"user_query": "Search for issues containing the keyword 'authentication failure' in Jira.", "target_mcp": "jira_mcp"},
            {"user_query": "Create a sub-task under JRA-789 in Jira.", "target_mcp": "jira_mcp"},
            {"user_query": "Update the priority of ticket PROJ-123 to high.", "target_mcp": "jira_mcp"},
            {"user_query": "Move issue to 'In Progress' status in our sprint.", "target_mcp": "jira_mcp"},
            
            # Salesforce MCP examples
            {"user_query": "Check the status of the 'Big Deal' opportunity in Salesforce.", "target_mcp": "salesforce_mcp"},
            {"user_query": "Update the contact information for the 'Alpha Corp' account in Salesforce.", "target_mcp": "salesforce_mcp"},
            {"user_query": "Log a new support case for a customer in Salesforce.", "target_mcp": "salesforce_mcp"},
            {"user_query": "Who is the primary contact for the 'Beta Services' opportunity in Salesforce?", "target_mcp": "salesforce_mcp"},
            {"user_query": "Find details about the customer account 'Globex Corp' in Salesforce.", "target_mcp": "salesforce_mcp"},
            {"user_query": "Create a new lead from the trade show contacts.", "target_mcp": "salesforce_mcp"},
            
            # Calendar MCP examples
            {"user_query": "Add a meeting to my calendar for project sync tomorrow.", "target_mcp": "calendar_mcp"},
            {"user_query": "What does my schedule look like for next week?", "target_mcp": "calendar_mcp"},
            {"user_query": "Find an open slot for a 30-minute meeting on Wednesday.", "target_mcp": "calendar_mcp"},
            {"user_query": "Reschedule my 10 AM meeting to 11 AM tomorrow.", "target_mcp": "calendar_mcp"},
            {"user_query": "Book a meeting room for my team sync on Friday.", "target_mcp": "calendar_mcp"},
            {"user_query": "Cancel my 3 PM appointment and send apologies.", "target_mcp": "calendar_mcp"},
            
            # General fallback examples
            {"user_query": "Tell me a random fact.", "target_mcp": "general_fallback"},
            {"user_query": "Write a short email.", "target_mcp": "general_fallback"},
            {"user_query": "What is the capital of France?", "target_mcp": "general_fallback"},
            {"user_query": "Explain quantum computing in simple terms.", "target_mcp": "general_fallback"},
            {"user_query": "Help me brainstorm ideas for a presentation.", "target_mcp": "general_fallback"},
            {"user_query": "What movies are playing tonight?", "target_mcp": "general_fallback"},
        ]
        
        # Convert to DSPy examples with proper input specification
        examples = [
            dspy.Example(user_query=item["user_query"], target_mcp=item["target_mcp"]).with_inputs("user_query") 
            for item in raw_data
        ]
        
        return examples
    
    def split_data(self, examples: List[dspy.Example], train_ratio: float = 0.8) -> Tuple[List[dspy.Example], List[dspy.Example]]:
        """Split data into training and evaluation sets with proper shuffling."""
        shuffled_examples = examples.copy()
        random.shuffle(shuffled_examples)
        
        split_index = int(len(shuffled_examples) * train_ratio)
        train_set = shuffled_examples[:split_index]
        eval_set = shuffled_examples[split_index:]
        
        logger.info(f"Data split: {len(train_set)} training examples, {len(eval_set)} evaluation examples")
        return train_set, eval_set
    
    def router_accuracy_metric(self, gold: dspy.Example, pred: dspy.Prediction, trace=None) -> float:
        """
        Improved accuracy metric with better error handling and logging.
        Returns 1.0 for correct prediction, 0.0 for incorrect.
        """
        # Handle cases where prediction failed or is malformed
        if not pred or not hasattr(pred, 'target_mcp'):
            logger.warning(f"Prediction missing target_mcp attribute for query: {gold.user_query}")
            return 0.0
        
        predicted_mcp = str(pred.target_mcp).strip().lower()
        actual_mcp = str(gold.target_mcp).strip().lower()
        
        # Check if predicted MCP is valid
        if predicted_mcp not in [mcp.lower() for mcp in MCPRouterConfig.VALID_MCPS]:
            logger.warning(f"Invalid MCP predicted: {predicted_mcp} for query: {gold.user_query}")
            return 0.0
        
        # Calculate accuracy
        is_correct = predicted_mcp == actual_mcp
        
        # Log incorrect predictions for debugging
        if not is_correct:
            logger.debug(f"Incorrect prediction - Query: '{gold.user_query}' | Expected: {actual_mcp} | Got: {predicted_mcp}")
        
        return float(is_correct)
    
    def train_router(self, max_bootstrapped_demos: int = 8, max_labeled_demos: int = 16) -> dspy.Module:
        """Train the router using BootstrapFewShot optimization."""
        logger.info("Starting router training...")
        
        # Get training data
        all_examples = self.create_training_data()
        training_examples, _ = self.split_data(all_examples)
        
        # Configure the optimizer
        fewshot_optimizer = BootstrapFewShot(
            metric=self.router_accuracy_metric,
            max_bootstrapped_demos=max_bootstrapped_demos,
            max_labeled_demos=max_labeled_demos
        )
        
        # Compile the router
        logger.info("Compiling router with few-shot examples...")
        self.compiled_router = fewshot_optimizer.compile(
            self.base_router, 
            trainset=training_examples
        )
        
        logger.info("Router training completed successfully!")
        return self.compiled_router
    
    def evaluate_router(self, router: dspy.Module) -> float:
        """Evaluate the router performance on held-out data."""
        if router is None:
            router = self.compiled_router
        
        if router is None:
            raise ValueError("No compiled router available. Train the router first.")
        
        # Get evaluation data
        all_examples = self.create_training_data()
        _, evaluation_examples = self.split_data(all_examples)
        
        if not evaluation_examples:
            logger.warning("No evaluation examples available. Using a subset of training data.")
            evaluation_examples = all_examples[-5:]  # Use last 5 examples for evaluation
        
        logger.info(f"Evaluating router on {len(evaluation_examples)} examples...")
        
        # Create evaluator
        evaluator = Evaluate(
            devset=evaluation_examples,
            metric=self.router_accuracy_metric,
            num_threads=1,
            display_progress=True,
            display_table=5  # Show detailed results for debugging
        )
        
        # Run evaluation
        evaluation_score = evaluator(router)
        logger.info(f"Evaluation completed. Accuracy: {evaluation_score:.4f}")
        
        return evaluation_score
    
    def test_router_predictions(self, test_queries: List[str]) -> Dict[str, str]:
        """Test the router on specific queries and return predictions."""
        if self.compiled_router is None:
            raise ValueError("No compiled router available. Train the router first.")
        
        results = {}
        logger.info("Testing router predictions...")
        
        for query in test_queries:
            try:
                prediction = self.compiled_router(user_query=query)
                predicted_mcp = prediction.target_mcp
                results[query] = predicted_mcp
                logger.info(f"Query: '{query}' -> Predicted MCP: {predicted_mcp}")
            except Exception as e:
                logger.error(f"Error predicting for query '{query}': {str(e)}")
                results[query] = "ERROR"
        
        return results

def main():
    """Main execution function demonstrating the complete workflow."""
    try:
        # Initialize trainer
        trainer = MCPRouterTrainer(key)
        
        # Train the router
        compiled_router = trainer.train_router()
        
        # Evaluate performance
        accuracy = trainer.evaluate_router(compiled_router)
        print(f"\nFinal Model Accuracy: {accuracy:.4f}")
        
        # Test on sample queries
        print("\nTesting on sample queries:")
        test_queries = [
                "Check if my latest pull request was merged on GitHub.",
                "Create a follow-up task in Jira for a completed story.",
                "Find details about the customer account 'Globex Corp' in Salesforce.",
                "Book a meeting room for my team sync on Friday.",
                "What movies are playing tonight?"
            ]
        predictions = trainer.test_router_predictions(test_queries)
        
        # Display results in a formatted way
        print("\n" + "="*60)
        print("ROUTER PREDICTION RESULTS")
        print("="*60)
        for query, prediction in predictions.items():
            print(f"Query: {query}")
            print(f"→ Routed to: {prediction}")
            if prediction in MCPRouterConfig.MCP_DESCRIPTIONS:
                print(f"  ({MCPRouterConfig.MCP_DESCRIPTIONS[prediction]})")
            print()
            
    except Exception as e:
        logger.error(f"Error in main execution: {str(e)}")
        raise

if __name__ == "__main__":
    main()
