import dspy
from dotenv import load_dotenv
import os
import random
import pandas as pd
from typing import List, Dict, Tuple, Optional
from dspy.evaluate import Evaluate
from dspy.teleprompt import BootstrapFewShot
import logging
from dataclasses import dataclass
import time
from langchain_openai import ChatOpenAI
import warnings

# Suppress noisy LiteLLM errors as discussed
logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)
os.environ["LITELLM_LOG"] = "CRITICAL"
warnings.filterwarnings("ignore", category=UserWarning, module="litellm")

# Set up clean logging for our experiment
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()
key = os.getenv('OPENAI_API_KEY')

@dataclass
class RoutingComparison:
    """
    Comprehensive comparison result that captures performance of both approaches
    on the same query. This is the heart of our comparative analysis.
    """
    # Required fields (no default values) - these must come first
    query: str
    actual_destination: str
    dspy_prediction: str
    dspy_correct: bool
    dspy_response_time: float
    zeroshot_prediction: str
    zeroshot_correct: bool
    zeroshot_response_time: float
    
    # Optional fields (with default values) - these must come last
    dspy_error: Optional[str] = None
    zeroshot_error: Optional[str] = None
    both_correct: bool = None
    both_wrong: bool = None
    dspy_better: bool = None
    zeroshot_better: bool = None
    
    def __post_init__(self):
        """Calculate comparative metrics automatically"""
        self.both_correct = self.dspy_correct and self.zeroshot_correct
        self.both_wrong = not self.dspy_correct and not self.zeroshot_correct
        self.dspy_better = self.dspy_correct and not self.zeroshot_correct
        self.zeroshot_better = self.zeroshot_correct and not self.dspy_correct

class MCPRouterConfig:
    """
    Centralized configuration that both approaches will use.
    This ensures we're comparing approaches on exactly the same problem definition.
    """
    
    # These match your original DESTINATIONS exactly
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
    
    # Valid destinations for routing (excluding reset_mode)
    VALID_DESTINATIONS = [key for key in DESTINATIONS.keys() if key != 'reset_mode']
    
    @classmethod
    def get_valid_destinations_string(cls) -> str:
        """Format valid destinations for prompts"""
        return "', '".join(cls.VALID_DESTINATIONS)

class ZeroShotMCPRouter:
    """
    Adapter class that wraps your original zero-shot routing logic
    in a standardized interface for systematic comparison.
    """
    
    def __init__(self, api_key: str, model_name: str = "gpt-4o"):
        """Initialize the zero-shot router with your original approach"""
        self.llm = ChatOpenAI(
            model=model_name, 
            api_key=api_key, 
            temperature=0  # Match your original configuration
        )
    
    def _build_routing_prompt(self, user_input: str) -> str:
        """
        Your original prompt building logic, exactly as you implemented it.
        This preserves the careful prompt engineering you developed.
        """
        # Get valid destination options (excluding reset_mode) 
        valid_options = MCPRouterConfig.VALID_DESTINATIONS
        options_list = ', '.join(valid_options)
        
        # Your original multi-line prompt for maximum clarity
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
    
    def _validate_destination(self, raw_destination: str) -> str:
        """
        Your original validation logic with the same fallback behavior.
        This preserves the robustness you built into your original system.
        """
        # Clean the response
        cleaned = raw_destination.strip().lower()
        
        # Check if it's a valid destination
        if cleaned in MCPRouterConfig.VALID_DESTINATIONS:
            return cleaned
        
        # Try partial matching (your original logic)
        for valid_dest in MCPRouterConfig.VALID_DESTINATIONS:
            if valid_dest in cleaned:
                logger.debug(f"Zero-shot: Found partial match '{valid_dest}' for '{cleaned}'")
                return valid_dest
        
        # Default fallback
        logger.warning(f"Zero-shot: Invalid destination '{cleaned}', defaulting to 'unknown'")
        return "unknown"
    
    def route_query(self, user_query: str) -> str:
        """
        Your original routing logic adapted for systematic evaluation.
        This maintains the exact same decision-making process you developed.
        """
        prompt = self._build_routing_prompt(user_query)
        result = self.llm.invoke(prompt)
        raw_destination = result.content.strip().lower()
        validated_destination = self._validate_destination(raw_destination)
        return validated_destination

