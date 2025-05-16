import json
import os
from typing import Dict, List, Optional, Any, Tuple
import yaml
from datetime import datetime
import logging
import re
import csv # Added CSV import
from src import llm

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
            return False, f"Boolean field with non-boolean input ({test_case['input']}) should fail. Valid values: {valid_booleans}"
        return True, ""

    def _analyze_business_rules(self, field_name: str, business_rules: str) -> Dict[str, Any]:
        """
        Analyzes business rules to extract key information.
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
   - "input": The test input value (can be null, string, number, boolean etc.)

3. Include these specific test categories:
{categories_list}

4. IMPORTANT: DO NOT create redundant test cases; focus on generating a concise set of tests 
   that cover all the business rules and data type requirements efficiently.
5. For 'input' field: if the input is meant to be null or None, use the JSON null value (e.g., "input": null). Do not use the string "NULL".

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

        if data_type in self.field_specific_rules:
            return self.field_specific_rules[data_type]["extra_validation"](test_case)

        return True, ""

    def _parse_llm_response(self, response_text: str, data_type: str) -> Optional[List[Dict[str, Any]]]:
        """Parse and validate LLM response with improved error handling."""
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
                    logging.warning(f"Test case {idx} validation failed: {error_msg} - Case: {case}")
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

    def generate_test_cases(self, rules_file: str, output_file: str, llm_client) -> None:
        """Main method to generate and save test cases."""
        try:
            with open(rules_file, "r") as f:
                rules = json.load(f)

            all_test_cases = {}
            total_fields_in_rules = sum(len(details["fields"]) for details in rules.values()) # Renamed for clarity
            processed_fields_count = 0
            
            logging.info("Checking business rules content for multi-line entries (first 5 instances):")
            debug_count = 0
            stop_debug_logging = False
            for parent_field_debug, details_debug in rules.items():
                if stop_debug_logging: break
                for field_name_debug, field_details_debug in details_debug["fields"].items():
                    business_rules_debug = field_details_debug.get("business_rules", "")
                    lines_debug = business_rules_debug.count('\n') + 1 if business_rules_debug else 0
                    if lines_debug > 1:
                        logging.info(f"Field {parent_field_debug}.{field_name_debug} has multi-line business rules ({lines_debug} lines)")
                        # logging.debug(f"Business rules for {parent_field_debug}.{field_name_debug}: {business_rules_debug}") # Can be very verbose
                    debug_count += 1
                    if debug_count >= 5:
                        stop_debug_logging = True
                        break
            
            for parent_field, details in rules.items():
                for field_name, field_details in details["fields"].items():
                    full_field_name = f"{parent_field}.{field_name}"
                    logging.info(f"Processing field {processed_fields_count + 1}/{total_fields_in_rules}: {full_field_name}")
                    
                    if full_field_name in all_test_cases: # Should not happen if logic is correct, but good check
                        logging.warning(f"Skipping {full_field_name}, key already exists in all_test_cases.")
                        processed_fields_count +=1 # Increment even if skipped by this check
                        continue

                    expected_values = field_details.get("expected_values", "")
                    business_rules = field_details.get("business_rules", "")
                    
                    lines = business_rules.count('\n') + 1 if business_rules else 0
                    if lines > 1:
                        logging.info(f"Field {full_field_name} has {lines} lines of business rules being sent to LLM.")
                    
                    prompt = self._generate_prompt(
                        field_name,
                        field_details["data_type"],
                        field_details["mandatory_field"],
                        field_details["primary_key"],
                        business_rules,
                        expected_values
                    )

                    max_retries = self.config.get("llm_retries", 3)
                    generated_cases_for_field = None
                    for attempt in range(max_retries):
                        try:
                            response_text = llm.generate_test_cases_with_llm(
                                llm_client, 
                                prompt,
                                self.config.get("max_output_tokens", 1000)
                            )
                            if response_text:
                                generated_cases_for_field = self._parse_llm_response(response_text, field_details["data_type"])
                            else:
                                logging.warning(f"Attempt {attempt + 1}/{max_retries} for {full_field_name}: LLM returned empty response.")


                            if generated_cases_for_field: # Check if list is not empty
                                all_test_cases[full_field_name] = generated_cases_for_field
                                logging.info(f"Successfully generated {len(generated_cases_for_field)} test cases for {full_field_name}")
                                break
                            else:
                                logging.warning(f"Attempt {attempt + 1}/{max_retries} for {full_field_name}: Failed to generate or parse valid test cases. LLM response might be invalid or empty after parsing.")
                                if attempt == max_retries - 1:
                                     all_test_cases[full_field_name] = [] # Add empty list to mark as processed but failed
                                     logging.error(f"Failed to generate test cases for {full_field_name} after {max_retries} attempts. Storing empty list.")

                        except Exception as e:
                            logging.error(f"Attempt {attempt + 1}/{max_retries} for {full_field_name} failed with exception: {str(e)}", exc_info=True)
                            if attempt == max_retries - 1:
                                all_test_cases[full_field_name] = [] # Add empty list on final attempt exception
                                logging.error(f"Failed to generate test cases for {full_field_name} due to exception after {max_retries} attempts. Storing empty list.")
                    
                    processed_fields_count += 1

            self._save_test_cases(all_test_cases, output_file)
            self._save_test_cases_as_csv(all_test_cases, output_file) # New call

            # Pass total_fields_in_rules to summary to reflect fields targeted, not just successfully processed
            self._generate_summary(all_test_cases, output_file, total_fields_in_rules)


        except Exception as e:
            logging.error(f"Failed to generate test cases: {str(e)}", exc_info=True)
            raise

    def _save_test_cases(self, test_cases: Dict[str, List[Dict[str, Any]]], output_file: str) -> None:
        """Save test cases to a JSON file with backup."""
        try:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            if os.path.exists(output_file):
                backup_file = f"{output_file}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
                os.rename(output_file, backup_file)
                logging.info(f"Created backup of JSON: {backup_file}")

            with open(output_file, "w") as f:
                json.dump(test_cases, f, indent=2)
            logging.info(f"Successfully saved JSON test cases to {output_file}")
        except Exception as e:
            logging.error(f"Failed to save JSON test cases: {str(e)}", exc_info=True)
            # Not raising here to allow CSV and summary to attempt saving
    
    # New method to save as CSV
    def _save_test_cases_as_csv(self, all_test_cases: Dict[str, List[Dict[str, Any]]], json_output_file: str) -> None:
        """Save test cases to a CSV file."""
        csv_output_file = os.path.splitext(json_output_file)[0] + ".csv"
        
        headers = ["SchemaName", "FieldName", "Test Case", "Description", "Expected Result", "Input"]
        
        try:
            os.makedirs(os.path.dirname(csv_output_file), exist_ok=True) # Ensure dir exists
            
            # Create backup of existing CSV file if it exists
            if os.path.exists(csv_output_file):
                backup_csv_file = f"{csv_output_file}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
                os.rename(csv_output_file, backup_csv_file)
                logging.info(f"Created backup of CSV: {backup_csv_file}")

            with open(csv_output_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                
                for full_field_name, test_case_list in all_test_cases.items():
                    parts = full_field_name.split('.', 1)
                    schema_name = parts[0] if len(parts) > 1 else "N/A"
                    field_name = parts[1] if len(parts) > 1 else parts[0]
                    
                    if not test_case_list: # Handle cases where a field might have no test cases generated
                        # Optionally write a row indicating no test cases, or skip
                        # writer.writerow([schema_name, field_name, "N/A", "No test cases generated", "N/A", "N/A"])
                        logging.info(f"No test cases to write to CSV for {full_field_name}.")
                        continue

                    for tc in test_case_list:
                        # Convert Python None to string "NULL" for CSV output as per example
                        input_value = "NULL" if tc.get("input") is None else tc.get("input")
                        # Convert boolean inputs to string representation for consistency in CSV
                        if isinstance(input_value, bool):
                            input_value = str(input_value)

                        writer.writerow([
                            schema_name,
                            field_name,
                            tc.get("test_case", ""),
                            tc.get("description", ""),
                            tc.get("expected_result", ""),
                            input_value
                        ])
            logging.info(f"Successfully saved CSV test cases to {csv_output_file}")

        except Exception as e:
            logging.error(f"Failed to save CSV test cases: {str(e)}", exc_info=True)
            # Not raising here to allow summary to attempt saving

    # Updated signature to accept total_fields_in_rules
    def _generate_summary(self, test_cases: Dict[str, List[Dict[str, Any]]], output_file: str, total_fields_in_rules: int) -> None:
        """Generate a summary of the test case generation."""
        # total_fields_processed reflects fields for which test case generation was attempted (key exists in test_cases dict)
        total_fields_with_generated_cases = len(test_cases) 
        
        total_test_cases_generated = sum(len(cases) for cases in test_cases.values() if cases) # Sum only if cases is not empty
        
        summary_lines = [
            "\nTest Case Generation Summary",
            f"{'=' * 30}",
            f"Total fields in rules file: {total_fields_in_rules}",
            f"Total fields for which test cases were attempted/stored: {total_fields_with_generated_cases}",
            f"Total test cases generated: {total_test_cases_generated}"
        ]

        if total_test_cases_generated > 0:
            pass_count = sum(1 for cases in test_cases.values() for case in cases if case.get("expected_result") == "Pass")
            fail_count = total_test_cases_generated - pass_count
            summary_lines.extend([
                f"  - Pass test cases: {pass_count} ({pass_count/total_test_cases_generated*100:.1f}%)",
                f"  - Fail test cases: {fail_count} ({fail_count/total_test_cases_generated*100:.1f}%)"
            ])
            if total_fields_with_generated_cases > 0: # Avoid division by zero if no fields had cases
                 # Calculate average based on fields that actually got test cases
                fields_with_at_least_one_case = sum(1 for cases in test_cases.values() if cases)
                if fields_with_at_least_one_case > 0:
                    avg_tc_per_field_with_cases = total_test_cases_generated / fields_with_at_least_one_case
                    summary_lines.append(f"Average test cases per field (with generated cases): {avg_tc_per_field_with_cases:.2f}")
                else:
                    summary_lines.append("Average test cases per field (with generated cases): N/A (No fields had cases)")

        else: # No test cases generated at all
            summary_lines.append("  - No Pass test cases.")
            summary_lines.append("  - No Fail test cases.")
            summary_lines.append("Average test cases per field: N/A")


        summary_lines.extend([
            f"JSON Output file: {output_file}",
            f"CSV Output file: {os.path.splitext(output_file)[0] + '.csv'}",
            f"{'=' * 30}"
        ])
        
        summary = "\n".join(summary_lines)
        logging.info(summary)
        
        try:
            summary_file = f"{os.path.splitext(output_file)[0]}_summary.txt"
            with open(summary_file, "w", encoding="utf-8") as f:
                f.write(summary)
            logging.info(f"Summary written to {summary_file}")
        except Exception as e:
            logging.error(f"Failed to write summary file: {e}", exc_info=True)


def main(config_dict=None): # Renamed config to config_dict to avoid clash if a module named config exists
    """Main function to run the test case generation."""
    try:
        if config_dict is None:
            config_path = "config/settings.yaml"
            try:
                with open(config_path, "r") as f:
                    config_dict = yaml.safe_load(f)
                logging.info(f"Loaded configuration from {config_path}")
            except Exception as e:
                logging.error(f"Failed to load config from {config_path}: {str(e)}", exc_info=True)
                raise
        
        # TestCaseGenerator loads its own config based on its __init__ default or passed param
        # The config_dict here is primarily for llm.initialize_llm
        generator = TestCaseGenerator() # Uses its own default config path
        
        # Ensure llm_client is initialized with the config_dict that was loaded/passed to main
        llm_client = llm.initialize_llm(config_dict)
        
        generator.generate_test_cases(
            generator.config["processed_rules_file"],
            generator.config["generated_test_cases_file"],
            llm_client
        )
    except Exception as e:
        logging.critical(f"Application failed critically: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
