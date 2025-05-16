import json
import os
from typing import Dict, List, Optional, Any, Tuple
import yaml
from datetime import datetime
import logging
import re
from src import llm  # Added IMPORT

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/test_generation.log', mode='a'),
        logging.StreamHandler()
    ]
)

class TestCaseGenerator:
    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config = self._load_config(config_path)
        self.field_specific_rules = self._initialize_field_rules()

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file with error handling."""
        try:
            with open(config_path, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logging.error(f"Failed to load config: {str(e)}")
            raise

    def _initialize_field_rules(self) -> Dict[str, Dict[str, Any]]:
        """Initialize specific rules for different field types."""
        return {
            "Date": {
                "valid_formats": [
                    "%Y-%m-%d %H:%M:%S.%f", # added for 3 places after seconds 
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d",  # Added simple date format
                    "%Y/%m/%d",  # Added alternative date format
                    "%m/%d/%Y"   # Added US date format
                ],
                "extra_validation": self._validate_date_format
            },
            "String": {
                "extra_validation": self._validate_string_format
            },
            "Boolean": {
                "extra_validation": self._validate_boolean_format
            }
        }

    def _validate_date_format(self, test_case: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate date format test cases."""
        if test_case["input"] is None:
            return True, ""

        if isinstance(test_case["input"], str):
            for date_format in self.field_specific_rules["Date"]["valid_formats"]:
                try:
                    datetime.strptime(test_case["input"], date_format)
                    return True, ""
                except ValueError:
                    continue
            return False, f"Invalid date format. Expected formats: {self.field_specific_rules['Date']['valid_formats']}"
        return False, "Date input must be a string"

    def _validate_string_format(self, test_case: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate string format test cases."""
        if test_case["input"] is None:
            return True, ""

        if not isinstance(test_case["input"], (str, type(None))):
            if test_case["expected_result"] == "Pass":
                return False, "String field with non-string input should fail"
        return True, ""
    
    def _validate_boolean_format(self, test_case: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate boolean format test cases."""
        if test_case["input"] is None:
            return True, ""
            
        valid_booleans = [True, False, "True", "False", "true", "false", 1, 0]
        if test_case["expected_result"] == "Pass" and test_case["input"] not in valid_booleans:
            return False, f"Boolean field with non-boolean input should fail. Valid values: {valid_booleans}"
        return True, ""

    def _analyze_business_rules(self, field_name: str, business_rules: str) -> Dict[str, Any]:
        """
        Analyzes business rules to extract key information like:
        - Format requirements
        - Value constraints
        - Data relationships
        - Transformation rules
        - Conditional logic

        This helps generate more relevant test cases.
        """
        rule_info = {
            "is_nullable": True,
            "required_formats": [],
            "value_constraints": [],
            "validation_rules": [],
            "transformation_rules": [],
            "conditional_logic": []
        }
        
        # Skip empty rules
        if not business_rules or business_rules.strip() == "":
            return rule_info
            
        # Parse nullability
        if "cannot be null" in business_rules.lower() or "cannot be blank" in business_rules.lower():
            rule_info["is_nullable"] = False
            rule_info["validation_rules"].append("Field cannot be null or blank")
            
        # Look for format requirements
        if "format" in business_rules.lower():
            # E.g., "YYYY-MM-DD format" or "must be in expected format"
            format_lines = [line for line in business_rules.split("\n") if "format" in line.lower()]
            for line in format_lines:
                rule_info["required_formats"].append(line.strip())
        
        # Look for value constraints 
        if "must be" in business_rules.lower() or "should be" in business_rules.lower():
            constraint_lines = [line for line in business_rules.split("\n") 
                              if "must be" in line.lower() or "should be" in line.lower()]
            for line in constraint_lines:
                if "null" not in line.lower() and "blank" not in line.lower():  # Skip nullability constraints
                    rule_info["value_constraints"].append(line.strip())
        
        # Look for data transformation rules
        if "transform" in business_rules.lower() or "concatenation" in business_rules.lower():
            transform_lines = [line for line in business_rules.split("\n") 
                             if "transform" in line.lower() or "concatenation" in line.lower()]
            for line in transform_lines:
                rule_info["transformation_rules"].append(line.strip())
                
        # Look for conditional logic
        if "if " in business_rules.lower() or "when " in business_rules.lower():
            conditional_lines = [line for line in business_rules.split("\n") 
                               if "if " in line.lower() or "when " in line.lower()]
            for line in conditional_lines:
                rule_info["conditional_logic"].append(line.strip())
                
        # Search for specific patterns like salesforceLeadID concatenation
        if "concatenation" in business_rules.lower() and "salesforceLeadID" in business_rules:
            # This is an important transformation rule for the ID
            concat_rules = [line for line in business_rules.split("\n") 
                          if "concatenation" in line.lower() and "salesforceLeadID" in line]
            if concat_rules:
                rule_info["transformation_rules"].extend(concat_rules)
                
        return rule_info

    def _generate_prompt(self, field_name: str, data_type: str, mandatory_field: bool, primary_key: bool,
                         business_rules: str, expected_values: str = "") -> str:
        """Generate a more structured and specific prompt for test case generation with improved business rule analysis."""
        # Generate field-specific information
        field_specific_info = ""
        
        # Add expected values to field-specific info if available
        if expected_values and expected_values.strip():
            field_specific_info += f"\nExpected Values: {expected_values}"
            
        # Apply data type specific guidance
        if data_type == "Date":
            field_specific_info += "\nFor Date fields, use these formats only:\n" + \
                                  "\n".join(f"- {fmt}" for fmt in self.field_specific_rules["Date"]["valid_formats"])
        elif data_type == "Boolean":
            field_specific_info += "\nFor Boolean fields, use values: True, False, true, false, 1, 0"
        
        # Analyze business rules for more targeted test cases
        rule_analysis = self._analyze_business_rules(field_name, business_rules)
        
        # Build test case categories based on rule analysis
        test_case_categories = []
        
        # Basic categories
        test_case_categories.append("Basic valid inputs")
        test_case_categories.append("Basic invalid inputs")
        
        # Nullability test cases
        if mandatory_field or not rule_analysis["is_nullable"]:
            test_case_categories.append("Null handling (should fail for mandatory fields)")
        else:
            test_case_categories.append("Null handling (should pass for optional fields)")
            
        # Format-specific test cases
        if rule_analysis["required_formats"]:
            test_case_categories.append("Format validation (testing required formats)")
            
        # Value constraint test cases
        if rule_analysis["value_constraints"]:
            test_case_categories.append("Value constraint validation")
            
        # Transformation rule test cases
        if rule_analysis["transformation_rules"]:
            test_case_categories.append("Data transformation validation")
            
        # Conditional logic test cases
        if rule_analysis["conditional_logic"]:
            test_case_categories.append("Conditional logic validation")
            
        # Primary key specific test cases
        if primary_key:
            test_case_categories.append("Primary key validation (uniqueness)")
            
        # Specific rule analysis for the prompt
        rule_analysis_text = ""
        
        # Add format requirements
        if rule_analysis["required_formats"]:
            rule_analysis_text += "\nFormat Requirements:"
            for format_rule in rule_analysis["required_formats"]:
                rule_analysis_text += f"\n- {format_rule}"
                
        # Add value constraints
        if rule_analysis["value_constraints"]:
            rule_analysis_text += "\nValue Constraints:"
            for constraint in rule_analysis["value_constraints"]:
                rule_analysis_text += f"\n- {constraint}"
                
        # Add transformation rules
        if rule_analysis["transformation_rules"]:
            rule_analysis_text += "\nTransformation Rules:"
            for transform in rule_analysis["transformation_rules"]:
                rule_analysis_text += f"\n- {transform}"
                
        # Add conditional logic
        if rule_analysis["conditional_logic"]:
            rule_analysis_text += "\nConditional Logic:"
            for condition in rule_analysis["conditional_logic"]:
                rule_analysis_text += f"\n- {condition}"
                
        # Create categories list
        categories_list = "\n".join(f"   - {category}" for category in test_case_categories)
        
        # Final prompt assembly
        prompt = f"""
Generate test cases for the field '{field_name}' with following specifications:
- Data Type: {data_type}
- Mandatory: {mandatory_field}
- Primary Key: {primary_key}
- Business Rules: {business_rules}{field_specific_info}

Analyzed Business Rules:{rule_analysis_text}

Requirements:
1. Include ONLY the JSON array of test cases in your response
2. Each test case must have these exact fields:
   - "test_case": A clear, unique identifier for the test
   - "description": Detailed explanation of what the test verifies
   - "expected_result": MUST be exactly "Pass" or "Fail"
   - "input": The test input value (can be null, string, number, etc.)

3. Include these specific test categories:
{categories_list}

4. IMPORTANT: DO NOT create redundant test cases; focus on generating a concise set of tests 
   that cover all the business rules and data type requirements efficiently.

Return the response in this exact format:
[
    {{
        "test_case": "TC001_Valid_Basic",
        "description": "Basic valid input test",
        "expected_result": "Pass",
        "input": "example"
    }}
]

IMPORTANT: Return ONLY the JSON array. No additional text or explanation."""

        return prompt

    def _validate_test_case(self, test_case: Dict[str, Any], data_type: str) -> Tuple[bool, str]:
        """Validate a single test case based on field type and rules."""
        if not all(field in test_case for field in ["test_case", "description", "expected_result", "input"]):
            return False, "Missing required fields"

        if test_case["expected_result"] not in ["Pass", "Fail"]:
            return False, "Invalid expected_result value"

        # Apply field-specific validation
        if data_type in self.field_specific_rules:
            return self.field_specific_rules[data_type]["extra_validation"](test_case)

        return True, ""

    def _parse_llm_response(self, response_text: str, data_type: str) -> Optional[List[Dict[str, Any]]]:
        """Parse and validate LLM response with improved error handling."""
        try:
            # Remove Markdown JSON blocks if present
            cleaned_text = response_text.replace("```json", "").replace("```", "").strip()

            # Handle invalid escape sequences
            cleaned_text = re.sub(r'\\([^"\\])', r'\\\\\1', cleaned_text)

            # Parse JSON
            test_cases = json.loads(cleaned_text)

            # Validate structure
            if not isinstance(test_cases, list):
                raise ValueError("Response is not a JSON array")

            # Validate and normalize each test case
            validated_cases = []
            for idx, case in enumerate(test_cases, 1):
                is_valid, error_msg = self._validate_test_case(case, data_type)
                if not is_valid:
                    logging.warning(f"Test case {idx} validation failed: {error_msg}")
                    continue

                # Normalize expected_result to Pass/Fail
                case["expected_result"] = "Pass" if case["expected_result"].lower() == "pass" else "Fail"
                validated_cases.append(case)

            return validated_cases

        except json.JSONDecodeError as e:
            logging.error(f"JSON parsing error: {str(e)} - Raw response: {response_text}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error parsing response: {str(e)}")
            return None

    def generate_test_cases(self, rules_file: str, output_file: str, llm_client) -> None:
        """Main method to generate and save test cases."""
        try:
            # Load rules
            with open(rules_file, "r") as f:
                rules = json.load(f)

            all_test_cases = {}
            total_fields = sum(len(details["fields"]) for details in rules.values())
            processed_fields = 0
            
            # Debug: Print out first few business rules to verify multi-line content
            logging.info("Checking business rules content for multi-line entries:")
            count = 0
            for parent_field, details in rules.items():
                for field_name, field_details in details["fields"].items():
                    business_rules = field_details.get("business_rules", "")
                    lines = business_rules.count('\n') + 1 if business_rules else 0
                    if lines > 1:
                        logging.info(f"Field {parent_field}.{field_name} has multi-line business rules ({lines} lines)")
                        logging.debug(f"Business rules for {parent_field}.{field_name}: {business_rules}")
                    count += 1
                    if count >= 5:  # Just log the first few for debugging
                        break
                if count >= 5:
                    break

            for parent_field, details in rules.items():
                for field_name, field_details in details["fields"].items():
                    full_field_name = f"{parent_field}.{field_name}"
                    logging.info(f"Processing field {processed_fields + 1}/{total_fields}: {full_field_name}")
                    if full_field_name in all_test_cases:
                        logging.warning(f"Skipping {full_field_name}, already processed.")
                        continue

                    # Get expected values if available (new field)
                    expected_values = field_details.get("expected_values", "")
                    business_rules = field_details.get("business_rules", "")
                    
                    # Log the business rules content to verify multi-line content is preserved
                    lines = business_rules.count('\n') + 1 if business_rules else 0
                    if lines > 1:
                        logging.info(f"Field {full_field_name} has {lines} lines of business rules")
                    
                    # Generate prompt with additional expected_values parameter and improved business rules analysis
                    prompt = self._generate_prompt(
                        field_name,
                        field_details["data_type"],
                        field_details["mandatory_field"],
                        field_details["primary_key"],
                        business_rules,
                        expected_values
                    )

                    # Get LLM response with retries
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            response_text = llm.generate_test_cases_with_llm(llm_client, prompt,
                                                                               self.config.get("max_output_tokens",
                                                                                                 1000))
                            test_cases = self._parse_llm_response(response_text, field_details["data_type"])

                            if test_cases:
                                all_test_cases[full_field_name] = test_cases
                                logging.info(f"Successfully generated {len(test_cases)} test cases")
                                break
                            else:
                                logging.warning(f"Attempt {attempt + 1}: Failed to generate valid test cases")
                        except Exception as e:
                            logging.error(f"Attempt {attempt + 1} failed: {str(e)}")
                            if attempt == max_retries - 1:
                                logging.error(
                                    f"Failed to generate test cases for {full_field_name} after {max_retries} attempts")

                    processed_fields += 1

            # Save results
            self._save_test_cases(all_test_cases, output_file)

            # Generate summary
            if total_fields > 0:
                self._generate_summary(all_test_cases, output_file)
            else:
                logging.warning("No fields were processed, skipping summary generation.")

        except Exception as e:
            logging.error(f"Failed to generate test cases: {str(e)}")
            raise.warning(f"Skipping {full_field_name}, already processed.")
                        continue

                    # Get expected values if available (new field)
                    expected_values = field_details.get("expected_values", "")
                    
                    # Generate prompt with additional expected_values parameter
                    prompt = self._generate_prompt(
                        field_name,
                        field_details["data_type"],
                        field_details["mandatory_field"],
                        field_details["primary_key"],
                        field_details.get("business_rules", ""),
                        expected_values
                    )

                    # Get LLM response with retries
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            response_text = llm.generate_test_cases_with_llm(llm_client, prompt,
                                                                               self.config.get("max_output_tokens",
                                                                                                 1000))
                            test_cases = self._parse_llm_response(response_text, field_details["data_type"])

                            if test_cases:
                                all_test_cases[full_field_name] = test_cases
                                logging.info(f"Successfully generated {len(test_cases)} test cases")
                                break
                            else:
                                logging.warning(f"Attempt {attempt + 1}: Failed to generate valid test cases")
                        except Exception as e:
                            logging.error(f"Attempt {attempt + 1} failed: {str(e)}")
                            if attempt == max_retries - 1:
                                logging.error(
                                    f"Failed to generate test cases for {full_field_name} after {max_retries} attempts")

                    processed_fields += 1

            # Save results
            self._save_test_cases(all_test_cases, output_file)

            # Generate summary
            if total_fields > 0:
                self._generate_summary(all_test_cases, output_file)
            else:
                logging.warning("No fields were processed, skipping summary generation.")

        except Exception as e:
            logging.error(f"Failed to generate test cases: {str(e)}")
            raise

    def _save_test_cases(self, test_cases: Dict[str, List[Dict[str, Any]]], output_file: str) -> None:
        """Save test cases with backup."""
        try:
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            # Create backup of existing file if it exists
            if os.path.exists(output_file):
                backup_file = f"{output_file}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
                os.rename(output_file, backup_file)
                logging.info(f"Created backup: {backup_file}")

            # Save new test cases
            with open(output_file, "w") as f:
                json.dump(test_cases, f, indent=2)
            logging.info(f"Successfully saved test cases to {output_file}")

        except Exception as e:
            logging.error(f"Failed to save test cases: {str(e)}")
            raise

    def _generate_summary(self, test_cases: Dict[str, List[Dict[str, Any]]], output_file: str) -> None:
        """Generate a summary of the test case generation."""
        total_fields = len(test_cases)
        total_test_cases = sum(len(cases) for cases in test_cases.values())
        
        # Calculate pass/fail distribution
        pass_count = sum(1 for cases in test_cases.values() for case in cases if case["expected_result"] == "Pass")
        fail_count = total_test_cases - pass_count
        
        # Calculate test cases by data type
        data_types = {}
        for full_field_name, cases in test_cases.items():
            # Extract data type from the tests if available
            field_parts = full_field_name.split('.')
            if len(field_parts) >= 2:
                schema_name = field_parts[0]
                field_name = field_parts[1]
                # We don't have easy access to the data type here without re-reading rules
                # This would require refactoring to pass the rules object
                data_types[full_field_name] = len(cases)
        
        summary = (
            f"\nTest Case Generation Summary\n"
            f"{'=' * 30}\n"
            f"Total fields processed: {total_fields}\n"
            f"Total test cases generated: {total_test_cases}\n"
            f"  - Pass test cases: {pass_count} ({pass_count/total_test_cases*100:.1f}%)\n"
            f"  - Fail test cases: {fail_count} ({fail_count/total_test_cases*100:.1f}%)\n"
            f"Average test cases per field: {total_test_cases / total_fields:.2f}\n"
            f"Output file: {output_file}\n"
            f"{'=' * 30}"
        )

        logging.info(summary)
        
        # Additionally, write summary to a file for easier access
        try:
            summary_file = f"{os.path.splitext(output_file)[0]}_summary.txt"
            with open(summary_file, "w") as f:
                f.write(summary)
            logging.info(f"Summary written to {summary_file}")
        except Exception as e:
            logging.error(f"Failed to write summary file: {e}")

def main(config=None):
    """Main function to run the test case generation."""
    try:
        if config is None:
            # Load config from default location
            config_path = "config/settings.yaml"
            try:
                with open(config_path, "r") as f:
                    config = yaml.safe_load(f)
            except Exception as e:
                logging.error(f"Failed to load config: {str(e)}")
                raise
                
        generator = TestCaseGenerator()
        llm_client = llm.initialize_llm(config)
        generator.generate_test_cases(
            generator.config["processed_rules_file"],
            generator.config["generated_test_cases_file"],
            llm_client
        )
    except Exception as e:
        logging.error(f"Application failed: {str(e)}")
        raise

if __name__ == "__main__":
    main()