class DSPyMCPRouter:
    """
    DSPy router implementation that matches your zero-shot problem exactly.
    This ensures we're comparing like with like.
    """
    
    class MCPSignature(dspy.Signature):
        """DSPy signature that mirrors the zero-shot classification task"""
        user_query = dspy.InputField(desc="User query to be routed to appropriate MCP server")
        target_destination = dspy.OutputField(
            desc=f"MCP server destination. Must be one of: {MCPRouterConfig.get_valid_destinations_string()}"
        )
    
    def __init__(self, api_key: str, model_name: str = "openai/gpt-4o"):
        """Initialize DSPy with the same model as zero-shot for fair comparison"""
        self.lm = dspy.LM(model_name, api_key=api_key, temperature=0)
        dspy.configure(lm=self.lm)
        
        self.base_router = dspy.Predict(self.MCPSignature)
        self.compiled_router = None
    
    def route_query(self, user_query: str) -> str:
        """Route a query using the current router (base or compiled)"""
        router = self.compiled_router if self.compiled_router else self.base_router
        try:
            prediction = router(user_query=user_query)
            return prediction.target_destination.strip().lower()
        except Exception as e:
            logger.error(f"DSPy routing error: {e}")
            return "unknown"

class UnifiedMCPComparison:
    """
    The main experimental framework that orchestrates comparison between
    DSPy optimization and zero-shot prompt engineering approaches.
    """
    
    def __init__(self, api_key: str = None, model_name: str = "gpt-4o"):
        """
        Initialize both routing approaches with identical configurations.
        This ensures that differences in performance come from the approaches, not the setup.
        """
        if api_key is None:
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OpenAI API key required for comparison")
        
        # Initialize both approaches with identical model configurations
        self.zero_shot_router = ZeroShotMCPRouter(api_key, model_name)
        self.dspy_router = DSPyMCPRouter(api_key, f"openai/{model_name}")
        
        # Store test data and results
        self.test_examples = []
        self.comparison_results = []
        
        logger.info(f"Initialized unified comparison with {model_name}")
    
    def create_comprehensive_test_data(self) -> List[dspy.Example]:
        """
        Create test data that thoroughly exercises both routing approaches.
        This uses the same comprehensive test data from the DSPy implementation.
        """
        
        # Internet search queries
        internet_queries = [
            "What's the current weather in New York?",
            "Find me the latest news about artificial intelligence", 
            "Search for information about Python programming best practices",
            "What are the top restaurants in San Francisco?",
            "Look up the stock price of Apple",
            "Find recent articles about machine learning",
            "Search for tutorial on React development"
        ]
        
        # GitHub queries
        github_queries = [
            "Show me my latest commits on the main branch in GitHub",
            "List all open pull requests in the backend repository",
            "Review pull request #102 from user_xyz", 
            "Compare branches 'feature/new-ui' and 'develop' in GitHub",
            "Find the commit history for the authentication module",
            "Search for repositories related to machine learning",
            "Show me issues labeled as 'bug' in the project"
        ]
        
        # Atlassian/JIRA queries
        atlassian_queries = [
            "Create a new issue in Jira for bug tracking",
            "Assign task PROJ-456 to me in the Jira project",
            "Search for issues containing 'authentication failure' in Jira", 
            "Update the priority of ticket PROJ-123 to high",
            "Move issue to 'In Progress' status in our sprint",
            "Find all tickets assigned to the backend team",
            "Show me the burndown chart for current sprint"
        ]
        
        # General AI queries
        general_queries = [
            "Explain quantum computing in simple terms",
            "What is the capital of France?",
            "Help me brainstorm ideas for a presentation",
            "Tell me a random fact about space", 
            "How do solar panels work?",
            "What's the difference between AI and machine learning?",
            "Summarize the concept of blockchain technology"
        ]
        
        # Email assistant queries
        email_queries = [
            "Help me write a professional email to my boss",
            "Draft an email to schedule a meeting with the team",
            "Compose a follow-up email for the client proposal",
            "Write an email declining a meeting invitation politely",
            "Help me respond to this customer complaint email", 
            "Draft a thank you email after the interview",
            "Write an email requesting time off"
        ]
        
        # Google Maps queries
        maps_queries = [
            "Find directions to the nearest coffee shop",
            "What's the traffic like on Highway 101?",
            "Show me restaurants near downtown Seattle",
            "Find parking near the convention center",
            "Get directions from home to the airport",
            "Search for gas stations along my route", 
            "Find hotels near Times Square"
        ]
        
        # Knowledge base queries
        knowledge_base_queries = [
            "Search our knowledge base for user interaction patterns",
            "Find information about customer feedback trends",
            "Look up user engagement metrics in our database",
            "Search for product usage analytics in our system",
            "Find customer support ticket patterns",
            "Look up user onboarding completion rates",
            "Search for feature adoption metrics"
        ]
        
        # SQLite database queries
        sqlite_queries = [
            "Query the Chinook database for sales data",
            "Find all customers in the SQLite database from California", 
            "Search the database for top-selling albums",
            "Get employee information from the Chinook database",
            "Find invoice totals by country in our SQLite DB",
            "Query track information from the music database",
            "Search for customer purchase history in Chinook"
        ]
        
        # Ambiguous/unknown queries
        unknown_queries = [
            "Help me with this thing",
            "Can you do something about the issue?",
            "I need assistance with the problem",
            "Fix this for me",
            "Handle this request",
            "Process this information",
            "Deal with this situation"
        ]
        
        # Create labeled examples
        all_examples = []
        
        def add_examples(queries, destination):
            for query in queries:
                example = dspy.Example(
                    user_query=query,
                    target_destination=destination
                ).with_inputs("user_query")
                all_examples.append(example)
        
        # Add all categories with their correct labels
        add_examples(internet_queries, 'search_internet')
        add_examples(github_queries, 'search_github')
        add_examples(atlassian_queries, 'search_atlassian')
        add_examples(general_queries, 'general_ai_response')
        add_examples(email_queries, 'email_assistant')
        add_examples(maps_queries, 'search_google_maps')
        add_examples(knowledge_base_queries, 'search_knowledge_base')
        add_examples(sqlite_queries, 'search_sqlite')
        add_examples(unknown_queries, 'unknown')
        
        logger.info(f"Created {len(all_examples)} test examples for unified comparison")
        return all_examples
    
    def train_dspy_router(self, train_examples: List[dspy.Example]) -> None:
        """
        Train the DSPy router using the systematic optimization approach.
        This represents the automated prompt optimization philosophy.
        """
        logger.info("Training DSPy router with systematic optimization...")
        
        def accuracy_metric(gold, pred, trace=None):
            """Accuracy metric that matches both approaches"""
            if not pred or not hasattr(pred, 'target_destination'):
                return 0.0
            
            predicted = str(pred.target_destination).strip().lower()
            actual = str(gold.target_destination).strip().lower()
            
            return float(predicted == actual)
        
        # Configure optimizer for multi-class classification
        optimizer = BootstrapFewShot(
            metric=accuracy_metric,
            max_bootstrapped_demos=15,  # More demos for 9-class problem
            max_labeled_demos=25
        )
        
        # Compile the router
        self.dspy_router.compiled_router = optimizer.compile(
            self.dspy_router.base_router,
            trainset=train_examples
        )
        
        logger.info("DSPy router training completed")
    
    def evaluate_single_query(self, query: str, actual_destination: str) -> RoutingComparison:
        """
        Evaluate both approaches on a single query with detailed timing and error tracking.
        This is where the direct comparison happens.
        """
        
        # Test DSPy approach
        dspy_start_time = time.time()
        try:
            dspy_prediction = self.dspy_router.route_query(query)
            dspy_response_time = time.time() - dspy_start_time
            dspy_error = None
        except Exception as e:
            dspy_prediction = "unknown"
            dspy_response_time = time.time() - dspy_start_time
            dspy_error = str(e)
            logger.error(f"DSPy error on '{query}': {e}")
        
        # Test zero-shot approach  
        zeroshot_start_time = time.time()
        try:
            zeroshot_prediction = self.zero_shot_router.route_query(query)
            zeroshot_response_time = time.time() - zeroshot_start_time
            zeroshot_error = None
        except Exception as e:
            zeroshot_prediction = "unknown"
            zeroshot_response_time = time.time() - zeroshot_start_time
            zeroshot_error = str(e)
            logger.error(f"Zero-shot error on '{query}': {e}")
        
        # Create comprehensive comparison result
        return RoutingComparison(
            query=query,
            actual_destination=actual_destination,
            dspy_prediction=dspy_prediction,
            dspy_correct=(dspy_prediction == actual_destination),
            dspy_response_time=dspy_response_time,
            dspy_error=dspy_error,
            zeroshot_prediction=zeroshot_prediction,
            zeroshot_correct=(zeroshot_prediction == actual_destination),
            zeroshot_response_time=zeroshot_response_time,
            zeroshot_error=zeroshot_error
        )
    
    def run_comprehensive_comparison(self) -> Tuple[pd.DataFrame, Dict]:
        """
        Execute the complete comparative analysis between both approaches.
        This is your main experimental method.
        """
        logger.info("Starting comprehensive MCP routing comparison...")
        
        # Step 1: Create test data
        all_examples = self.create_comprehensive_test_data()
        
        # Step 2: Split data strategically (stratified by destination)
        train_examples, test_examples = self._split_data_strategically(all_examples)
        self.test_examples = test_examples
        
        # Step 3: Train DSPy router (zero-shot needs no training)
        self.train_dspy_router(train_examples)
        
        # Step 4: Evaluate both approaches on identical test data
        logger.info(f"Evaluating both approaches on {len(test_examples)} test queries...")
        
        comparison_results = []
        for i, example in enumerate(test_examples):
            if i % 10 == 0:  # Progress indicator
                logger.info(f"Processing query {i+1}/{len(test_examples)}")
            
            result = self.evaluate_single_query(
                example.user_query, 
                example.target_destination
            )
            comparison_results.append(result)
        
        self.comparison_results = comparison_results
        
        # Step 5: Analyze results comprehensively
        return self._analyze_comparative_results()
    
    def _split_data_strategically(self, examples: List[dspy.Example], train_ratio: float = 0.7) -> Tuple[List[dspy.Example], List[dspy.Example]]:
        """Stratified split to ensure balanced representation in train/test"""
        
        # Group by destination for balanced splitting
        examples_by_dest = {}
        for ex in examples:
            dest = ex.target_destination
            if dest not in examples_by_dest:
                examples_by_dest[dest] = []
            examples_by_dest[dest].append(ex)
        
        train_set, test_set = [], []
        
        for dest, dest_examples in examples_by_dest.items():
            random.shuffle(dest_examples)
            split_idx = int(len(dest_examples) * train_ratio)
            train_set.extend(dest_examples[:split_idx])
            test_set.extend(dest_examples[split_idx:])
        
        random.shuffle(train_set)
        random.shuffle(test_set)
        
        logger.info(f"Data split: {len(train_set)} training, {len(test_set)} testing examples")
        return train_set, test_set
    
    def _analyze_comparative_results(self) -> Tuple[pd.DataFrame, Dict]:
        """
        Comprehensive analysis of comparative performance.
        This is where the scientific insights are extracted.
        """
        
        # Create detailed results DataFrame
        results_data = []
        for result in self.comparison_results:
            results_data.append({
                'query': result.query,
                'actual_destination': result.actual_destination,
                'dspy_prediction': result.dspy_prediction,
                'dspy_correct': result.dspy_correct,
                'dspy_response_time': result.dspy_response_time,
                'zeroshot_prediction': result.zeroshot_prediction,
                'zeroshot_correct': result.zeroshot_correct,
                'zeroshot_response_time': result.zeroshot_response_time,
                'both_correct': result.both_correct,
                'both_wrong': result.both_wrong,
                'dspy_better': result.dspy_better,
                'zeroshot_better': result.zeroshot_better
            })
        
        results_df = pd.DataFrame(results_data)
        
        # Calculate comprehensive statistics
        total_queries = len(self.comparison_results)
        
        # Overall accuracy comparison
        dspy_accuracy = results_df['dspy_correct'].mean()
        zeroshot_accuracy = results_df['zeroshot_correct'].mean()
        
        # Comparative performance analysis
        both_correct = results_df['both_correct'].sum()
        both_wrong = results_df['both_wrong'].sum()
        dspy_better = results_df['dspy_better'].sum()
        zeroshot_better = results_df['zeroshot_better'].sum()
        
        # Performance by category
        category_analysis = results_df.groupby('actual_destination').agg({
            'dspy_correct': ['count', 'sum', 'mean'],
            'zeroshot_correct': ['sum', 'mean'],
            'dspy_response_time': 'mean',
            'zeroshot_response_time': 'mean'
        }).round(4)
        
        # Summary statistics
        summary_stats = {
            'total_test_queries': total_queries,
            'dspy_overall_accuracy': dspy_accuracy,
            'zeroshot_overall_accuracy': zeroshot_accuracy,
            'accuracy_difference': dspy_accuracy - zeroshot_accuracy,
            'both_correct_count': both_correct,
            'both_correct_percent': both_correct / total_queries * 100,
            'both_wrong_count': both_wrong,
            'both_wrong_percent': both_wrong / total_queries * 100,
            'dspy_better_count': dspy_better,
            'dspy_better_percent': dspy_better / total_queries * 100,
            'zeroshot_better_count': zeroshot_better,
            'zeroshot_better_percent': zeroshot_better / total_queries * 100,
            'avg_dspy_response_time': results_df['dspy_response_time'].mean(),
            'avg_zeroshot_response_time': results_df['zeroshot_response_time'].mean(),
            'category_performance': category_analysis
        }
        
        return results_df, summary_stats

