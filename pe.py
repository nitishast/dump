import pandas as pd
import json
import yaml
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/parse_excel.log', mode='a'),
        logging.StreamHandler()
    ]
)

def load_config(config_path="config/settings.yaml"):
    """Loads configuration from a YAML file."""
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"Config file not found at {config_path}")
        return None
    except yaml.YAMLError as e:
        logging.error(f"Error parsing config file: {e}")
        return None


def preprocess_excel(file_path, sheet_name):
    """Preprocess the Excel file with updated column handling."""
    try:
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        logging.info(f"Successfully loaded Excel file: {file_path}, sheet: {sheet_name}")

        # Rename columns to remove leading/trailing spaces
        df.columns = df.columns.str.strip()
        
        # Log the actual columns found for debugging
        logging.info(f"Found columns: {list(df.columns)}")

        # Updated expected columns based on new CSV format
        expected_columns = [
            "Schema Name", 
            "Attributes Details", 
            "Data Type", 
            "Business Rules",
            "Expected Values",  # New column
            "Mandatory Field", 
            "Required from Source to have data populated", 
            "Primary Key", 
            "Required for Deployment Validation",
            "Post-Deployment Validation",  # New column
            "Regression Test"  # New column
        ]
        
        # Check for required columns (with flexibility for whitespace)
        missing_cols = []
        for expected_col in expected_columns:
            found = False
            for col in df.columns:
                if expected_col.lower().strip() == col.lower().strip():
                    found = True
                    break
            if not found:
                missing_cols.append(expected_col)
        
        if missing_cols:
            logging.warning(f"The following expected columns were not found: {missing_cols}")
            logging.warning("Continuing with available columns...")
        
        # Fill down the "Schema Name" category
        schema_col = df.columns[0]  # Schema Name is always the first column
        df[schema_col] = df[schema_col].ffill()

        return df

    except Exception as e:
        logging.error(f"Error preprocessing Excel file: {e}")
        return None

