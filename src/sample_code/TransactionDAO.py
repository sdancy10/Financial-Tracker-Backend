from GmailUtil import GmailUtil
from AuthUtil import AuthUtil
from TransactionParser import TransactionParser
from dataclasses import dataclass, field
from typing import List, Dict
from google.cloud import firestore
from metaphone import doublemetaphone
import pandas as pd
from joblib import load
from transaction_categorization_model import extract_features, tune_parameters, run_model_training
import nltk
# nltk.download('stopwords')
# nltk.download('punkt')
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import re
import traceback
from dateutil.parser import parse  # <-- for flexible date parsing


@dataclass
class TransactionDAO:
    mailbox: str = field(default='Transactions', init=False)
    auth: AuthUtil = field(init=False)
    email_results: List = field(default_factory=list)
    total_emails: int = field(default=0)
    transaction_results: List[TransactionParser] = field(default_factory=list)
    total_transactions: int = field(default=0)
    transaction_dict_results: List[Dict] = field(default_factory=list)

    def __post_init__(self):
        self.auth = AuthUtil()

    def __get_category_subcategory_prediction__(self):
        """
        Make category/subcategory predictions on self.transaction_dict_results.
        If 'year', 'month', 'day' columns do not exist, we'll skip converting them.
        """
        if len(self.transaction_dict_results) > 0:
            # Load the trained model
            trained_pipeline = load('trained_transaction_category_pipeline.joblib')

            # Create a DataFrame from the transaction dictionaries
            df = pd.DataFrame(self.transaction_dict_results)
            print("\n[DEBUG] __get_category_subcategory_prediction__ - columns before transformations:", df.columns)

            # Convert all object columns to 'string' dtype
            for col in df.select_dtypes(include=['object']).columns:
                df[col] = df[col].astype('string')

            # Now, if 'year', 'month', 'day' columns exist, convert them to string as well
            missing_cols = [col for col in ['year', 'month', 'day'] if col not in df.columns]
            if missing_cols:
                print("[WARNING] The following columns are missing in df, so we won't convert them:",
                      missing_cols)

            for col in ['year', 'month', 'day']:
                if col in df.columns:
                    df[col] = df[col].astype('string')

            X_new = df

            # Make predictions with the trained model
            Y_new_pred = trained_pipeline.predict(X_new)

            # Modify each dictionary in transaction_dict_results with the predicted category and subcategory
            for i, prediction in enumerate(Y_new_pred):
                self.transaction_dict_results[i]['predicted_category'] = prediction[0]
                self.transaction_dict_results[i]['predicted_subcategory'] = prediction[1]
        else:
            for d in self.transaction_dict_results:
                print(d)

    def get_email_data(self, userid='5oZfUgtSn0g1VaEa6VNpHVC51Zq2'):
        self.auth.get_local_credentials(userid)
        self.__get_email_transactions()
        self.__get_transaction_lists()
        self.__get_category_subcategory_prediction__()

    def post_db_data(self, userid=u'5oZfUgtSn0g1VaEa6VNpHVC51Zq2'):
        # Authenticate
        self.auth.get_local_credentials('firebase')
        db = firestore.Client.from_service_account_json(self.auth.user_pw)
        firestore_transaction = db.transaction()
        transactions_ref = db.collection('users') \
            .document(userid) \
            .collection('transactions')

        @firestore.transactional
        def update_in_transaction(firestore_transaction, transactions_ref, transaction):
            transaction_ref = transactions_ref.document(transaction['id'])
            snapshot = transaction_ref.get(transaction=firestore_transaction)
            existing_transaction = snapshot.get('id')
            if existing_transaction:
                # Transaction exists, update it
                firestore_transaction.update(transaction_ref, transaction)
                return True
            else:
                # Transaction does not exist, create it
                firestore_transaction.set(transaction_ref, transaction)
                return True

        update_counter = 0
        create_counter = 0
        for transaction in self.transaction_dict_results:
            result = update_in_transaction(firestore_transaction, transactions_ref, transaction)
            if result:
                create_counter += 1
            else:
                update_counter += 1
        print('Created Records: ' + str(create_counter))
        print('Updated Records: ' + str(update_counter))

    def get_db_data(self, user_id=u'5oZfUgtSn0g1VaEa6VNpHVC51Zq2'):
        # Authenticate
        self.auth.get_local_credentials('firebase')
        db = firestore.Client.from_service_account_json(self.auth.user_pw)
        users_ref = db.collection('users') \
            .document(user_id) \
            .collection('transactions')
        doc_results = []
        for doc in users_ref.stream():
            doc_results.append(doc.to_dict())

        print(len(doc_results))

    def __get_email_transactions(self):
        gmail_util = GmailUtil()
        print(self.auth.user_nm)
        gmail_util.create_connection(self.auth.user_nm, self.auth.user_pw)
        gmail_util.set_mailbox(self.mailbox)
        search_param = ''

        for mail in gmail_util.get_emails(search_param):
            mail_id = mail['id']
            subject = mail['subject']
            message = mail['message'].__str__()
            body = mail['body']
            date = mail['message']['Date']
            if (("Transaction" in subject)
                or ("transaction" in subject)
                or ("External Transfer" in subject)
                or ("Payment through Chase" in subject)
                or ((("withdrawal or purchase" in subject.lower()) or "deposit" in subject.lower())
                    and 'huntington' in message.lower() and not 'early pay' in message.lower())
                or (("account_ending_in" in subject.lower()) and 'noreply.pncalerts@pnc.com' not in message.lower())
                or (("account ending in" in subject.lower()) and 'noreply.pncalerts@pnc.com' not in message.lower())) \
                    and ("statement" not in subject.lower()):
                self.email_results.append((mail_id, body, date))
        self.total_emails = len(self.email_results)

    def __get_transaction_lists(self):
        """
        Build the transaction_dict_results from the email_results and then
        create year/month/day columns in the DataFrame using a flexible date parser.
        """
        df = None  # Initialize so we can reference it in the except block if needed

        # Helper to parse dates with dateutil
        def flexible_date_parser(dt_str):
            try:
                return parse(dt_str)
            except Exception:
                return None

        try:
            # Build up transaction_dict_results from email_results
            for notification_id, notification_txt, notification_dt in self.email_results:
                transaction = TransactionParser()
                transaction.set_transaction_text(notification_id, notification_txt, notification_dt)
                self.transaction_results.append(transaction)
                self.transaction_dict_results.append(transaction.get_dict())

            if self.transaction_dict_results:
                df = pd.DataFrame(self.transaction_dict_results)

                print("---- DEBUG: Initial DataFrame shape:", df.shape)
                print("---- DEBUG: Columns in df before date conversion:", df.columns)

                # Make sure 'date' column exists
                if 'date' not in df.columns:
                    print("---- DEBUG WARNING: 'date' column is missing!")
                else:
                    print("---- DEBUG: Sample 'date' values:\n", df['date'])

                # Use dateutil parser on each row (returns None if it fails)
                df['date'] = df['date'].apply(flexible_date_parser)
                # Drop rows where the date couldn't be parsed
                # df.dropna(subset=['date'], inplace=True)

                # Convert to UTC
                df['date'] = pd.to_datetime(df['date'], utc=True)

                print("---- DEBUG: 'date' column dtype after conversion:", df['date'].dtype)

                # Convert amount to float
                df['amount'] = df['amount'].astype(float)

                # Set index to 'date'
                df = df.set_index('date')
                print("---- DEBUG: Index dtype after setting df.set_index('date'):", df.index.dtype)

                # Now create columns year, month, day if index is datetime
                if pd.api.types.is_datetime64_any_dtype(df.index):
                    df['year'] = df.index.year
                    df['month'] = df.index.month
                    df['day'] = df.index.day
                    df['day_name'] = df.index.day_name()

                    print("---- DEBUG: Created columns year, month, day, day_name. df.columns:", df.columns)
                    print("---- DEBUG: df.head() after creating year/month/day:\n", df.head())
                else:
                    print("---- DEBUG ERROR: df.index is NOT datetime. year/month/day assignments will fail.")

                # Reset index so 'date' is a column again
                df = df.reset_index()

                def vendor_cleanup(vendor_name):
                    # Remove special characters
                    result = re.sub('[^A-Za-z ]+', ' ', vendor_name).lower()
                    # Remove multiple spaces
                    result = re.sub(' +', ' ', result)
                    try:
                        stop_words = set(stopwords.words('english'))
                    except LookupError:
                        nltk.download('stopwords')
                        stop_words = set(stopwords.words('english'))

                    custom_stops = ['co', 'orig', 'us', 'name', 'com', 'pending']
                    [stop_words.add(stop) for stop in custom_stops]

                    try:
                        result = word_tokenize(result)
                    except LookupError:
                        nltk.download('punkt')
                        result = word_tokenize(result)

                    result = [w for w in result if w.lower() not in stop_words]
                    result = ' '.join(result)
                    return result

                def clean_metaphone(x):
                    if x[1] == '':
                        return x[0], x[0]
                    else:
                        return x[0], x[1]

                df['vendor_cleaned'] = df['vendor'].apply(vendor_cleanup)
                df['cleaned_metaphone'] = df['vendor_cleaned'].apply(doublemetaphone)
                df['cleaned_metaphone'] = df['cleaned_metaphone'].apply(clean_metaphone)

                # Update self.transaction_dict_results with new columns
                self.transaction_dict_results = df.to_dict(orient='records')
                self.total_transactions = len(self.transaction_dict_results)

        except Exception as e:
            print("---- EXCEPTION in __get_transaction_lists: ", e)
            traceback.print_exc()
            if df is not None:
                self.print_df_info(df)

    def print_df_info(self, df):
        pd.set_option('display.max_rows', None)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.max_colwidth', None)
        pd.set_option('display.width', None)
        print(df.tail(5))
        print(df.dtypes)  # This will show the data types of each column
        print(df.head())  # This will help you inspect the first few rows of your data


def main():
    users = ['aDer8RS94NPmPdAYGHQQpI3iWm13', '5oZfUgtSn0g1VaEa6VNpHVC51Zq2']
    for user in users:
        t = TransactionDAO()
        t.get_email_data(userid=user)
        print(user + ' Total Records: ' + str(len(t.transaction_dict_results)))
        for trans in t.transaction_dict_results:
            print(trans)
        t.post_db_data(userid=user)
        del t


if __name__ == '__main__':
    main()