def main():
    """
    Main execution function that runs the complete comparative analysis
    and produces comprehensive results for scientific analysis.
    """
    try:
        # Initialize the unified comparison framework
        comparison = UnifiedMCPComparison(api_key=key)
        
        # Run the comprehensive comparison
        results_df, summary_stats = comparison.run_comprehensive_comparison()
        
        # Display results in a structured format
        print("\n" + "="*80)
        print("UNIFIED MCP ROUTING COMPARISON RESULTS")
        print("="*80)
        print(f"Total Test Queries: {summary_stats['total_test_queries']}")
        print(f"DSPy Overall Accuracy: {summary_stats['dspy_overall_accuracy']:.4f}")
        print(f"Zero-Shot Overall Accuracy: {summary_stats['zeroshot_overall_accuracy']:.4f}")
        print(f"Accuracy Difference (DSPy - Zero-Shot): {summary_stats['accuracy_difference']:.4f}")
        
        print(f"\nComparative Performance Breakdown:")
        print(f"Both Correct: {summary_stats['both_correct_count']} ({summary_stats['both_correct_percent']:.1f}%)")
        print(f"Both Wrong: {summary_stats['both_wrong_count']} ({summary_stats['both_wrong_percent']:.1f}%)")
        print(f"DSPy Better: {summary_stats['dspy_better_count']} ({summary_stats['dspy_better_percent']:.1f}%)")
        print(f"Zero-Shot Better: {summary_stats['zeroshot_better_count']} ({summary_stats['zeroshot_better_percent']:.1f}%)")
        
        print(f"\nResponse Time Comparison:")
        print(f"Average DSPy Response Time: {summary_stats['avg_dspy_response_time']:.3f} seconds")
        print(f"Average Zero-Shot Response Time: {summary_stats['avg_zeroshot_response_time']:.3f} seconds")
        
        print(f"\nPer-Category Performance:")
        print(summary_stats['category_performance'])
        
        # Save detailed results for further analysis
        results_df.to_csv('unified_mcp_comparison_results.csv', index=False)
        print(f"\nDetailed results saved to 'unified_mcp_comparison_results.csv'")
        
        print(f"\nSample of detailed comparisons:")
        print(results_df[['query', 'actual_destination', 'dspy_prediction', 'zeroshot_prediction', 
                         'dspy_correct', 'zeroshot_correct']].head(10).to_string(index=False))
        
        return results_df, summary_stats
        
    except Exception as e:
        logger.error(f"Comparison failed: {e}")
        raise

if __name__ == "__main__":
    results_df, summary_stats = main()
