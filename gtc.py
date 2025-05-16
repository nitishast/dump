import json
import os
from typing import Dict, List, Optional, Any, Tuple
import yaml
from datetime import datetime
import logging
import re
from src import llm  # This import was present in both

# Set up logging (from new script, with mode='a')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/test_generation.log', mode='a'), # Kept mode='a' from new script
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
        # Taken from new script (updated Date formats, added Boolean)
        return {
            "Date": {
                "valid_formats": [
                    "%Y-%m-%d %H:%M:%S.%f",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d",
                    "%Y/%m/%d",
                    "%m/%d/%Y"
                ],
                "extra_validation": self._validate_date_format
            },
            "String": {
                "extra_validation": self._validate_string_format
            },
            "Boolean": { # New from new script
                "extra_validation": self._validate_boolean_format
            }
        }

    def _validate_date_format(self, test_case: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate date format test cases."""
        # Logic is same as old, uses updated self.field_specific_rules
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
        # Logic from new script (effectively same as old)
        if test_case["input"] is None:
            return True, ""

        if not isinstance(test_case["input"], (str, type(None))):
            if test_case["expected_result"] == "Pass":
                return False, "String field with non-string input should fail"
        return True, ""

    # New method from new script
    def _validate_boolean_format(self, test_case: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate boolean format test cases."""
        if test_case["input"] is None:
            return True, ""
            
        valid_booleans = [True, False, "True", "False", "true", "false", 1, 0] # true/false strings and 1/0 added
        # Logic from new script:
        if test_case["expected_result"] == "Pass" and test_case["input"] not in valid_booleans:
            return False, f"Boolean field with non-boolean input should fail. Valid values: {valid_booleans}"
        return True, ""

    # New method from new script
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
        
        if not business_rules or business_rules.strip() == "":
            return rule_info
            
        if "cannot be null" in business_rules.lower() or "cannot be blank" in business_rules.lower():
            rule_info["is_nullable"] = False
            rule_info["validation_rules"].append("Field cannot be null or blank")
            
        if "format" in business_rules.lower():
            format_lines = [line for line in business_rules.split("\n") if "format" in line.lower()]
            for line in format_lines:
                rule_info["required_formats"].append(line.strip())
        
        if "must be" in business_rules.lower() or "should be" in business_rules.lower():
            constraint_lines = [line for line in business_rules.split("\n") 
                              if "must be" in line.lower() or "should be" in line.lower()]
            for line in constraint_lines:
                if "null" not in line.lower() and "blank" not in line.lower():
                    rule_info["value_constraints"].append(line.strip())
        
        if "transform" in business_rules.lower() or "concatenation" in business_rules.lower():
            transform_lines = [line for line in business_rules.split("\n") 
                             if "transform" in line.lower() or "concatenation" in line.lower()]
            for line in transform_lines:
                rule_info["transformation_rules"].append(line.strip())
                
        if "if " in business_rules.lower() or "when " in business_rules.lower():
            conditional_lines = [line for line in business_rules.split("\n") 
                               if "if " in line.lower() or "when " in line.lower()]
            for line in conditional_lines:
                rule_info["conditional_logic"].append(line.strip())
                
        if "concatenation" in business_rules.lower() and "salesforceLeadID" in business_rules:
            concat_rules = [line for line in business_rules.split("\n") 
                          if "concatenation" in line.lower() and "salesforceLeadID" in line]
            if concat_rules:
                rule_info["transformation_rules"].extend(concat_rules)
                
        return rule_info

    # Updated method signature and logic from new script
    def _generate_prompt(self, field_name: str, data_type: str, mandatory_field: bool, primary_key: bool,
                         business_rules: str, expected_values: str = "") -> str:
        """Generate a more structured and specific prompt for test case generation with improved business rule analysis."""
        field_specific_info = ""
        
        if expected_values and expected_values.strip():
            field_specific_info += f"\nExpected Values: {expected_values}"
            
        if data_type == "Date":
            field_specific_info += "\nFor Date fields, use these formats only:\n" + \
                                  "\n".join(f"- {fmt}" for fmt in self.field_specific_rules["Date"]["valid_formats"])
        elif data_type == "Boolean":
            field_specific_info += "\nFor Boolean fields, use values: True, False, true, false, 1, 0"
        
        rule_analysis = self._analyze_business_rules(field_name, business_rules)
        
        test_case_categories = []
        test_case_categories.append("Basic valid inputs")
        test_case_categories.append("Basic invalid inputs")
        
        if mandatory_field or not rule_analysis["is_nullable"]:
            test_case_categories.append("Null handling (should fail for mandatory fields)")
        else:
            test_case_categories.append("Null handling (should pass for optional fields)")
            
        if rule_analysis["required_formats"]:
            test_case_categories.append("Format validation (testing required formats)")
            
        if rule_analysis["value_constraints"]:
            test_case_categories.append("Value constraint validation")
            
        if rule_analysis["transformation_rules"]:
            test_case_categories.append("Data transformation validation")
            
        if rule_analysis["conditional_logic"]:
            test_case_categories.append("Conditional logic validation")
            
        if primary_key:
            test_case_categories.append("Primary key validation (uniqueness)")
            
        rule_analysis_text = ""
        if rule_analysis["required_formats"]:
            rule_analysis_text += "\nFormat Requirements:"
            for format_rule in rule_analysis["required_formats"]:
                rule_analysis_text += f"\n- {format_rule}"
        if rule_analysis["value_constraints"]:
            rule_analysis_text += "\nValue Constraints:"
            for constraint in rule_analysis["value_constraints"]:
                rule_analysis_text += f"\n- {constraint}"
        if rule_analysis["transformation_rules"]:
            rule_analysis_text += "\nTransformation Rules:"
            for transform in rule_analysis["transformation_rules"]:
                rule_analysis_text += f"\n- {transform}"
        if rule_analysis["conditional_logic"]:
            rule_analysis_text += "\nConditional Logic:"
            for condition in rule_analysis["conditional_logic"]:
                rule_analysis_text += f"\n- {condition}"
                
        categories_list = "\n".join(f"   - {category}" for category in test_case_categories)
        
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
        # Logic is same as old script
        if not all(field in test_case for field in ["test_case", "description", "expected_result", "input"]):
            return False, "Missing required fields"

        if test_case["expected_result"] not in ["Pass", "Fail"]:
            return False, "Invalid expected_result value"

        if data_type in self.field_specific_rules:
            # This will now correctly call _validate_boolean_format if data_type is "Boolean"
            return self.field_specific_rules[data_type]["extra_validation"](test_case)

        return True, ""

    def _parse_llm_response(self, response_text: str, data_type: str) -> Optional[List[Dict[str, Any]]]:
        """Parse and validate LLM response with improved error handling."""
        # Logic is same as old script
        try:
            cleaned_text = response_text.replace("```json", "").replace("```", "").strip()
            cleaned_text = re.sub(r'\\([^"\\])', r'\\\\\1', cleaned_text)
            test_cases = json.loads(cleaned_text)

            if not isinstance(test_cases, list):
                raise ValueError("Response is not a JSON array")

            validated_cases = []
            for idx, case in enumerate(test_cases, 1):
                is_valid, error_msg = self._validate_test_case(case, data_type)
                if not is_valid:
                    logging.warning(f"Test case {idx} validation failed: {error_msg}")
                    continue
                case["expected_result"] = "Pass" if case["expected_result"].lower() == "pass" else "Fail"
                validated_cases.append(case)
            return validated_cases
        except json.JSONDecodeError as e:
            logging.error(f"JSON parsing error: {str(e)} - Raw response: {response_text}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error parsing response: {str(e)}")
            return None

    # Method updated with logic from the first (more complete) version in the new script
    def generate_test_cases(self, rules_file: str, output_file: str, llm_client) -> None:
        """Main method to generate and save test cases."""
        try:
            with open(rules_file, "r") as f:
                rules = json.load(f)

            all_test_cases = {}
            total_fields = sum(len(details["fields"]) for details in rules.values())
            processed_fields = 0
            
            # Debug logging from new script
            logging.info("Checking business rules content for multi-line entries:")
            count = 0
            stop_debug_logging = False
            for parent_field, details in rules.items():
                if stop_debug_logging: break
                for field_name, field_details in details["fields"].items():
                    business_rules_debug = field_details.get("business_rules", "")
                    lines_debug = business_rules_debug.count('\n') + 1 if business_rules_debug else 0
                    if lines_debug > 1:
                        logging.info(f"Field {parent_field}.{field_name} has multi-line business rules ({lines_debug} lines)")
                        logging.debug(f"Business rules for {parent_field}.{field_name}: {business_rules_debug}")
                    count += 1
                    if count >= 5:
                        stop_debug_logging = True
                        break
            
            for parent_field, details in rules.items():
                for field_name, field_details in details["fields"].items():
                    full_field_name = f"{parent_field}.{field_name}"
                    logging.info(f"Processing field {processed_fields + 1}/{total_fields}: {full_field_name}")
                    if full_field_name in all_test_cases:
                        logging.warning(f"Skipping {full_field_name}, already processed.")
                        continue

                    expected_values = field_details.get("expected_values", "") # From new script
                    business_rules = field_details.get("business_rules", "") # From new script (explicitly)
                    
                    # Logging from new script
                    lines = business_rules.count('\n') + 1 if business_rules else 0
                    if lines > 1:
                        logging.info(f"Field {full_field_name} has {lines} lines of business rules")
                    
                    # Call to updated _generate_prompt (includes expected_values)
                    prompt = self._generate_prompt(
                        field_name,
                        field_details["data_type"],
                        field_details["mandatory_field"],
                        field_details["primary_key"],
                        business_rules, # Passed explicitly
                        expected_values  # New argument
                    )

                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            response_text = llm.generate_test_cases_with_llm(llm_client, prompt,
                                                                               self.config.get("max_output_tokens", 1000))
                            test_cases = self._parse_llm_response(response_text, field_details["data_type"])

                            if test_cases:
                                all_test_cases[full_field_name] = test_cases
                                logging.info(f"Successfully generated {len(test_cases)} test cases for {full_field_name}") # Enhanced logging
                                break
                            else:
                                logging.warning(f"Attempt {attempt + 1} for {full_field_name}: Failed to generate valid test cases from LLM response.")
                        except Exception as e:
                            logging.error(f"Attempt {attempt + 1} for {full_field_name} failed: {str(e)}")
                            if attempt == max_retries - 1:
                                logging.error(f"Failed to generate test cases for {full_field_name} after {max_retries} attempts.")
                    processed_fields += 1

            self._save_test_cases(all_test_cases, output_file)

            if total_fields > 0:
                self._generate_summary(all_test_cases, output_file) # Call to updated summary
            else:
                logging.warning("No fields were processed, skipping summary generation.")

        except Exception as e:
            logging.error(f"Failed to generate test cases: {str(e)}")
            raise

    def _save_test_cases(self, test_cases: Dict[str, List[Dict[str, Any]]], output_file: str) -> None:
        """Save test cases with backup."""
        try:
            # Ensure output directory exists (from new script)
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            if os.path.exists(output_file):
                backup_file = f"{output_file}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
                os.rename(output_file, backup_file)
                logging.info(f"Created backup: {backup_file}")

            with open(output_file, "w") as f:
                json.dump(test_cases, f, indent=2)
            logging.info(f"Successfully saved test cases to {output_file}")
        except Exception as e:
            logging.error(f"Failed to save test cases: {str(e)}")
            raise

    # Method updated with logic from new script
    def _generate_summary(self, test_cases: Dict[str, List[Dict[str, Any]]], output_file: str) -> None:
        """Generate a summary of the test case generation."""
        total_fields = len(test_cases)
        if total_fields == 0: # Guard against division by zero if no test cases were actually generated for fields
            logging.warning("No test cases found to generate a summary for.")
            summary = (
                f"\nTest Case Generation Summary\n"
                f"{'=' * 30}\n"
                f"Total fields processed (targeted): {total_fields} (based on input rules potentially)\n"
                f"Total test cases generated: 0\n"
                f"Output file: {output_file}\n"
                f"{'=' * 30}"
            )
        else:
            total_test_cases = sum(len(cases) for cases in test_cases.values())
            if total_test_cases == 0: # If fields were processed but no test cases generated
                 summary = (
                    f"\nTest Case Generation Summary\n"
                    f"{'=' * 30}\n"
                    f"Total fields processed: {total_fields}\n"
                    f"Total test cases generated: {total_test_cases}\n"
                    f"Output file: {output_file}\n"
                    f"{'=' * 30}"
                )
            else:
                pass_count = sum(1 for cases in test_cases.values() for case in cases if case["expected_result"] == "Pass")
                fail_count = total_test_cases - pass_count
            
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
        
        try:
            summary_file = f"{os.path.splitext(output_file)[0]}_summary.txt"
            with open(summary_file, "w") as f:
                f.write(summary)
            logging.info(f"Summary written to {summary_file}")
        except Exception as e:
            logging.error(f"Failed to write summary file: {e}")

# main function structure from new script (config is optional)
def main(config=None):
    """Main function to run the test case generation."""
    try:
        if config is None:
            config_path = "config/settings.yaml" # Default config path
            try:
                with open(config_path, "r") as f:
                    config = yaml.safe_load(f)
                logging.info(f"Loaded configuration from {config_path}")
            except Exception as e:
                logging.error(f"Failed to load config from {config_path}: {str(e)}")
                raise
        
        # TestCaseGenerator will load its own config from its default path
        # if its config_path argument is not overridden.
        # The 'config' dict loaded here is primarily for llm.initialize_llm
        generator = TestCaseGenerator() 
        llm_client = llm.initialize_llm(config) # config dict passed here
        
        generator.generate_test_cases(
            generator.config["processed_rules_file"],
            generator.config["generated_test_cases_file"],
            llm_client
        )
    except Exception as e:
        # Log the full traceback for better debugging
        logging.error(f"Application failed: {str(e)}", exc_info=True)
        # Re-raise to indicate failure to the caller/environment
        raise

if __name__ == "__main__":
    main()
