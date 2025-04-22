import json
import os
from typing import Dict, List, Optional, Any, Tuple
import yaml
from datetime import datetime
import logging
import re
from src import llm  # Added IMPORT
import csv  # <-- Import the csv module

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/test_generation.log'),
        logging.StreamHandler()
    ]
)

class TestCaseGenerator:
    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config = self._load_config(config_path)
        self.field_specific_rules = self._initialize_field_rules()
        # Ensure output directory exists (useful for both JSON and CSV)
        output_dir = os.path.dirname(self.config.get("generated_test_cases_file", "output/generated_test_cases.json"))
        if output_dir: # Check if output_dir is not empty (e.g., if filename is just 'output.json')
             os.makedirs(output_dir, exist_ok=True)
        log_dir = os.path.dirname('logs/test_generation.log')
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)


    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file with error handling."""
        try:
            with open(config_path, "r") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logging.error(f"Configuration file not found: {config_path}")
            raise
        except Exception as e:
            logging.error(f"Failed to load config: {str(e)}")
            raise

    def _initialize_field_rules(self) -> Dict[str, Dict[str, Any]]:
        """Initialize specific rules for different field types."""
        return {
            "Date": {
                "valid_formats": [
                    "%Y-%m-%d %H:%M:%S.%f", # added for 3 places after seconds
                    # "%Y-%m-%d %H:%M:%S",
                    # "%Y/%m/%d %H:%M:%S",
                    # "%m/%d/%Y %H:%M:%S"
                ],
                "extra_validation": self._validate_date_format
            },
            "String": {
                "extra_validation": self._validate_string_format
            }
            # Add other data types and their rules here if needed
        }

    def _validate_date_format(self, test_case: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate date format test cases."""
        if test_case["input"] is None:
             # Allow None if the test case expects failure or if None is valid based on rules
             # For simplicity here, we assume None might be valid for some 'Fail' cases
             return True, ""

        if isinstance(test_case["input"], str):
            for date_format in self.field_specific_rules["Date"]["valid_formats"]:
                try:
                    datetime.strptime(test_case["input"], date_format)
                    # If parsing succeeds, it's a valid format
                    # If expected result is Pass, this is correct.
                    # If expected result is Fail, this might be an issue unless the failure is for another reason.
                    # This basic validation primarily checks format conformance.
                    return True, ""
                except ValueError:
                    continue # Try the next format
            # If no format matched
            if test_case["expected_result"] == "Pass":
                 return False, f"Invalid date format. Expected one of: {self.field_specific_rules['Date']['valid_formats']}"
            else: # If expected Fail, not matching a valid format is the expected outcome
                 return True, "" # Format is invalid as expected for a Fail case
        # If input is not a string (and not None)
        if test_case["expected_result"] == "Pass":
            return False, "Date input must be a string for a 'Pass' case (unless None is explicitly allowed)"
        else: # If expected Fail, non-string input is a valid reason for failure
            return True, ""


    def _validate_string_format(self, test_case: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate string format test cases."""
        # Allow None input, assuming business logic handles it (might cause Pass or Fail)
        if test_case["input"] is None:
            return True, ""

        # Check if the input is actually a string
        if not isinstance(test_case["input"], str):
            # If it's not a string, it should generally Fail unless None is allowed and handled
            if test_case["expected_result"] == "Pass":
                return False, "Input is not a string, but expected result is 'Pass'."
            else: # Expected 'Fail', and input is not a string, which is a valid reason to fail.
                return True, ""
        # If it is a string, it passes this basic type check.
        # Further string validation (length, pattern) would go here if needed.
        return True, ""


    def _generate_prompt(self, field_name: str, data_type: str, mandatory_field: bool, primary_key: bool,
                         business_rules: str) -> str:
        """Generate a more structured and specific prompt for test case generation."""
        # Basic prompt structure
        prompt = f"""
Generate a comprehensive list of test cases for the field '{field_name}'.
Field Details:
- Data Type: {data_type}
- Mandatory: {'Yes' if mandatory_field else 'No'}
- Primary Key: {'Yes' if primary_key else 'No'}
- Business Rules: {business_rules if business_rules else 'N/A'}

Generate test cases covering various scenarios including:
1.  Valid basic input ('Pass').
2.  Valid edge cases (e.g., min/max length/value if applicable) ('Pass').
3.  Invalid input based on data type ('Fail').
4.  Invalid input based on business rules ('Fail').
5.  Empty input ('Fail' if mandatory, potentially 'Pass' or 'Fail' if not, depending on rules).
6.  Null input (consider if allowed, usually 'Fail' if mandatory).
7.  Boundary value analysis (if applicable, e.g., for numbers or dates).
8.  Special characters or formats ('Fail' unless specifically allowed).

For each test case, provide:
- test_case: A short identifier (e.g., TC001_Valid_Basic).
- description: A brief explanation of the test case.
- expected_result: Either "Pass" or "Fail".
- input: The exact input value to use for the test. Use `null` for JSON null value, empty string `""` for empty.

Format the output as a JSON array of objects. Example:
[
  {{
    "test_case": "TC001_Valid_Basic",
    "description": "Basic valid input test",
    "expected_result": "Pass",
    "input": "SomeValidValue"
  }},
  {{
    "test_case": "TC002_Invalid_Format",
    "description": "Input with invalid format",
    "expected_result": "Fail",
    "input": "Invalid@Value!"
  }},
  {{
    "test_case": "TC003_Empty_Input",
    "description": "Empty string input",
    "expected_result": "{'Fail' if mandatory_field else 'Pass/Fail (check rules)'}",
    "input": ""
  }}
]
"""
        # Add specific instructions for data types like Date
        if data_type == "Date":
            valid_formats_str = "\n".join(f"- '{fmt}'" for fmt in self.field_specific_rules["Date"]["valid_formats"])
            prompt += f"\nImportant: For Date fields, ensure 'Pass' cases use ONLY the following formats for the 'input' value:\n{valid_formats_str}\nTest invalid date formats as 'Fail' cases."

        # Add more specific instructions for other types if needed
        # elif data_type == "Number":
        #     prompt += "\nFor Number fields, include tests for zero, negative numbers, large numbers, and non-numeric input."

        return prompt

    def _validate_test_case(self, test_case: Dict[str, Any], data_type: str) -> Tuple[bool, str]:
        """Validate a single test case based on field type and rules."""
        # Check for required keys
        required_keys = ["test_case", "description", "expected_result", "input"]
        if not all(key in test_case for key in required_keys):
            missing_keys = [key for key in required_keys if key not in test_case]
            return False, f"Missing required keys: {', '.join(missing_keys)}"

        # Validate expected_result value
        if test_case["expected_result"] not in ["Pass", "Fail"]:
            return False, f"Invalid expected_result value: '{test_case['expected_result']}'. Must be 'Pass' or 'Fail'."

        # Apply field-specific validation using the initialized rules
        if data_type in self.field_specific_rules:
            validator = self.field_specific_rules[data_type].get("extra_validation")
            if validator:
                is_valid, error_msg = validator(test_case)
                if not is_valid:
                    return False, error_msg # Return specific error from validator

        # Basic type check (can be expanded)
        # This is a fallback if no specific validator exists or passes basic checks
        inp = test_case["input"]
        exp_res = test_case["expected_result"]

        if data_type == "String" and not isinstance(inp, (str, type(None))) and exp_res == "Pass":
             return False, f"Input '{inp}' is not a string or null, but expected result is 'Pass'."
        if data_type == "Integer" and not isinstance(inp, (int, type(None))) and exp_res == "Pass":
             return False, f"Input '{inp}' is not an integer or null, but expected result is 'Pass'."
        if data_type == "Number" and not isinstance(inp, (int, float, type(None))) and exp_res == "Pass":
             return False, f"Input '{inp}' is not a number or null, but expected result is 'Pass'."
        # Date validation is handled by _validate_date_format

        return True, "" # Passed validation


    def _parse_llm_response(self, response_text: str, data_type: str) -> Optional[List[Dict[str, Any]]]:
        """Parse and validate LLM response with improved error handling."""
        try:
            # Basic cleaning: remove markdown code blocks and leading/trailing whitespace
            cleaned_text = re.sub(r'^```json\s*', '', response_text, flags=re.IGNORECASE)
            cleaned_text = re.sub(r'\s*```$', '', cleaned_text)
            cleaned_text = cleaned_text.strip()

            # Attempt to fix common JSON issues like trailing commas (requires careful regex)
            # Remove trailing commas before ']' or '}'
            cleaned_text = re.sub(r',\s*(\}|\])', r'\1', cleaned_text)

            # Handle potential escape issues (be cautious, this might corrupt valid escapes)
            # This regex tries to fix unescaped backslashes NOT followed by standard escape chars like ", \, n, t, etc.
            # It's heuristic and might need refinement based on observed errors.
            # cleaned_text = re.sub(r'\\([^"\\/bfnrtu])', r'\\\\\1', cleaned_text)
            # --> Let's be less aggressive initially, JSON parser might handle some cases.

            # Replace Pythonic None/True/False with JSON null/true/false if needed (case-insensitive)
            cleaned_text = re.sub(r'\bNone\b', 'null', cleaned_text, flags=re.IGNORECASE)
            cleaned_text = re.sub(r'\bTrue\b', 'true', cleaned_text, flags=re.IGNORECASE)
            cleaned_text = re.sub(r'\bFalse\b', 'false', cleaned_text, flags=re.IGNORECASE)


            if not cleaned_text:
                 logging.warning("LLM response was empty after cleaning.")
                 return None

            # Parse JSON
            test_cases = json.loads(cleaned_text)

            # Validate structure - should be a list
            if not isinstance(test_cases, list):
                logging.error(f"Parsed response is not a JSON list. Type: {type(test_cases)}")
                # Attempt to handle if it's a dict containing a list (common mistake)
                if isinstance(test_cases, dict) and len(test_cases) == 1:
                    key = list(test_cases.keys())[0]
                    if isinstance(test_cases[key], list):
                        logging.warning(f"Response was a dict, extracting list from key '{key}'")
                        test_cases = test_cases[key]
                    else:
                         raise ValueError("Response is not a JSON list and doesn't contain a single list.")
                else:
                    raise ValueError("Response is not a JSON list.")


            # Validate and normalize each test case
            validated_cases = []
            for idx, case in enumerate(test_cases, 1):
                 if not isinstance(case, dict):
                     logging.warning(f"Item {idx} in list is not a dictionary, skipping.")
                     continue

                 # Normalize expected_result before validation
                 if 'expected_result' in case and isinstance(case['expected_result'], str):
                     if case['expected_result'].lower() == 'pass':
                         case['expected_result'] = 'Pass'
                     elif case['expected_result'].lower() == 'fail':
                         case['expected_result'] = 'Fail'
                     # else: leave it as is for validation to catch invalid value

                 is_valid, error_msg = self._validate_test_case(case, data_type)
                 if not is_valid:
                    # Log specific error and the problematic case data
                    logging.warning(f"Test case {idx} validation failed: {error_msg}. Case data: {case}")
                    # Optionally skip invalid cases or try to fix them
                    continue # Skip this invalid case

                 # Ensure input key exists, even if None (null in JSON)
                 if 'input' not in case:
                     case['input'] = None # Default to null if missing, validation might have already caught this

                 validated_cases.append(case)

            if not validated_cases:
                 logging.warning("No valid test cases found after parsing and validation.")
                 return None

            return validated_cases

        except json.JSONDecodeError as e:
            logging.error(f"JSON parsing error: {e.message} at line {e.lineno} col {e.colno}")
            logging.error(f"Problematic text snippet near error: {cleaned_text[max(0, e.pos-30):e.pos+30]}")
            # logging.debug(f"Full cleaned text causing error:\n{cleaned_text}") # Use debug level for full text
            return None
        except ValueError as e: # Catch structure errors
             logging.error(f"Data structure error: {str(e)}")
             # logging.debug(f"Full cleaned text causing error:\n{cleaned_text}")
             return None
        except Exception as e:
            logging.error(f"Unexpected error parsing LLM response: {str(e)}", exc_info=True) # Include stack trace
            # logging.debug(f"Raw response text:\n{response_text}")
            return None

    def generate_test_cases(self, rules_file: str, output_file_base: str, llm_client) -> None: # Changed output_file to output_file_base
        """Main method to generate and save test cases to JSON and CSV."""
        try:
            # Load rules
            try:
                with open(rules_file, "r") as f:
                    rules = json.load(f)
            except FileNotFoundError:
                 logging.error(f"Rules file not found: {rules_file}")
                 return # Stop execution if rules are missing
            except json.JSONDecodeError as e:
                 logging.error(f"Error decoding JSON from rules file {rules_file}: {e}")
                 return

            all_test_cases: Dict[str, List[Dict[str, Any]]] = {}
            total_fields = sum(len(details.get("fields", {})) for details in rules.values()) # Added .get for safety
            processed_fields = 0

            if total_fields == 0:
                logging.warning(f"No fields found in the rules file: {rules_file}. No test cases will be generated.")
                return

            logging.info(f"Starting test case generation for {total_fields} fields...")

            for parent_field, details in rules.items():
                if not isinstance(details, dict) or "fields" not in details:
                     logging.warning(f"Skipping invalid entry '{parent_field}' in rules file (expected dict with 'fields' key).")
                     continue

                for field_name, field_details in details["fields"].items():
                    if not isinstance(field_details, dict):
                         logging.warning(f"Skipping invalid field definition for '{field_name}' under '{parent_field}' (expected dict).")
                         continue

                    full_field_name = f"{parent_field}.{field_name}"
                    processed_fields += 1
                    logging.info(f"Processing field {processed_fields}/{total_fields}: {full_field_name}")

                    # Check for required field details
                    required_details = ["data_type", "mandatory_field", "primary_key"]
                    if not all(key in field_details for key in required_details):
                         missing_keys = [key for key in required_details if key not in field_details]
                         logging.error(f"Skipping field {full_field_name} due to missing details: {', '.join(missing_keys)}")
                         continue # Skip this field

                    # Generate prompt
                    prompt = self._generate_prompt(
                        field_name,
                        field_details["data_type"],
                        field_details["mandatory_field"],
                        field_details["primary_key"],
                        field_details.get("business_rules", "") # Use .get for optional field
                    )

                    # Get LLM response with retries
                    max_retries = self.config.get("llm_retries", 3) # Get retries from config or default to 3
                    test_cases = None # Initialize test_cases to None for the retry loop
                    for attempt in range(max_retries):
                        try:
                            logging.info(f"Attempt {attempt + 1}/{max_retries} to generate cases for {full_field_name}")
                            response_text = llm.generate_test_cases_with_llm(
                                llm_client,
                                prompt,
                                self.config.get("max_output_tokens", 1024) # Increased default
                            )
                            if not response_text:
                                logging.warning(f"Attempt {attempt + 1}: LLM returned empty response for {full_field_name}.")
                                continue # Go to next attempt

                            test_cases = self._parse_llm_response(response_text, field_details["data_type"])

                            if test_cases:
                                logging.info(f"Successfully generated {len(test_cases)} valid test cases for {full_field_name} on attempt {attempt + 1}.")
                                all_test_cases[full_field_name] = test_cases
                                break # Exit retry loop on success
                            else:
                                logging.warning(f"Attempt {attempt + 1}: Failed to parse or validate LLM response for {full_field_name}.")
                                # Optional: Add a small delay before retrying
                                # time.sleep(1)

                        except Exception as e:
                            logging.error(f"Attempt {attempt + 1} for {full_field_name} failed with exception: {str(e)}", exc_info=True)
                            # Optional: Delay before retry on exception
                            # time.sleep(2)

                        if attempt == max_retries - 1 and not test_cases:
                                logging.error(f"Failed to generate valid test cases for {full_field_name} after {max_retries} attempts.")
                                # Decide if you want to store an empty list or skip the field entirely
                                # all_test_cases[full_field_name] = [] # Option: Store empty list

            # Save results (JSON and CSV)
            if all_test_cases:
                 # Determine output filenames (ensure they have extensions)
                 json_output_file = output_file_base if output_file_base.lower().endswith(".json") else f"{output_file_base}.json"
                 csv_output_file = os.path.splitext(json_output_file)[0] + ".csv"

                 self._save_test_cases(all_test_cases, json_output_file, csv_output_file) # Pass both filenames
                 # Generate summary
                 self._generate_summary(all_test_cases, json_output_file, csv_output_file) # Pass both filenames to summary
            else:
                 logging.warning("No test cases were successfully generated for any field.")


        except Exception as e:
            logging.error(f"Critical error during test case generation process: {str(e)}", exc_info=True)
            # No raise here, allow logging to handle it, or re-raise if needed upstream


    # --- MODIFIED METHOD ---
    def _save_test_cases(self, test_cases: Dict[str, List[Dict[str, Any]]], json_output_file: str, csv_output_file: str) -> None:
        """Save test cases to JSON and CSV files with backup."""

        # --- Save JSON ---
        try:
            # Create backup of existing JSON file if it exists
            if os.path.exists(json_output_file):
                json_backup_file = f"{json_output_file}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
                try:
                    os.rename(json_output_file, json_backup_file)
                    logging.info(f"Created JSON backup: {json_backup_file}")
                except OSError as e:
                    logging.error(f"Failed to create JSON backup for {json_output_file}: {e}")
                    # Decide if you want to proceed without backup or stop

            # Save new test cases to JSON
            with open(json_output_file, "w", encoding='utf-8') as f: # Added encoding
                json.dump(test_cases, f, indent=2, ensure_ascii=False) # Added ensure_ascii=False
            logging.info(f"Successfully saved test cases to JSON: {json_output_file}")

        except Exception as e:
            logging.error(f"Failed to save test cases to JSON file {json_output_file}: {str(e)}", exc_info=True)
            # Consider if failure to save JSON should prevent CSV saving (depends on requirements)

        # --- Save CSV ---
        try:
            # Create backup of existing CSV file if it exists
            if os.path.exists(csv_output_file):
                csv_backup_file = f"{csv_output_file}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
                try:
                    os.rename(csv_output_file, csv_backup_file)
                    logging.info(f"Created CSV backup: {csv_backup_file}")
                except OSError as e:
                    logging.error(f"Failed to create CSV backup for {csv_output_file}: {e}")
                    # Decide if you want to proceed without backup or stop

            # Define CSV Headers
            headers = ["FieldName", "test_case", "description", "expected_result", "input"]

            # Write data to CSV
            with open(csv_output_file, "w", newline='', encoding='utf-8') as csvfile: # Added encoding and newline=''
                writer = csv.writer(csvfile)
                writer.writerow(headers) # Write header row

                # Iterate through the dictionary and flatten the data
                for full_field_name, cases_list in test_cases.items():
                    for case_dict in cases_list:
                        # Prepare row data, ensuring order matches headers
                        # Handle potential None input correctly for CSV representation
                        input_val = case_dict.get('input')
                        # Represent None as empty string or specific marker like 'NULL' in CSV
                        csv_input = '' if input_val is None else str(input_val)

                        row = [
                            full_field_name,
                            case_dict.get('test_case', ''), # Use .get with default for safety
                            case_dict.get('description', ''),
                            case_dict.get('expected_result', ''),
                            csv_input # Use the processed input value
                        ]
                        writer.writerow(row)

            logging.info(f"Successfully saved test cases to CSV: {csv_output_file}")

        except Exception as e:
            logging.error(f"Failed to save test cases to CSV file {csv_output_file}: {str(e)}", exc_info=True)
            # No raise here, just log the error

    # --- MODIFIED METHOD ---
    def _generate_summary(self, test_cases: Dict[str, List[Dict[str, Any]]], json_output_file: str, csv_output_file: str) -> None:
        """Generate a summary of the test case generation."""
        total_fields_processed = len(test_cases) # Fields for which cases were actually generated
        total_test_cases_generated = sum(len(cases) for cases in test_cases.values())

        # Avoid division by zero if no fields were processed
        avg_cases_per_field = (total_test_cases_generated / total_fields_processed) if total_fields_processed > 0 else 0

        summary = (
            f"\n--- Test Case Generation Summary ---\n"
            f"Total fields processed successfully: {total_fields_processed}\n"
            f"Total test cases generated: {total_test_cases_generated}\n"
            f"Average test cases per field: {avg_cases_per_field:.2f}\n" # Format average
            f"JSON Output file: {json_output_file}\n"
            f"CSV Output file: {csv_output_file}\n" # Added CSV file path
            f"------------------------------------\n"
        )

        logging.info(summary)


def main(config_path: str = "config/settings.yaml"): # Pass config path to main
    try:
        # Load config first to pass to initializers if needed
        try:
             with open(config_path, "r") as f:
                 config = yaml.safe_load(f)
        except FileNotFoundError:
             logging.error(f"Main: Configuration file not found: {config_path}")
             return # Exit if config missing
        except Exception as e:
             logging.error(f"Main: Failed to load config {config_path}: {str(e)}")
             return # Exit if config loading fails


        generator = TestCaseGenerator(config_path=config_path) # Pass path to constructor
        llm_client = llm.initialize_llm(config) # Initialize LLM using loaded config

        # Get file paths from the generator's loaded config
        rules_file = generator.config.get("processed_rules_file")
        output_base = generator.config.get("generated_test_cases_file") # This is now the base name

        if not rules_file or not output_base:
             logging.error("Configuration missing 'processed_rules_file' or 'generated_test_cases_file'. Cannot proceed.")
             return

        generator.generate_test_cases(
            rules_file,
            output_base, # Pass the base name (e.g., "output/generated_tests")
            llm_client
        )
        logging.info("Test case generation process completed.")

    except Exception as e:
        # Catch any unexpected errors during setup or execution
        logging.error(f"Application failed: {str(e)}", exc_info=True) # Log stack trace
        # Decide if you need to exit with an error code, e.g., sys.exit(1)


# Example of how to run main (if this script is executed directly)
if __name__ == "__main__":
     # Assuming llm module and config file are set up correctly
     # You might need to adjust the path to your config file
     main(config_path="config/settings.yaml")
