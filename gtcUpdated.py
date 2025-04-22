import json
import os
from typing import Dict, List, Optional, Any, Tuple
import yaml
from datetime import datetime
import logging
import re
from src import llm  # Added IMPORT
import csv  # <--- Import the csv module

# Set up logging (ensure logs directory exists)
log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'test_generation.log')),
        logging.StreamHandler()
    ]
)

class TestCaseGenerator:
    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config = self._load_config(config_path)
        self.field_specific_rules = self._initialize_field_rules()
        # Ensure output directory exists based on config
        output_file_path = self.config.get("generated_test_cases_file", "output/generated_test_cases.json")
        output_dir = os.path.dirname(output_file_path)
        if output_dir: # Check if output_dir is not empty
             os.makedirs(output_dir, exist_ok=True)


    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file with error handling."""
        try:
            with open(config_path, "r") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
             logging.error(f"Configuration file not found: {config_path}")
             raise
        except Exception as e:
            logging.error(f"Failed to load config from {config_path}: {str(e)}")
            raise

    def _initialize_field_rules(self) -> Dict[str, Dict[str, Any]]:
        """Initialize specific rules for different field types."""
        # This structure remains unchanged from your provided code
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
        }

    def _validate_date_format(self, test_case: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate date format test cases."""
        # This logic remains unchanged from your provided code
        if test_case["input"] is None:
            # Assuming None might be valid for Fail cases or non-mandatory fields
            return True, ""

        if isinstance(test_case["input"], str):
            for date_format in self.field_specific_rules["Date"]["valid_formats"]:
                try:
                    datetime.strptime(test_case["input"], date_format)
                    # Format matches. If expected Pass, this is good. If Fail, maybe unexpected.
                    # Basic validation only checks format conformance here.
                    return True, ""
                except ValueError:
                    continue # Try next format
            # If no format matched after trying all
            if test_case["expected_result"] == "Pass":
                 return False, f"Invalid date format for 'Pass' case. Input: '{test_case['input']}'. Expected one of: {self.field_specific_rules['Date']['valid_formats']}"
            else: # Expected Fail, and format is invalid, so this is correct.
                 return True, ""
        # Input is not a string (and not None)
        if test_case["expected_result"] == "Pass":
            return False, f"Date input '{test_case['input']}' must be a string for a 'Pass' case."
        else: # Expected Fail, non-string input is a valid reason.
            return True, ""


    def _validate_string_format(self, test_case: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate string format test cases."""
         # This logic remains unchanged from your provided code
        if test_case["input"] is None:
            return True, "" # Allow None, assume handled by logic/mandatory checks

        if not isinstance(test_case["input"], str):
            if test_case["expected_result"] == "Pass":
                return False, f"Input '{test_case['input']}' is not a string, but expected result is 'Pass'."
            else: # Expected Fail, and type is wrong, so this is valid failure reason
                return True, ""
        # It is a string, passes basic type check.
        return True, ""

    def _generate_prompt(self, field_name: str, data_type: str, mandatory_field: bool, primary_key: bool,
                         business_rules: str) -> str:
        """Generate a more structured and specific prompt for test case generation."""
        # This prompt generation remains unchanged from your provided code
        field_specific_info = ""
        if data_type == "Date":
            field_specific_info = "\nFor Date fields, use these formats only:\n" + \
                                  "\n".join(f"- {fmt}" for fmt in self.field_specific_rules["Date"]["valid_formats"])

        # Using the exact prompt structure you provided last
        return f"""
Generate test cases for the field '{field_name}' with following specifications:
- Data Type: {data_type}
- Mandatory: {mandatory_field}
- Primary Key: {primary_key}
- Business Rules: {business_rules if business_rules else 'N/A'} {field_specific_info}

Requirements:
1. Include ONLY the JSON array of test cases in your response
2. Each test case must have these exact fields:
   - "test_case": A clear, unique identifier for the test
   - "description": Detailed explanation of what the test verifies
   - "expected_result": MUST be exactly "Pass" or "Fail"
   - "input": The test input value (can be null, string, number, etc.) Use JSON null for null values.

3. Include these types of test cases:
   - Basic valid inputs ('Pass')
   - Basic invalid inputs ('Fail')
   - Null/empty handling (expected result depends on mandatory status and rules)
   - Boundary conditions (if applicable)
   - Edge cases
   - Type validation ('Fail' for wrong types)

4. Consider field-specific requirements:
   - For Date fields: Ensure 'Pass' cases use valid formats. Test invalid formats for 'Fail'.
   - For String fields: Consider length limits, character restrictions if mentioned in rules.
   - Handle nullable fields appropriately based on constraints.

Return the response in this exact format:
[
    {{
        "test_case": "TC001_Valid_Basic",
        "description": "Basic valid input test",
        "expected_result": "Pass",
        "input": "example"
    }},
    {{
        "test_case": "TC002_Invalid_Type",
        "description": "Invalid data type input",
        "expected_result": "Fail",
        "input": 12345
    }}
]

IMPORTANT: Return ONLY the JSON array. No additional text or explanation."""


    def _validate_test_case(self, test_case: Dict[str, Any], data_type: str) -> Tuple[bool, str]:
        """Validate a single test case based on field type and rules."""
        # This validation logic remains unchanged from your provided code
        required_keys = ["test_case", "description", "expected_result", "input"]
        if not all(field in test_case for field in required_keys):
            missing = [k for k in required_keys if k not in test_case]
            return False, f"Missing required fields: {', '.join(missing)}"

        if test_case["expected_result"] not in ["Pass", "Fail"]:
            return False, f"Invalid expected_result value: '{test_case['expected_result']}'. Must be 'Pass' or 'Fail'."

        # Apply field-specific validation using the initialized rules
        if data_type in self.field_specific_rules:
            validator = self.field_specific_rules[data_type].get("extra_validation")
            if validator:
                is_valid, error_msg = validator(test_case)
                # If the specific validator returns False, use its message
                if not is_valid:
                    return False, error_msg
        # If no specific validator or it passed, return True
        return True, ""

    def _parse_llm_response(self, response_text: str, data_type: str) -> Optional[List[Dict[str, Any]]]:
        """Parse and validate LLM response with improved error handling."""
        # This parsing logic remains unchanged from your provided code
        try:
            # Remove Markdown JSON blocks if present
            cleaned_text = response_text.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[len("```json"):].strip()
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-len("```")].strip()

            # Minimal cleaning - JSON parser is often robust enough
            # cleaned_text = re.sub(r'\\([^"\\])', r'\\\\\1', cleaned_text) # Be cautious with regex replacements

            if not cleaned_text:
                 logging.warning("LLM response was empty after cleaning.")
                 return None

            test_cases = json.loads(cleaned_text)

            if not isinstance(test_cases, list):
                # Try to recover if it's a dict with a single list value
                if isinstance(test_cases, dict) and len(test_cases) == 1:
                    potential_list = list(test_cases.values())[0]
                    if isinstance(potential_list, list):
                        logging.warning("LLM response was a dict, extracted list.")
                        test_cases = potential_list
                    else:
                        raise ValueError("Response is not a JSON list and not a dict containing a single list.")
                else:
                    raise ValueError("Response is not a JSON list.")


            validated_cases = []
            for idx, case in enumerate(test_cases, 1):
                if not isinstance(case, dict):
                     logging.warning(f"Item {idx} is not a dictionary, skipping: {case}")
                     continue

                # Normalize expected_result before validation
                if 'expected_result' in case and isinstance(case['expected_result'], str):
                     res_lower = case['expected_result'].lower()
                     if res_lower == 'pass':
                         case['expected_result'] = 'Pass'
                     elif res_lower == 'fail':
                         case['expected_result'] = 'Fail'
                     # else: validation will catch invalid values

                is_valid, error_msg = self._validate_test_case(case, data_type)
                if not is_valid:
                    logging.warning(f"Test case {idx} validation failed for data type '{data_type}': {error_msg}. Case: {case}")
                    continue # Skip invalid case

                validated_cases.append(case)

            if not validated_cases:
                 logging.warning("No valid test cases found after parsing and validation.")
                 return None

            return validated_cases

        except json.JSONDecodeError as e:
            logging.error(f"JSON parsing error: {e}. Snippet: '{response_text[max(0, e.pos-20):e.pos+20]}'")
            # logging.debug(f"Raw response causing JSON error:\n{response_text}") # Optional: log full response on debug
            return None
        except ValueError as e: # Catch structure errors
             logging.error(f"Data structure error after JSON parse: {str(e)}")
             return None
        except Exception as e:
            logging.error(f"Unexpected error parsing LLM response: {str(e)}", exc_info=True)
            return None


    def generate_test_cases(self, rules_file: str, output_file: str, llm_client) -> None:
        """Main method to generate and save test cases."""
        # This generation logic remains unchanged from your provided code
        try:
            # Load rules
            try:
                with open(rules_file, "r") as f:
                    rules = json.load(f)
            except FileNotFoundError:
                 logging.error(f"Rules file not found: {rules_file}")
                 raise # Re-raise to stop execution
            except json.JSONDecodeError as e:
                 logging.error(f"Error decoding JSON from rules file {rules_file}: {e}")
                 raise # Re-raise

            all_test_cases = {}
            total_fields = sum(len(details.get("fields", {})) for details in rules.values()) # Safer access
            processed_fields = 0

            if total_fields == 0:
                logging.warning(f"No fields found in the rules file: {rules_file}. Exiting.")
                return

            logging.info(f"Starting test case generation for {total_fields} fields...")

            for parent_field, details in rules.items():
                 if not isinstance(details, dict) or "fields" not in details:
                     logging.warning(f"Skipping invalid entry '{parent_field}' in rules file.")
                     continue

                 for field_name, field_details in details["fields"].items():
                    if not isinstance(field_details, dict):
                         logging.warning(f"Skipping invalid field definition for '{field_name}' under '{parent_field}'.")
                         continue

                    full_field_name = f"{parent_field}.{field_name}"
                    processed_fields += 1
                    logging.info(f"Processing field {processed_fields}/{total_fields}: {full_field_name}")

                    # Check required details (example) - adapt if needed
                    required_details = ["data_type", "mandatory_field", "primary_key"]
                    if not all(k in field_details for k in required_details):
                        missing = [k for k in required_details if k not in field_details]
                        logging.error(f"Skipping {full_field_name}: Missing required details: {', '.join(missing)}")
                        continue

                    # Generate prompt
                    prompt = self._generate_prompt(
                        field_name,
                        field_details["data_type"],
                        field_details["mandatory_field"],
                        field_details["primary_key"],
                        field_details.get("business_rules", "")
                    )

                    # Get LLM response with retries
                    max_retries = self.config.get("llm_retries", 3)
                    test_cases = None
                    for attempt in range(max_retries):
                        try:
                            logging.info(f"Attempt {attempt + 1}/{max_retries} for {full_field_name}")
                            response_text = llm.generate_test_cases_with_llm(
                                llm_client,
                                prompt,
                                self.config.get("max_output_tokens", 1024) # Use config value or default
                            )

                            if not response_text:
                                logging.warning(f"Attempt {attempt + 1}: LLM returned empty response for {full_field_name}.")
                                continue

                            test_cases = self._parse_llm_response(response_text, field_details["data_type"])

                            if test_cases:
                                all_test_cases[full_field_name] = test_cases
                                logging.info(f"Successfully generated {len(test_cases)} valid test cases for {full_field_name} on attempt {attempt + 1}.")
                                break # Success
                            else:
                                logging.warning(f"Attempt {attempt + 1}: Failed to parse or validate LLM response for {full_field_name}.")
                                # Optional delay: time.sleep(1)

                        except Exception as e:
                            logging.error(f"Attempt {attempt + 1} for {full_field_name} failed with exception: {str(e)}", exc_info=False) # Set exc_info=True for full trace
                            # Optional delay: time.sleep(2)

                        if attempt == max_retries - 1 and not test_cases:
                                logging.error(f"Failed to generate valid test cases for {full_field_name} after {max_retries} attempts.")
                                # Optionally store empty list: all_test_cases[full_field_name] = []

            # Save results (JSON and CSV)
            if all_test_cases:
                 self._save_test_cases(all_test_cases, output_file) # output_file is the JSON path from config
                 # Generate summary
                 self._generate_summary(all_test_cases, output_file)
            else:
                 logging.warning("No test cases were successfully generated for any field.")


        except Exception as e:
            logging.error(f"Critical error during test case generation process: {str(e)}", exc_info=True)
            # Re-raise if main function needs to know about the failure
            raise

    # --- MODIFIED METHOD ---
    def _save_test_cases(self, test_cases: Dict[str, List[Dict[str, Any]]], json_output_file: str) -> None:
        """Save test cases to JSON with backup and also create a CSV version."""

        # --- 1. Save JSON (Original logic) ---
        try:
            # Create backup of existing JSON file if it exists
            if os.path.exists(json_output_file):
                json_backup_file = f"{json_output_file}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
                try:
                    os.rename(json_output_file, json_backup_file)
                    logging.info(f"Created JSON backup: {json_backup_file}")
                except OSError as e:
                    logging.error(f"Failed to create JSON backup for {json_output_file}: {e}")
                    # Continue saving even if backup fails? Or raise? For now, log and continue.

            # Save new test cases as JSON
            with open(json_output_file, "w", encoding='utf-8') as f:
                json.dump(test_cases, f, indent=2, ensure_ascii=False)
            logging.info(f"Successfully saved test cases to JSON: {json_output_file}")

        except Exception as e:
            logging.error(f"Failed to save test cases to JSON file {json_output_file}: {str(e)}", exc_info=True)
            # If JSON fails, maybe we shouldn't proceed to CSV? Or try anyway? Let's try anyway.
            # raise # Optionally re-raise if JSON saving is critical

        # --- 2. Save CSV ---
        # Determine CSV filename from JSON filename
        csv_output_file = os.path.splitext(json_output_file)[0] + ".csv"

        try:
            # Create backup of existing CSV file if it exists
            if os.path.exists(csv_output_file):
                csv_backup_file = f"{csv_output_file}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
                try:
                    os.rename(csv_output_file, csv_backup_file)
                    logging.info(f"Created CSV backup: {csv_backup_file}")
                except OSError as e:
                    logging.error(f"Failed to create CSV backup for {csv_output_file}: {e}")
                    # Log and continue

            # Define CSV Headers based on user's example structure
            headers = ["Schema Name", "Field Name", "test_case", "description", "expected_result", "input"]

            # Write data to CSV using the csv module
            with open(csv_output_file, "w", newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL) # Use minimal quoting
                writer.writerow(headers) # Write header row

                # Iterate through the dictionary and flatten the data
                for full_field_name, cases_list in test_cases.items():
                    # Split the full field name into schema and field parts
                    parts = full_field_name.split('.', 1) # Split only on the first dot
                    schema_name = parts[0] if len(parts) > 0 else full_field_name # Handle case with no dot
                    field_name = parts[1] if len(parts) > 1 else "" # The rest is the field name

                    for case_dict in cases_list:
                        # Prepare row data, ensuring order matches headers
                        # Handle input formatting for CSV
                        input_val = case_dict.get('input')
                        # Represent None explicitly or as empty string
                        csv_input = "NULL" if input_val is None else str(input_val)

                        row = [
                            schema_name,
                            field_name,
                            case_dict.get('test_case', ''), # Use .get for safety
                            case_dict.get('description', ''),
                            case_dict.get('expected_result', ''),
                            csv_input # Use the processed input value
                        ]
                        writer.writerow(row)

            logging.info(f"Successfully saved test cases to CSV: {csv_output_file}")

        except Exception as e:
            logging.error(f"Failed to save test cases to CSV file {csv_output_file}: {str(e)}", exc_info=True)
            # Do not raise here, as JSON might have saved successfully. Just log the error.

    # --- MODIFIED METHOD ---
    def _generate_summary(self, test_cases: Dict[str, List[Dict[str, Any]]], json_output_file: str) -> None:
        """Generate a summary of the test case generation, including CSV file path."""
        total_fields_generated_for = len(test_cases) # Count fields that actually have test cases
        total_test_cases = sum(len(cases) for cases in test_cases.values())

        # Calculate average safely
        avg_cases_per_field = (total_test_cases / total_fields_generated_for) if total_fields_generated_for > 0 else 0

        # Derive CSV filename for the summary
        csv_output_file = os.path.splitext(json_output_file)[0] + ".csv"

        # Using the user's specific summary format numbers (hardcoded for now as in the original)
        # TODO: Ideally, these numbers should be calculated dynamically if possible
        # total_fields_processed_in_run = 10 # Example from user text - how is this determined?
        # total_test_cases_generated_in_run = 122 # Example from user text
        # avg_cases_per_field_in_run = 12.2 # Example from user text

        # Let's use the calculated values instead of hardcoded ones for accuracy
        summary = (
            f"\n--- Test Case Generation Summary ---\n"
            f"{'=' * 30}\n"
            # f"Total fields processed: {total_fields_processed_in_run} \n" # Using hardcoded value from user prompt
            # f"Total test cases generated: {total_test_cases_generated_in_run} \n" # Using hardcoded value
            # f"Average test cases per field: {avg_cases_per_field_in_run:.1f} \n" # Using hardcoded value
            f"Fields with generated cases: {total_fields_generated_for}\n" # Actual count
            f"Total test cases generated: {total_test_cases}\n" # Actual count
            f"Average test cases per field (generated): {avg_cases_per_field:.2f}\n" # Actual average
            f"JSON Output file: {json_output_file}\n"
            f"CSV Output file: {csv_output_file}\n" # Added CSV path
            f"{'=' * 30}"
        )

        logging.info(summary)

# Ensure this is the main function structure you are using:

def main(config_path: str = "config/settings.yaml"): # Accepts the PATH STRING
    try:
        # --- Load config dictionary FIRST ---
        try:
             with open(config_path, "r") as f:
                 # Load the dictionary from the file path
                 config = yaml.safe_load(f)
        except FileNotFoundError:
             logging.error(f"Main: Configuration file not found: {config_path}")
             # Exit or raise if config is essential
             return # Or raise SystemExit(1)
        except Exception as e:
             # Log the error showing the path it tried to open
             logging.error(f"Main: Failed to load config from path '{config_path}': {str(e)}")
             # Exit or raise
             return # Or raise SystemExit(1)

        # --- Validate required config keys ---
        required_config_keys = ["processed_rules_file", "generated_test_cases_file"] # Add other required keys
        if not all(key in config for key in required_config_keys):
             missing_keys = [key for key in required_config_keys if key not in config]
             logging.error(f"Configuration file '{config_path}' is missing required keys: {', '.join(missing_keys)}")
             return # Or raise SystemExit(1)

        # --- Initialize Generator (pass the PATH STRING) ---
        # The constructor will load the config again internally using the path
        generator = TestCaseGenerator(config_path=config_path)

        # --- Initialize LLM (pass the LOADED DICTIONARY) ---
        llm_client = llm.initialize_llm(config)

        # --- Generate Test Cases (use paths from the generator's loaded config) ---
        generator.generate_test_cases(
            generator.config["processed_rules_file"],
            generator.config["generated_test_cases_file"], # This is the JSON output path
            llm_client
        )
        logging.info("Test case generation process completed.")

    except Exception as e:
        # Catch any other unexpected errors during setup or execution
        logging.error(f"Application failed unexpectedly in main: {str(e)}", exc_info=True) # Log stack trace
        # Depending on deployment, might want sys.exit(1) here

# Example of how to run main (if this script is executed directly)
if __name__ == "__main__":
     # Ensure the llm module is available and config/settings.yaml exists and is correct
     main(config_path="config/settings.yaml") # Pass the PATH STRING here

# Example of how to run main (if this script is executed directly)
if __name__ == "__main__":
     # Ensure the llm module is available and config/settings.yaml exists and is correct
     main(config_path="config/settings.yaml")
