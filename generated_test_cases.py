# generated_test_cases.py

import json
import os
from typing import Dict, List, Optional, Any, Tuple
import yaml
from datetime import datetime
import logging
import re
from src import llm

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
                    "%Y-%m-%d",  # Date only
                    "%m/%d/%Y",
                    "%Y/%m/%d",
                    "%m-%d-%Y",

                ],
                "extra_validation": self._validate_date_format
            },
            "String": {
                "extra_validation": self._validate_string_format
            },
             "DateTime": {  # Separate rule for DateTime
                "valid_formats": ["%Y-%m-%d %H:%M:%S.%f"],
                "extra_validation": self._validate_date_format
            },
            "Long": {
                "extra_validation": self._validate_long_format
            }
        }
    def _validate_long_format(self, test_case: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate Long format test cases"""
        if test_case["input"] is None:
            return True, "" #Allow null

        if not isinstance(test_case["input"], (int)):
            if test_case["expected_result"] == "Pass":
                return False, "Long field with non-integer input should fail"
        return True, ""
    def _validate_date_format(self, test_case: Dict[str, Any], data_type:str = "Date") -> Tuple[bool, str]:
        """Validate date/datetime format test cases."""

        if test_case["input"] is None:
            return True, ""

        if isinstance(test_case["input"], str):
            formats = self.field_specific_rules[data_type]["valid_formats"]
            for date_format in formats:
                try:
                    datetime.strptime(test_case["input"], date_format)
                    return True, ""
                except ValueError:
                    continue
            return False, f"Invalid date format. Expected formats: {formats}"
        return False, f"{data_type} input must be a string"

    def _validate_string_format(self, test_case: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate string format test cases."""
        if test_case["input"] is None:
            return True, ""

        if not isinstance(test_case["input"], (str, type(None))):
            if test_case["expected_result"] == "Pass":
                return False, "String field with non-string input should fail"
        return True, ""

    def _generate_prompt(self, field_name: str, data_type: str, mandatory_field: bool, primary_key: bool,
                         business_rules: str) -> str:
        """Generate a more structured and specific prompt for test case generation."""
        field_specific_info = ""
        if data_type == "Date":
            field_specific_info = "\nFor Date fields, use these formats *only*:\n" + \
                                  "\n".join(f"- {fmt}" for fmt in self.field_specific_rules["Date"]["valid_formats"])
        elif data_type == "DateTime":
            field_specific_info = "\nFor DateTime fields, use this format *ONLY*:\n" + \
                                    "- %Y-%m-%d %H:%M:%S.%f"


        prompt =  f"""
        Generate test cases for the field '{field_name}' with following specifications:
        - Data Type: {data_type}
        - Mandatory: {mandatory_field}
        - Primary Key: {primary_key}
        - Business Rules: {business_rules}

        Requirements:
        1.  Return a JSON array of test case objects.  Do *NOT* include any introductory text or explanations.  Do *NOT* include a code block.  Output *ONLY* the JSON array.
        2.  Each test case *MUST* have these exact fields:
            - "test_case": A clear, unique identifier for the test (string).
            - "description": Detailed explanation of what the test verifies (string).
            - "expected_result": MUST be exactly "Pass" or "Fail" (string).
            - "input": The test input value (can be null, string, number, etc.).
        3. Include these types of test cases:
            - Basic valid inputs.
            - Basic invalid inputs.
            - Null/empty handling (if applicable).
            - Boundary conditions (if applicable).
            - Edge cases (if applicable).
            - Type validation.
        4. Consider field-specific requirements:
            {field_specific_info}
            - For String fields: Consider length limits and character restrictions.
            - Handle nullable fields appropriately based on the 'Mandatory' constraint.
        5. Do not include any javascript code snippet. If you have to show repetitions, use "a" * 255 instead of "a".repeat(255)

        Example Format (the example is for a different field, use the specifications above):
        [
            {{
                "test_case": "TC001_Valid_Basic",
                "description": "Basic valid input test",
                "expected_result": "Pass",
                "input": "example"
            }}
        ]
        """
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
            # Remove any surrounding text or code blocks, focusing on potential JSON
            cleaned_text = response_text.strip()
            cleaned_text = re.sub(r'^```[a-zA-Z]*\s*', '', cleaned_text, flags=re.MULTILINE)  # Remove code block start
            cleaned_text = re.sub(r'```\s*$', '', cleaned_text, flags=re.MULTILINE)  # Remove code block end
            cleaned_text = cleaned_text.strip()
            match = re.search(r'\[.*\]', cleaned_text, re.DOTALL)
            if match:
                 cleaned_text = match.group(0)
            # Attempt to parse the cleaned text as JSON
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
    def generate_test_cases(self, rules_file: str, output_file: str, llm_client) -> None:  # added llm client
        """Main method to generate and save test cases."""
        try:
            # Load rules
            with open(rules_file, "r") as f:
                rules = json.load(f)

            all_test_cases = {}
            total_fields = sum(len(details["fields"]) for details in rules.values())
            processed_fields = 0
            skipped_fields = []  # Keep track of skipped fields

            for parent_field, details in rules.items():
                for field_name, field_details in details["fields"].items():
                    full_field_name = f"{parent_field}.{field_name}"
                    logging.info(f"Processing field {processed_fields + 1}/{total_fields}: {full_field_name}")
                    if full_field_name in all_test_cases:
                        logging.warning(f"Skipping {full_field_name}, already processed.")
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
                    max_retries = 3
                    success = False #track success
                    for attempt in range(max_retries):
                        try:
                            response_text = llm.generate_test_cases_with_llm(llm_client, prompt,
                                                                               self.config.get("max_output_tokens",
                                                                                                 1000))
                            test_cases = self._parse_llm_response(response_text, field_details["data_type"])

                            if test_cases:
                                all_test_cases[full_field_name] = test_cases
                                logging.info(f"Successfully generated {len(test_cases)} test cases")
                                success = True
                                break  # Exit retry loop on success
                            else:
                                logging.warning(f"Attempt {attempt + 1}: Failed to generate valid test cases")
                        except Exception as e:
                            logging.error(f"Attempt {attempt + 1} failed: {str(e)}")
                            if attempt == max_retries - 1:
                                logging.error(
                                    f"Failed to generate test cases for {full_field_name} after {max_retries} attempts")
                    if not success:
                        skipped_fields.append(full_field_name)  # Add to skipped list


                    processed_fields += 1

            # Save results
            self._save_test_cases(all_test_cases, output_file)

            # Log skipped fields
            if skipped_fields:
                logging.warning(f"Skipped fields (failed after {max_retries} retries): {', '.join(skipped_fields)}")

            # Generate summary
            if total_fields > 0:  #added a check to ensure that it does not divide by zero.
                self._generate_summary(all_test_cases, output_file)
            else:
                logging.warning("No fields were processed, skipping summary generation.")

        except Exception as e:
            logging.error(f"Failed to generate test cases: {str(e)}")
            raise

    def _save_test_cases(self, test_cases: Dict[str, List[Dict[str, Any]]], output_file: str) -> None:
        """Save test cases with backup."""
        try:
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
        summary = ""
        if total_fields > 0:  # Avoid division by zero
            summary = (
                f"\nTest Case Generation Summary\n"
                f"{'=' * 30}\n"
                f"Total fields processed: {total_fields}\n"
                f"Total test cases generated: {total_test_cases}\n"
                f"Average test cases per field: {total_test_cases / total_fields:.2f}\n"
                f"Output file: {output_file}\n"
                f"{'=' * 30}"
            )
        else:
            summary = (
                f"\nTest Case Generation Summary\n"
                f"{'=' * 30}\n"
                f"Total fields processed: 0\n"
                f"Total test cases generated: 0\n"
                f"No test cases were generated.\n"
                f"Output file: {output_file}\n"
                f"{'=' * 30}"
          )

        logging.info(summary)
def main(config):
    try:
        generator = TestCaseGenerator()
        llm_client = llm.initialize_llm(config)  # Initialize LLM client
        generator.generate_test_cases(
            generator.config["processed_rules_file"],
            generator.config["generated_test_cases_file"],
            llm_client  # Pass LLM client
        )
    except Exception as e:
        logging.error(f"Application failed: {str(e)}")
        raise

if __name__ == "__main__":
    with open("config/settings.yaml", "r") as f:
        config = yaml.safe_load(f)
    main(config)
