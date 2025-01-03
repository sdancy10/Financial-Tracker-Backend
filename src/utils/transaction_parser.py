from typing import Dict, Any, Optional, List, Tuple
import logging
import base64
import re
from datetime import datetime, timedelta
from src.utils.config import Config
from zoneinfo import ZoneInfo
import platform
from email.utils import parsedate_to_datetime

class TransactionParser:
    """Parses transaction data from various sources"""
    
    # Common date formats to try
    DATE_FORMATS = [
        '%b %d, %Y at %I:%M %p',  # Dec 30, 2024 at 5:07 PM
        '%B %d, %Y at %I:%M %p',  # December 30, 2024 at 5:07 PM
        '%Y-%m-%dT%H:%M:%S',      # 2024-12-30T17:07:00
        '%Y-%m-%d',               # 2024-12-30
        '%m/%d/%Y',               # 12/30/2024
        '%m/%d/%y',               # 12/30/24
        '%b %d, %Y',              # Dec 30, 2024
        '%B %d, %Y',              # December 30, 2024
        '%Y-%m-%d %H:%M:%S',      # 2024-12-30 17:07:00
        '%m/%d/%y %I:%M %p',      # 12/30/24 5:07 PM
        '%a, %d %b %Y %H:%M:%S %z',  # e.g. Tue, 24 Dec 2024 21:44:55 +0000
        '%Y-%m-%dT%H:%M:%S%z',     # ISO format with timezone
        '%Y-%m-%d %H:%M:%S%z',     # ISO-like with timezone
        '%d/%m/%Y %H:%M:%S%z',     # Common format with timezone
        '%Y-%m-%dT%H:%M:%S.%f%z',  # ISO format with microseconds and timezone
    ]

    def _parse_date(self, date_str: str, email_date: Optional[str] = None) -> Optional[str]:
        if not date_str:
            return None

        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        import platform
        from email.utils import parsedate_to_datetime

        # Parse email date first if provided
        email_datetime = None
        if email_date:
            try:
                email_datetime = parsedate_to_datetime(email_date)
                self.logger.debug(f"Parsed email date: {email_datetime}")
            except Exception as e:
                self.logger.debug(f"Failed to parse email date: {str(e)}")

        # 1. First try to get timezone from the date string itself
        tz_info = None
        
        # Check for explicit offset in date string (e.g., +0000, -0500)
        offset_match = re.search(r'([+-]\d{4})', date_str)
        if offset_match:
            try:
                # Convert +0000 format to timezone
                hours = int(offset_match.group(1)[1:3])
                minutes = int(offset_match.group(1)[3:])
                offset = timedelta(hours=hours, minutes=minutes)
                if offset_match.group(1)[0] == '-':
                    offset = -offset
                tz_info = timezone(offset)
            except ValueError:
                pass

        # 2. Check for named timezones
        if not tz_info:
            if 'ET' in date_str:
                tz_info = ZoneInfo('America/New_York')
            elif 'CT' in date_str:
                tz_info = ZoneInfo('America/Chicago')
            elif 'MT' in date_str:
                tz_info = ZoneInfo('America/Denver')
            elif 'PT' in date_str:
                tz_info = ZoneInfo('America/Los_Angeles')
            elif 'GMT' in date_str or 'Z' in date_str:
                tz_info = timezone.utc

        # 3. Use email timezone if available
        if not tz_info and email_datetime and email_datetime.tzinfo:
            tz_info = email_datetime.tzinfo

        # 4. Fall back to system timezone
        if not tz_info:
            try:
                if platform.system() == 'Windows':
                    import winreg
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\TimeZoneInformation') as key:
                        tz_keyname = winreg.QueryValueEx(key, 'TimeZoneKeyName')[0]
                        tz_info = ZoneInfo(tz_keyname)
                else:
                    with open('/etc/timezone', 'r') as f:
                        tz_info = ZoneInfo(f.read().strip())
            except:
                tz_info = timezone.utc

        # Clean the date string but preserve timezone information
        cleaned_date_str = date_str
        for tz in ['ET', 'CT', 'MT', 'PT', 'GMT']:
            if tz in cleaned_date_str:
                cleaned_date_str = cleaned_date_str.replace(tz, '').strip()

        # Try parsing with each format
        for fmt in self.DATE_FORMATS:
            try:
                parsed_date = datetime.strptime(cleaned_date_str, fmt)

                # If we don't have time info in parsed date but have it in email_date
                if parsed_date.hour == 0 and parsed_date.minute == 0 and parsed_date.second == 0:
                    if email_datetime:
                        parsed_date = parsed_date.replace(
                            hour=email_datetime.hour,
                            minute=email_datetime.minute,
                            second=email_datetime.second,
                            microsecond=email_datetime.microsecond
                        )

                # Attach timezone if not already present
                if parsed_date.tzinfo is None:
                    parsed_date = parsed_date.replace(tzinfo=tz_info)

                # Convert to UTC
                utc_date = parsed_date.astimezone(timezone.utc)
                
                # Format as ISO8601 string
                return utc_date.isoformat()

            except ValueError:
                continue
            except Exception as e:
                if self.debug_enabled:
                    self.logger.debug(f"Error parsing date '{cleaned_date_str}' with format '{fmt}': {e}")
                continue

        return None


    # Transaction email templates
    TEMPLATES = {
        'Huntington Checking/Savings': {
            'iterate_results': False,
            'account': r'(?<=CK)(\d{4})',
            'amount': r'(?<=for \$)(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\b(?=(?: at|$))',
            'vendor': r'(?<= at )(.*?)(?= from)',
            'date': r'(?<=as of )(\d{1,2}\/\d{1,2}\/\d{2}\s+\d{1,2}:\d{2}\s+(?:AM|PM)\s+ET)'
        },
        'Target Credit Card': {
            'iterate_results': False,
            'account': r'(?<=ending in )[\d]{4}',
            'amount': r'(?<=transaction of \$)(\d{1,3}(?:,\d{3})*(?:\.\d+)?)(?= at)',
            'vendor': r'(?s)(?<=\sat\s)(.*?)(?=\s+was)',
            'date': ''
        },
        'US Bank - Credit Card': {
            'iterate_results': False,
            'account': r'(?<=card ending in )\d{4}',
            'amount': r'(?<=charged \$)(.*)(?=  at)',
            'vendor': r'(?<=at )(.*)(?=\. A)',
            'date': ''
        },
        'Chase Payment Sent': {
            'iterate_results': False,
            # capture the 4 digits after "...":
            'account': r'Account ending in[^(]*\(\.\.\.([\d]{4})\)',
            
            # capture the numeric amount:
            'amount': r'You sent \$(\d+(?:,\d{3})*(?:\.\d{2})?)',
            
            # capture the vendor in either "You sent $... to ..." 
            # or from the <td> cell labeled "Recipient":
            # -- Removed the "=+to" and replaced with "\s+to\s+" to match your actual email text.
            'vendor': r'(?:You sent \$[\d,.]+\s+to\s+|Recipient<\/td>\s*<td[^>]*>)([^\r\n]+)',
            
            # capture date from text after "Sent on"
            # -- If your email has <td> tags, you can still rely on them. 
            # -- Otherwise, this simpler pattern grabs the date up to the next "<" (or line break).
            'date': r'Sent on\s*\r?\n\s*([^\r\n<]+)',
            
            # match the subject line format:
            'subject_pattern': r'You sent \$[\d,.]+.*account ending in'
        },
        'Discover Credit Card': {
            'iterate_results': False,
            'account': r'(?<=Last 4 #:&nbsp;)(\d{4})',
            'amount': r'(?<=(\$))(.*)(?=<br\/>)',
            'vendor': r'(?<=(Merchant: ))(.*)(?=<br\/>)',
            'date': r'(?<=(Date: ))(.*)(?=<br\/>)'
        },
        'Discover Transaction Alert': {
            'iterate_results': False,
            'account': r'Account ending in\s+(\d{4})',
            'amount': r'Amount: \$(\d+(?:,\d{3})*(?:\.\d{2})?)',
            'vendor': r'(?s)Merchant:\s+([^\n]+)', #TODO: may need to update all old templates with (?s)
            'date': r'Transaction Date::\s*([^\n]+)',
        },
        'Chase Direct Deposit': {
            'iterate_results': False,
            'account': r'Account ending in[^(]*\(\.\.\.([\d]{4})\)',
            'amount': r'You have a direct deposit of \$(\d+(?:,\d{3})*(?:\.\d{2})?)',
            'vendor': r'Direct Deposit',  # Fixed vendor for direct deposits
            'date': r'>([^<]+(?:AM|PM) ET)</td>'
        },
        'Chase Transaction Alert - New1': {
            'iterate_results': False,
            'account': r'(?:Chase [^(]+\(...(\d{4})\)|Account ending in[^<]*\(...(\d{4})\))',
            'amount': r'(?:You made a \$(\d+(?:,\d{3})*(?:\.\d{2})?) transaction|You have a direct deposit of \$(\d+(?:,\d{3})*(?:\.\d{2})))',
            'vendor': r'(?:transaction with ([^<\n\r]+)|Your \$\d+(?:,\d{3})*(?:\.\d{2})? transaction with ([^<\n\r]+))',
            'date': r'>([^<]+(?:AM|PM) ET)</td>',
            'subject_pattern': r'Your \$[\d,.]+.*(?:transaction with|direct deposit)',
            'subject_vendor': r'transaction with\s+([^<\n\r]+)'  # Extract vendor from subject if not found in body
        },
        'Chase Test Format': {
            'iterate_results': False,
            'account': r'(?<=card ending in )(\d+)',
            'amount': r'\$([0-9,.]+)',
            'vendor': r'(?<=made at )(.+?)(?= using)',
            'date': ''
        },
        'Chase Sapphire Preferred': {
            'iterate_results': False,
            'account': r"(?:Chase [^(]+\(...(\d{4})\)|Account ending in[^<]*\(...(\d{4})\))",
            'amount': r"(?:You made a \$(\d+(?:,\d{3})*(?:\.\d{2})?) transaction|You have a direct deposit of \$(\d+(?:,\d{3})*(?:\.\d{2})))",
            'vendor': r"(?s)Merchant:\s*([^<\n\r]+)",
            'date': r"(?:Date</td>.*?<td[^>]*>([^<]+)</td>)|(?:>([^<]+(?:AM|PM) ET)</td>)"
        },
        'Chase External Transfer': {
            'iterate_results': False,
            'account': r'(?<=ending in )(\d*)(?=.)',
            'amount': r'(?<=A \$)(.*)(?= external)',
            'vendor': r'(?<=to )(.*)(?= on)',
            'date': ''
        },
        'Chase Debit Card': {
            'iterate_results': False,
            'account': r'(?<=ending in )(\d*)(?=.)',
            'amount': r'(?<=A \$)(.*)(?= debit)',
            'vendor': r'(?<=to )(.*)(?= on)',
            'date': ''
        },
        'Chase Checking Acct - Bill Pay': {
            'iterate_results': False,
            'account': r'(?<=ending in )(\d+)',
            'amount': r'\$([0-9,.]+)',
            'vendor': r'(?s)payment to ([^.]+?)(?= on)',
            'date': r'on ([^.]+?)(?= executed)'
        },
        'Chase Credit Cards - HTML Template': {
            'iterate_results': True,
            'account': r'<td[^>]*>(?:<.*?>)*([^<]+)(?:<\/.*?>)*<\/td>',
            'amount': r'<td[^>]*>(?:<.*?>)*([^<]+)(?:<\/.*?>)*<\/td>',
            'vendor': r'<td[^>]*>(?:<.*?>)*([^<]+)(?:<\/.*?>)*<\/td>',
            'date': ''
        },
        'Chase Credit Cards - ??': {
            'iterate_results': False,
            'account': r'(?<=ending in )(\d*)(?=.)',
            'amount': r'(?<=charge of \(\$...\) )(.*)(?= at (.*) on)',
            'vendor': r'(?<=at )(.*)(?= has)',
            'date': ''
        },
        'Capital One Credit Card': {
            'iterate_results': False,
            'account': r'(?<=Account ending in )[\d]{4}',
            'amount': r'(?<=(\$))(.*)(?= was )',
            'vendor': r'(?<= at )(.*)(?=, a)',
            'date': ''
        },
        'Huntington Checking/Savings Deposit': {
            'iterate_results': False,
            'account': r'(?<=CK)(\d{4})',
            'amount': r'(?<=for \$)(([0-9,.]+)*)',
            'vendor': r'(?<= from )(.*)(?= to)',
            'date': ''
        },
        'Huntington Checking/Savings Deposit2': {
            'iterate_results': False,
            'account': r'(?<=CK)(\d{4})',
            'amount': r'(?<=for \$)(([0-9,.]+)*)',
            'vendor': r'(?<= at )(.*)(?= from)',
            'date': ''
        },
        'Chase Payment Alert': {
            'iterate_results': False,
            'account': r'Account ending in[^(]*\(\.\.\.([\d]{4})\)',
            'amount': r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)',
            'vendor': r'(?:You sent \$[\d,.]+\s+to\s+)([^<\n\r]+)',
            'date': r'Sent on\s+([^<]+)'
        }
    }
    
    def __init__(self):
        self.config = Config()
        self.logger = logging.getLogger(__name__)
        self.debug_enabled = True  # Changed to True for debugging
        if not self.debug_enabled:
            self.logger.setLevel(logging.ERROR)
        self.__template_used__ = ''
        self.__transaction_text__ = ''
        self.__transaction_amt__ = None
        self.__transaction_vendor__ = ''
        self.__transaction_account__ = ''
        self.__transaction_date__ = ''
        self.__transaction_id__ = ''
        self.__gmail_id__ = ''  # Add Gmail API ID field
        
    def parse_gmail_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a Gmail message into a transaction"""
        try:
            # Extract message body and headers
            headers = message['payload']['headers']
            body = self._get_message_body(message['payload'])
            
            # Get message IDs
            message_id = message.get('message_id')  # Original Message-ID from headers
            gmail_id = message.get('gmail_id')  # Gmail API ID
            
            # Log message details
            header_dict = {h['name']: h['value'] for h in headers}
            self.logger.info(f"\n=== Processing Email ===")
            self.logger.info(f"Gmail ID: {gmail_id}")
            self.logger.info(f"Subject: {header_dict.get('Subject', 'N/A')}")
            self.logger.info(f"From: {header_dict.get('From', 'N/A')}")
            self.logger.info(f"Date: {header_dict.get('Date', 'N/A')}")
            self.logger.info(f"Body Preview: {body[:200]}...")
            
            # Find matching template
            template_name, matches = self._find_matching_template(headers, body)
            if not template_name or not matches:
                self.logger.warning(f"No matching template found for message {gmail_id}")
                return None
            
            # Extract transaction data using template
            transaction = self._extract_transaction_data(template_name, matches)
            if not transaction:
                self.logger.warning(f"Failed to extract transaction data from message {gmail_id}")
                return None
            
            # Add message IDs
            transaction['id'] = message_id
            transaction['id_api'] = gmail_id
            
            # Add template used
            transaction['template_used'] = template_name
            
            # Log successful parsing
            self.logger.info("\n=== Parsing Results ===")
            self.logger.info(f"Template Used: {template_name}")
            self.logger.info(f"Transaction Details:")
            self.logger.info(f"  - Amount: {transaction.get('amount')}")
            self.logger.info(f"  - Vendor: {transaction.get('vendor')}")
            self.logger.info(f"  - Account: {transaction.get('account')}")
            self.logger.info(f"  - Date: {transaction.get('date')}")
            self.logger.info("====BODY====")
            self.logger.info(f"{body}")
            
            return transaction
        except Exception as e:
            self.logger.error(f"Error parsing Gmail message: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None
        
    def _sanitize_body(self, body: str) -> str:
        """
        Remove potentially malicious or unwanted HTML/scripts/styles,
        and return a cleaned version of the body text.
        """
        # Remove script tags and content
        body = re.sub(r'<script.*?>.*?</script>', '', body, flags=re.DOTALL | re.IGNORECASE)
        # Remove style tags and content
        body = re.sub(r'<style.*?>.*?</style>', '', body, flags=re.DOTALL | re.IGNORECASE)
        # Remove all other HTML tags
        body = re.sub(r'<[^>]+>', '', body)
        return body

    def _get_message_body(self, payload: Dict[str, Any]) -> str:
        """Extract message body from Gmail API payload and sanitize it."""
        raw_body = ''
        if 'body' in payload and payload['body'].get('data'):
            raw_body = base64.urlsafe_b64decode(payload['body']['data']).decode()
        elif 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    raw_body = base64.urlsafe_b64decode(part['body']['data']).decode()
                    break
        
        # Sanitize the body before returning
        sanitized_body = self._sanitize_body(raw_body)
        return sanitized_body
    
    def _get_message_body_old(self, payload: Dict[str, Any]) -> str:
        """Extract message body from Gmail API payload"""
        if 'body' in payload and payload['body'].get('data'):
            return base64.urlsafe_b64decode(payload['body']['data']).decode()
        
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    return base64.urlsafe_b64decode(part['body']['data']).decode()
        
        return ''
    
    def get_dict(self) -> Dict[str, Any]:
        """Get transaction data as a dictionary"""
        result = {
            'id': self.__transaction_id__,
            'id_api': self.__gmail_id__,  # Include Gmail API ID
            'template_used': self.__template_used__,
            'date': self.__transaction_date__,
            'account': self.__transaction_account__,
            'vendor': self.__transaction_vendor__,
            'amount': self.__transaction_amt__
        }
        return result
    
    def __reset__(self):
        """Reset transaction fields"""
        self.__transaction_amt__ = None
        self.__transaction_vendor__ = None
        self.__transaction_account__ = None
        self.__transaction_date__ = None
        self.__template_used__ = None
        self.__transaction_id__ = None
        self.__transaction_text__ = None
        self.__gmail_id__ = ''  # Reset Gmail API ID
        self.logger.debug("Reset transaction fields") 
    
    def _find_matching_template(self, headers: List[Dict[str, str]], body: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Find a matching template for the message"""
        # Convert headers to dict for easier access
        header_dict = {h['name']: h['value'] for h in headers}
        subject = header_dict.get('Subject', '')
        from_addr = header_dict.get('From', '')
        
        self.logger.info("\n=== Template Matching ===")
        
        # Try all templates until one succeeds
        for template_name, template in self.TEMPLATES.items():
            try:
                self.logger.info(f"\nTrying template: {template_name}")
                
                # Check if email_from matches if specified
                if template.get('email_from') and template['email_from'] != from_addr:
                    self.logger.info(f"❌ Skipping - email_from doesn't match")
                    self.logger.info(f"  Expected: {template['email_from']}")
                    self.logger.info(f"  Got: {from_addr}")
                    continue
                
                # Check if subject matches if specified
                if template.get('subject_pattern'):
                    subject_match = re.search(template['subject_pattern'], subject, re.IGNORECASE | re.DOTALL)
                    if not subject_match:
                        self.logger.info(f"❌ Skipping - subject_pattern doesn't match")
                        self.logger.info(f"  Pattern: {template['subject_pattern']}")
                        self.logger.info(f"  Subject: {subject}")
                        continue
                    else:
                        self.logger.info(f"✓ Subject pattern matches")
                
                # Create matches dictionary with all necessary data
                matches = {
                    'subject': subject,
                    'from': from_addr,
                    'headers': headers,
                    'body': body  # Add the body to the matches dictionary
                }
                
                # For templates with iterate_results=True, handle differently
                if template.get('iterate_results', False):
                    cells = re.findall(template['account'], body, re.IGNORECASE | re.DOTALL)
                    if cells:
                        matches['cells'] = cells
                        return template_name, matches
                
                # For non-iterate templates, check if we have matches
                has_matches = False
                matches_found = {}
                
                # Try amount pattern
                if template.get('amount'):
                    amount_matches = list(re.finditer(template['amount'], body, re.IGNORECASE | re.DOTALL))
                    if amount_matches:
                        has_matches = True
                        matches_found['amount'] = amount_matches[0].group(1) if amount_matches[0].groups() else amount_matches[0].group(0)
                        self.logger.info(f"✓ Amount found: {matches_found['amount']}")
                    else:
                        self.logger.info(f"❌ Amount not found - Pattern: {template['amount']}")
                
                # Try vendor pattern
                if template.get('vendor'):
                    if isinstance(template['vendor'], str):
                        if template['vendor'].startswith('(?') or template['vendor'].startswith('(.*?)'):
                            # It's a regex pattern
                            vendor_matches = list(re.finditer(template['vendor'], body, re.IGNORECASE | re.DOTALL))
                            if vendor_matches:
                                has_matches = True
                                # Try each group until we find a non-empty one
                                groups = vendor_matches[0].groups()
                                vendor = next((g for g in groups if g and g.strip()), None)
                                if vendor:
                                    matches_found['vendor'] = vendor.strip()
                                    self.logger.info(f"✓ Vendor found: {matches_found['vendor']}")
                            else:
                                self.logger.info(f"❌ Vendor not found - Pattern: {template['vendor']}")
                        else:
                            # It's a fixed string
                            has_matches = True
                            matches_found['vendor'] = template['vendor']
                            self.logger.info(f"✓ Vendor (fixed): {matches_found['vendor']}")
                
                # Try account pattern
                if template.get('account'):
                    account_matches = list(re.finditer(template['account'], body, re.IGNORECASE | re.DOTALL))
                    if account_matches:
                        has_matches = True
                        matches_found['account'] = account_matches[0].group(1) if account_matches[0].groups() else account_matches[0].group(0)
                        self.logger.info(f"✓ Account found: {matches_found['account']}")
                    else:
                        self.logger.info(f"❌ Account not found - Pattern: {template['account']}")
                
                # Try date pattern
                if template.get('date'):
                    date_matches = list(re.finditer(template['date'], body, re.IGNORECASE | re.DOTALL))
                    if date_matches:
                        matches_found['date'] = date_matches[0].group(1) if date_matches[0].groups() else date_matches[0].group(0)
                        self.logger.info(f"✓ Date found: {matches_found['date']}")
                    else:
                        self.logger.info(f"❌ Date not found - Pattern: {template['date']}")
                
                # Check if we have the minimum required fields
                if 'amount' in matches_found and ('account' in matches_found or 'vendor' in matches_found):
                    self.logger.info(f"\n✓ Found matching template: {template_name}")
                    matches['found'] = matches_found  # Add the found matches to the matches dictionary
                    return template_name, matches
                else:
                    self.logger.info("❌ Missing required fields")
            
            except Exception as e:
                self.logger.error(f"\n❌ Error processing template {template_name}: {str(e)}")
                import traceback
                self.logger.error(traceback.format_exc())
                continue
        
        self.logger.info("\n❌ No matching template found")
        return None, None
    
    def _extract_transaction_data(self, template_name: str, matches: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract transaction data using the matched template"""
        template = self.TEMPLATES[template_name]
        body = matches.get('body', '')
        found_matches = matches.get('found', {})
        
        # Get email date from headers
        header_dict = {h['name']: h['value'] for h in matches.get('headers', [])}
        email_date = header_dict.get('Date')
        if email_date:
                    parsed_email_date = self._parse_date(email_date,email_date)
        
        try:
            # For templates with iterate_results=True
            if template.get('iterate_results', False):
                cells = matches['cells']
                cells = [cell.strip() for cell in cells]
                
                # Find account number, amount, and merchant
                account = None
                amount = None
                merchant = None
                
                for cell in cells:
                    if 'ending in' in cell.lower():
                        account = cell.split()[-1]
                    elif '$' in cell:
                        amount = cell.replace('$', '').replace(',', '')
                    elif not any(x in cell.lower() for x in ['account', 'amount', 'merchant', 'posted']):
                        merchant = cell
                
                # Ensure all required fields are present
                if not all([account, amount, merchant]):
                    return None
                
                return {
                    'account': account,
                    'amount': float(amount),
                    'vendor': merchant,
                    'date': parsed_email_date or datetime.utcnow().isoformat()
                }
            
            # For non-iterate templates
            amount = None
            if 'amount' in found_matches:
                amount_str = found_matches['amount']
                # Remove $ and commas, handle parentheses for negative amounts
                amount_str = amount_str.replace('$', '').replace(',', '')
                if '(' in amount_str and ')' in amount_str:
                    amount_str = '-' + amount_str.replace('(', '').replace(')', '')
                amount = float(amount_str)
                self.logger.debug(f"Found amount: {amount}")
            
            account = None
            if 'account' in found_matches:
                account = found_matches['account'].strip()
                self.logger.debug(f"Found account: {account}")
            
            merchant = None
            if 'vendor' in found_matches:
                merchant = found_matches['vendor'].strip()
                self.logger.debug(f"Found vendor: {merchant}")
            elif template.get('subject_vendor'):
                # Try to get vendor from subject if not found in body
                subject = matches.get('subject', '')
                subject_vendor_match = re.search(template['subject_vendor'], subject, re.IGNORECASE | re.DOTALL)
                if subject_vendor_match:
                    merchant = subject_vendor_match.group(1).strip()
                    self.logger.debug(f"Found vendor from subject: {merchant}")
            
            date = None
            if 'date' in found_matches:
                date_str = found_matches['date']
                date = self._parse_date(date_str, email_date)
                if date:
                    self.logger.debug(f"Found date: {date}")
            
            # If no date from template, try to get from email headers
            if not date and email_date:
                date = self._parse_date(email_date, email_date)
                if date:
                    self.logger.debug(f"Found date from headers: {date}")
            
            # If we have the minimum required fields
            if amount is not None and (account is not None or merchant is not None):
                self.logger.debug(f"Extracted transaction data: amount={amount}, account={account}, merchant={merchant}, date={date},email_date={parsed_email_date}")
                return {
                    'account': account,
                    'amount': amount,
                    'vendor': merchant,
                    'date': date if isinstance(date, str) else (date.isoformat() if date else parsed_email_date),
                    'template_used': template_name
                }
            
            self.logger.debug(f"Missing required fields: amount={amount}, account={account}, merchant={merchant}")
            return None
            
        except Exception as e:
            self.logger.error(f"Error extracting transaction data: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None 