def extract_rules_from_dataframe(df):
    """Extract rules from the cleaned dataframe with updated column mapping and multi-line business rules handling."""
    try:
        # Get column names - using flexible approach for finding columns
        schema_col = "Schema Name"
        attribute_col = next((col for col in df.columns if "Attributes Details" in col), "Attributes Details")
        data_type_col = next((col for col in df.columns if "Data Type" in col), "Data Type")
        business_rules_col = next((col for col in df.columns if "Business Rules" in col), "Business Rules")
        expected_values_col = next((col for col in df.columns if "Expected Values" in col), "Expected Values")
        mandatory_field_col = next((col for col in df.columns if "Mandatory Field" in col), "Mandatory Field")
        from_source_col = next((col for col in df.columns if "Required from Source" in col), "Required from Source to have data populated")
        primary_key_col = next((col for col in df.columns if "Primary Key" in col), "Primary Key")
        required_for_deployment_col = next((col for col in df.columns if "Required for Deployment Validation" in col), "Required for Deployment Validation")
        post_deployment_validation_col = next((col for col in df.columns if "Post-Deployment Validation" in col), "Post-Deployment Validation")
        regression_test_col = next((col for col in df.columns if "Regression Test" in col), "Regression Test")
        
        # Log the actual columns being used
        column_mapping = {
            "schema_col": schema_col,
            "attribute_col": attribute_col,
            "data_type_col": data_type_col,
            "business_rules_col": business_rules_col,
            "expected_values_col": expected_values_col,
            "mandatory_field_col": mandatory_field_col,
            "from_source_col": from_source_col,
            "primary_key_col": primary_key_col,
            "required_for_deployment_col": required_for_deployment_col,
            "post_deployment_validation_col": post_deployment_validation_col,
            "regression_test_col": regression_test_col
        }
        logging.info(f"Using column mapping: {column_mapping}")
        
        # Mapping for data type standardization
        type_mapping = {
            'datetime': 'Date',
            'date': 'Date',
            'timestamp': 'Date',
            'int': 'Integer',
            'integer': 'Integer',
            'float': 'Float',
            'decimal': 'Float',
            'boolean': 'Boolean',
            'bool': 'Boolean',
            'string': 'String',
            'text': 'String',
            'object': 'String'  # Mapping for "object" type in new CSV
        }
        
        extracted_rules = {}
        business_rules_collector = {}  # To collect multi-line business rules
        
        # First pass: Identify all fields and collect basic information
        for idx, row in df.iterrows():
            schema_name = row[schema_col]
            attribute_name = row[attribute_col]
            
            # Skip rows with missing schema and attribute
            if pd.isna(schema_name) and pd.isna(attribute_name):
                continue
                
            # Skip rows with missing attribute name (but keep processing for business rules collection)
            if pd.isna(attribute_name) or str(attribute_name).strip() == "":
                # This might be a continuation row with additional business rules
                # Try to associate it with the last processed field
                if business_rules_col in df.columns and pd.notna(row[business_rules_col]):
                    last_schema = None
                    last_attribute = None
                    
                    # Find the last valid schema and attribute
                    for prev_idx in range(idx-1, -1, -1):
                        prev_row = df.iloc[prev_idx]
                        if pd.notna(prev_row[attribute_col]) and str(prev_row[attribute_col]).strip() != "":
                            last_schema = str(prev_row[schema_col]).strip()
                            last_attribute = str(prev_row[attribute_col]).strip()
                            break
                    
                    if last_schema and last_attribute:
                        key = f"{last_schema}.{last_attribute}"
                        if key not in business_rules_collector:
                            business_rules_collector[key] = []
                        business_rules_collector[key].append(str(row[business_rules_col]).strip())
                continue
                
            # Basic field processing
            schema_key = str(schema_name).strip()
            attribute_key = str(attribute_name).strip()
            key = f"{schema_key}.{attribute_key}"
            
            # Initialize business rules collector for this field
            if key not in business_rules_collector:
                business_rules_collector[key] = []
            
            # Add the current row's business rules
            if business_rules_col in df.columns and pd.notna(row[business_rules_col]):
                business_rules_collector[key].append(str(row[business_rules_col]).strip())
        
        # Second pass: Process all fields with collected business rules
        for idx, row in df.iterrows():
            schema_name = row[schema_col]
            attribute_name = row[attribute_col]
            
            # Skip rows with missing schema and attribute or missing attribute name
            if pd.isna(schema_name) and pd.isna(attribute_name):
                continue
            if pd.isna(attribute_name) or str(attribute_name).strip() == "":
                continue
                
            # Process the field
            schema_key = str(schema_name).strip()
            attribute_key = str(attribute_name).strip()
            key = f"{schema_key}.{attribute_key}"
            
            # Skip if we've already processed this field
            if schema_key in extracted_rules and attribute_key in extracted_rules[schema_key]["fields"]:
                continue
                
            # Ensure schema exists in output dictionary
            if schema_key not in extracted_rules:
                extracted_rules[schema_key] = {"fields": {}}
            
            # Helper function to handle Yes/No fields
            def is_yes(value):
                if pd.isna(value):
                    return False
                value_str = str(value).strip().lower()
                return value_str in ["yes", "y", "true", "1"]
            
            # Standardize data type
            raw_data_type = str(row[data_type_col]).strip().lower() if pd.notna(row[data_type_col]) else "string"
            # Remove any additional qualifiers like (10,2) for decimals
            raw_data_type = raw_data_type.split('(')[0].strip()
            
            # Map to standardized type, default to String
            data_type = type_mapping.get(raw_data_type, 'String')
            
            # Combine all collected business rules for this field
            combined_business_rules = "\n".join(business_rules_collector.get(key, []))
            
            expected_values = str(row[expected_values_col]).strip() if expected_values_col in df.columns and pd.notna(row[expected_values_col]) else ""
            
            # Build field object with new fields
            field_data = {
                "data_type": data_type,
                "mandatory_field": is_yes(row[mandatory_field_col]),
                "primary_key": is_yes(row[primary_key_col]),
                "business_rules": combined_business_rules,
                "expected_values": expected_values
            }
            
            # Add optional fields if they exist in the dataframe
            if from_source_col in df.columns:
                field_data["from_source"] = is_yes(row[from_source_col])
            
            if required_for_deployment_col in df.columns:
                field_data["required_for_deployment"] = is_yes(row[required_for_deployment_col])
                
            if post_deployment_validation_col in df.columns:
                field_data["post_deployment_validation"] = is_yes(row[post_deployment_validation_col])
                
            if regression_test_col in df.columns:
                field_data["regression_test"] = is_yes(row[regression_test_col])
            
            extracted_rules[schema_key]["fields"][attribute_key] = field_data
            
        # Add a log for debug purposes showing the results
        for schema_key, schema_data in extracted_rules.items():
            for field_key, field_data in schema_data["fields"].items():
                # Log multi-line rules that were collected
                if len(business_rules_collector.get(f"{schema_key}.{field_key}", [])) > 1:
                    logging.info(f"Multi-line rules collected for {schema_key}.{field_key}: " + 
                                 f"{len(business_rules_collector.get(f'{schema_key}.{field_key}', []))} lines")
                    logging.debug(f"Business rules for {schema_key}.{field_key}: {field_data['business_rules']}")
        
        return extracted_rules
    except Exception as e:
        logging.error(f"Error extracting rules: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return {}

def parse_excel(config):
    """Parses the Excel file and extracts the rules."""
    excel_file = config.get("excel_file")
    excel_sheet_name = config.get("excel_sheet_name")

    if not excel_file or not excel_sheet_name:
        logging.error("Error: excel_file or excel_sheet_name not found in config.")
        return None

    df = preprocess_excel(excel_file, excel_sheet_name)

    if df is not None:
        rules = extract_rules_from_dataframe(df)
        return rules
    else:
        return None

def save_rules(rules, output_file):
    """Saves the extracted rules to a JSON file."""
    try:
        with open(output_file, "w") as f:
            json.dump(rules, f, indent=4)
        logging.info(f"✅ Rules extracted and saved to {output_file}")
    except IOError as e:
        logging.error(f"Error saving rules to {output_file}: {e}")

if __name__ == "__main__":
    config = load_config()
    if config is None:
        exit()

    rules = parse_excel(config)
    if rules:
        output_file = config.get("processed_rules_file")
        if output_file:
            save_rules(rules, output_file)
        else:
            logging.error("Error: processed_rules_file not found in config.")
