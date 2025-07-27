#!/usr/bin/env python3
"""
Check ML training data quality before training
"""

import os
import sys
import pandas as pd
import argparse
from google.cloud import storage

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

def check_data_quality(project_id: str):
    """Check the quality of ML training data in Cloud Storage"""
    print(f"\nChecking ML training data quality for project: {project_id}")
    print("="*60)
    
    # Initialize storage client
    storage_client = storage.Client(project=project_id)
    bucket_name = f"{project_id}-ml-data"
    
    try:
        bucket = storage_client.bucket(bucket_name)
        
        # Find parquet files
        blobs = list(bucket.list_blobs(prefix='training/'))
        parquet_files = [blob for blob in blobs if blob.name.endswith('.parquet')]
        
        if not parquet_files:
            print("❌ No parquet files found in training directory")
            return
            
        print(f"✓ Found {len(parquet_files)} parquet file(s)")
        
        # Load and analyze each file
        all_data = []
        for blob in parquet_files:
            print(f"\nAnalyzing: {blob.name}")
            df = pd.read_parquet(f"gs://{bucket_name}/{blob.name}")
            all_data.append(df)
            
            print(f"  - Records: {len(df)}")
            print(f"  - Columns: {', '.join(df.columns)}")
            print(f"  - First 5 rows:\n{df[['transaction_id', 'user_id', 'vendor', 'vendor_cleaned', 'category', 'subcategory', 'is_user_corrected', 'user_category', 'user_subcategory', 'predicted_category', 'predicted_subcategory']].head(5)}")
            
            # Debug: Check for predicted_category
            if 'predicted_category' in df.columns:
                print(f"\n  ⚠️  Found 'predicted_category' column (should have been mapped to 'category')")
                print(f"  predicted_category distribution:")
                pred_cat_counts = df['predicted_category'].value_counts()
                for cat, count in pred_cat_counts.head(5).items():
                    print(f"    - {cat}: {count}")
            
            # Debug: Check for user_category
            if 'user_category' in df.columns:
                print(f"\n  ✓ Found 'user_category' column (user-provided categories)")
                user_cat_not_null = df['user_category'].notna().sum()
                print(f"  User categories provided: {user_cat_not_null} ({user_cat_not_null/len(df)*100:.1f}%)")
                if user_cat_not_null > 0:
                    print(f"  user_category distribution:")
                    user_cat_counts = df['user_category'].value_counts()
                    for cat, count in user_cat_counts.head(5).items():
                        print(f"    - {cat}: {count}")
                        
                # Check how many would fall back to predicted
                if 'predicted_category' in df.columns:
                    pred_not_uncategorized = (df['predicted_category'].notna() & 
                                            (df['predicted_category'] != 'Uncategorized')).sum()
                    would_use_predicted = df['user_category'].isna().sum()
                    print(f"\n  Category source breakdown:")
                    print(f"    - Using user_category: {user_cat_not_null}")
                    print(f"    - Would use predicted_category: {min(would_use_predicted, pred_not_uncategorized)}")
                    print(f"    - Would be 'Uncategorized': {len(df) - user_cat_not_null - min(would_use_predicted, pred_not_uncategorized)}")
            
            # Debug: Check for user_subcategory
            if 'user_subcategory' in df.columns:
                user_subcat_not_null = df['user_subcategory'].notna().sum()
                print(f"  User subcategories provided: {user_subcat_not_null} ({user_subcat_not_null/len(df)*100:.1f}%)")
            
            # Check for required columns
            required_columns = ['category', 'subcategory', 'vendor', 'amount', 'user_id']
            missing_columns = []
            
            # Special handling for category/subcategory - check user versions too
            for col in required_columns:
                if col == 'category':
                    # Category is considered present if either 'category' or 'user_category' exists
                    if 'category' not in df.columns and 'user_category' not in df.columns:
                        missing_columns.append(col)
                    elif 'category' not in df.columns and 'user_category' in df.columns:
                        print(f"  ℹ️  'category' column missing but 'user_category' found - this is OK")
                elif col == 'subcategory':
                    # Subcategory is considered present if either 'subcategory' or 'user_subcategory' exists
                    if 'subcategory' not in df.columns and 'user_subcategory' not in df.columns:
                        missing_columns.append(col)
                    elif 'subcategory' not in df.columns and 'user_subcategory' in df.columns:
                        print(f"  ℹ️  'subcategory' column missing but 'user_subcategory' found - this is OK")
                elif col not in df.columns:
                    missing_columns.append(col)
                    
            if missing_columns:
                print(f"  ⚠️  Missing columns: {missing_columns}")
                
                # Check for alternative column names
                alt_mappings = {
                    'category': ['predicted_category', 'user_category'],
                    'subcategory': ['predicted_subcategory', 'user_subcategory'], 
                    'account': ['account_id']
                }
                for missing_col, alternatives in alt_mappings.items():
                    if missing_col in missing_columns:
                        for alt in alternatives:
                            if alt in df.columns:
                                print(f"     Found '{alt}' which should map to '{missing_col}'")
            
            # Check category distribution
            # Use 'category' if available, otherwise fall back to 'user_category'
            category_col = 'category' if 'category' in df.columns else ('user_category' if 'user_category' in df.columns else None)
            
            if category_col:
                print(f"\n  Category distribution (from '{category_col}'):")
                category_counts = df[category_col].value_counts()
                for cat, count in category_counts.head(10).items():
                    print(f"    - {cat}: {count} ({count/len(df)*100:.1f}%)")
                    
                if len(category_counts) == 1:
                    print(f"\n  ⚠️  WARNING: Only one category found: '{category_counts.index[0]}'")
                    print(f"     This will cause issues with model training!")
                    
                # Check for Uncategorized
                uncategorized_df = df[df['category'] == 'Uncategorized']
                pd.set_option('display.max_colwidth', None)
                print(f"  - First 5 Uncategorized rows:\n{uncategorized_df[['transaction_id', 'user_id', 'vendor', 'vendor_cleaned', 'category', 'subcategory', 'is_user_corrected', 'user_category', 'user_subcategory', 'predicted_category', 'predicted_subcategory']].head(5)}")
                uncategorized_count = uncategorized_df.shape[0]
                # Check for Uncategorized or null values
                if category_col == 'category':
                    uncategorized_df = df[df['category'] == 'Uncategorized']
                else:  # user_category
                    # For user_category, check for null values instead of 'Uncategorized'
                    uncategorized_df = df[df[category_col].isna()]
                    
                if len(uncategorized_df) > 0:
                    pd.set_option('display.max_colwidth', None)
                    print(f"\n  First 5 uncategorized/null rows:")
                    # Show relevant columns for debugging
                    debug_columns = ['transaction_id', 'vendor', 'category']
                    if 'user_category' in df.columns:
                        debug_columns.append('user_category')
                    if 'predicted_category' in df.columns:
                        debug_columns.append('predicted_category')
                    if 'is_user_corrected' in df.columns:
                        debug_columns.append('is_user_corrected')
                    
                    # Only show columns that exist
                    debug_columns = [col for col in debug_columns if col in df.columns]
                    print(uncategorized_df[debug_columns].head(5))
                    
                    uncategorized_count = uncategorized_df.shape[0]
                    uncategorized_pct = uncategorized_count / len(df) * 100
                    if category_col == 'category':
                        print(f"\n  ⚠️  {uncategorized_count} ({uncategorized_pct:.1f}%) transactions are 'Uncategorized'")
                    else:
                        print(f"\n  ⚠️  {uncategorized_count} ({uncategorized_pct:.1f}%) transactions have no user category")
            else:
                print(f"\n  ❌ No category information found (neither 'category' nor 'user_category' columns exist)")
                    
            # Check user distribution
            if 'user_id' in df.columns:
                print(f"\n  User distribution:")
                user_counts = df['user_id'].value_counts()
                for user, count in user_counts.items():
                    print(f"    - {user}: {count} transactions")
                    
            # Check for user corrections
            if 'is_user_corrected' in df.columns:
                corrected_count = df[df['is_user_corrected'] == True].shape[0]
                print(f"\n  User corrections: {corrected_count} ({corrected_count/len(df)*100:.1f}%)")
                
        # Combine all data for overall analysis
        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            print(f"\n{'='*60}")
            print(f"OVERALL DATA QUALITY SUMMARY")
            print(f"{'='*60}")
            print(f"Total records: {len(combined_df)}")
            
            # Check for user corrections across all data
            if 'is_user_corrected' in combined_df.columns:
                total_corrected = combined_df['is_user_corrected'].sum()
                print(f"User-corrected transactions: {total_corrected} ({total_corrected/len(combined_df)*100:.1f}%)")
            
            if 'category' in combined_df.columns:
                unique_categories = combined_df['category'].nunique()
                print(f"Unique categories: {unique_categories}")
                
                if unique_categories < 2:
                    print("\n❌ CRITICAL: Less than 2 categories found!")
                    print("   The model needs at least 2 different categories to train properly.")
                    print("\n   Suggestions:")
                    print("   1. Ensure transactions have been properly categorized")
                    print("   2. Load more diverse transaction data")
                    print("   3. Manually categorize some transactions in Firestore")
                elif unique_categories < 5:
                    print("\n⚠️  WARNING: Only {} categories found.".format(unique_categories))
                    print("   Consider adding more diverse transaction data for better model performance.")
                else:
                    print(f"\n✓ Good category diversity: {unique_categories} categories")
            elif 'user_category' in combined_df.columns:
                # Fall back to user_category if category doesn't exist
                non_null_user_cats = combined_df['user_category'].notna()
                if non_null_user_cats.sum() > 0:
                    unique_categories = combined_df.loc[non_null_user_cats, 'user_category'].nunique()
                    print(f"Unique user categories: {unique_categories} (from {non_null_user_cats.sum()} categorized transactions)")
                    
                    if unique_categories < 2:
                        print("\n❌ CRITICAL: Less than 2 user categories found!")
                        print("   The model needs at least 2 different categories to train properly.")
                    elif unique_categories < 5:
                        print("\n⚠️  WARNING: Only {} user categories found.".format(unique_categories))
                    else:
                        print(f"\n✓ Good category diversity: {unique_categories} user categories")
                else:
                    print("\n❌ No user categories found (all null)")
            else:
                print("\n❌ No category data found in combined dataset")
                    
    except Exception as e:
        print(f"❌ Error checking data quality: {e}")
        import traceback
        traceback.print_exc()

def main():
    parser = argparse.ArgumentParser(description='Check ML training data quality')
    parser.add_argument('--project-id', required=True, help='GCP project ID')
    args = parser.parse_args()
    
    check_data_quality(args.project_id)

if __name__ == "__main__":
    main() 