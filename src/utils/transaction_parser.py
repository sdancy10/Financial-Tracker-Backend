from typing import Dict, Any, Optional, List, Tuple, Iterator
import logging
import base64
import re
from datetime import datetime, timedelta
from src.utils.config import Config
from zoneinfo import ZoneInfo
import platform
import html
from email.utils import parsedate_to_datetime
import quopri  # Added import for quoted-printable decoding

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
            'amount': r'(?<=for\s\$)(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\b(?=(?:\s+(?:from|at)|$))',
            'vendor': r'(?<= at )(.+?)(?= from)|(?<=from\s)(.+?)(?= to )',
            'date': r'(?<=as of )(\d{1,2}\/\d{1,2}\/\d{2}\s+\d{1,2}:\d{2}\s+(?:AM|PM)\s+ET)'
        },
        'Target Credit Card': {
            'iterate_results': False,
            'account': r'(?<=ending in )[\d]{4}',
            'amount': r'(?<=transaction of \$)(\d{1,3}(?:,\d{3})*(?:\.\d+)?)(?= at)',
            'vendor': r'(?s)(?<=\sat\s)(.*?)(?=\s+was|\s+has)',
            'date': ''
        },
        'US Bank - Credit Card': {
            'iterate_results': False,
            'account': r'(?<=card ending in )\d{4}',
            'amount': r'\$(\d+(?:\.\d+)?)',
            'vendor': r'(?<=at )([^.]+)',
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
            # 'vendor': r'(?:You sent \$[\d,.]+\s+to\s+|Recipient<\/td>\s*<td[^>]*>)([^\r\n]+)\s*<\/td>)',
            'vendor': r'(?:You sent \$[\d,.]+\s+to\s+([^<\r\n\s]+)|Recipient<\/td>\s*<td[^>]*>\s*([^<\r\n\s]+))',
            
            # capture date from text after "Sent on"
            # -- If your email has <td> tags, you can still rely on them. 
            # -- Otherwise, this simpler pattern grabs the date up to the next "<" (or line break).
            'date': r'Sent on<\/td>[\s\S]*?<td[^>]*>\s*(?:<[^>]+>\s*)*([^<]+(?:AM|PM)\sET)',
            
            # match the subject line format:
            'subject_pattern': r'You sent \$[\d,.]+.*account ending in'
        },
        'Capital One Credit Card': {
            'iterate_results': False,
            'account': r'(?:ending in|card ending in|last 4 #)\s*(\d{4})',
            'amount': r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)',
            'vendor': r'(?s),\s*at\s+([^,]+),',
            'date': r'on\s+(\d{1,2}\/\d{1,2}\/\d{4})(?=,)'
        },
        'Discover Credit Card': {
            'iterate_results': False,
            'account': r'(?:Last 4 #:\s*[ ]*|Account ending in\s*)(\d{4})',
            'amount': r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)',
            'vendor': r'(?:Merchant\s*:+\s*|at\s+)([^<\n\r]+?)(?=\s*(?:Amount:|\s*$|\s*,))',
            'date': r'(?:Date:\s*|Transaction Date:\s*)([^<\n\r]+?)(?=(?:\s*<br\/>|\s*$))'
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
            'account': r'(?:Account ending in[^(]*\(...|ending in)\s*(\d{4})',
            'amount': r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)',
            'vendor': r'(?:made at|transaction with|at\s+|Merchant:\s*|purchase at\s+)([^<\n\r.]+?)(?=(?:\s+using|\s*$|\s*,|\s*\.|<br/>|\s+on))',
            'date': r'(?:on|Date:|Transaction Date:)\s*([^<\n\r]+?)(?=(?:\s*$|\s*<|\s*executed|<br/>))',
            'subject_pattern': r'(?:Chase Alert)'  # Add subject pattern to help with matching
        },
        'Chase Sapphire Preferred': {
            'iterate_results': False,
            'account': r"(?:Chase [^(]+\(...(\d{4})\)|Account ending in[^<]*\(...(\d{4})\))",
            'amount': r"(\$\d+(?:,\d{3})*(?:\.\d{2}))",
            'vendor': r"(?s)(?<=Merchant</td>).*?<td[^>]*>\s*(.*?)\s*</td>",
            'date': r"Date<\/td>[\s\S]*?<td[^>]*>\s*(?:<[^>]+>\s*)*([^<]+(?:AM|PM)\sET)"
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
            'account': r'(?:Chase [^(]+\(...(\d{4})\)|Account ending in[^<]*\(...(\d{4})\))',
            'amount': r'(\$\d+(?:,\d{3})*(?:\.\d{2}))',
            'vendor': r'(?s)(?<=Recipient<\/td>).*?<td[^>]*>\s*(.*?)\s*<\/td>',
            'date': r'Made on<\/td>[\s\S]*?<td[^>]*>\s*(?:<[^>]+>\s*)*([^<]+(?:AM|PM)\sET)'
        },
        'Chase Credit Cards - HTML Template': {
            'iterate_results': True,
            'account': r'<td[^>]*>(?:<.*?>)*([^<]+)(?:<\/.*?>)*<\/td>',
            'amount': r'<td[^>]*>(?:<.*?>)*([^<]+)(?:<\/.*?>)*<\/td>',
            'vendor': r'<td[^>]*>(?:<.*?>)*([^<]+)(?:<\/.*?>)*<\/td>',
            'date': ''
        },
        'Huntington Checking/Savings Deposit': {
            'iterate_results': False,
            'account': r'(?:CK|ending in|Last 4 #|Card ending in?\s*Card ending in|Account #|Account ending in|(?:account )?nicknamed CK)\s*(\d{4})',
            'amount': r'(?:for )?\$(\d+(?:,\d{3})*(?:\.\d{2})?)',
            'vendor': r'(?:from\s+|at\s+|Merchant:\s*)([^<\n\r.]+?)(?=(?:\s+to|\s*$|\s*,|\s*\.|<br/>|\s+on))',
            'date': r'(?:on|Date:|Transaction Date:|as of)\s*([^<\n\r]+?)(?=(?:\s*$|\s*<|\s*executed|<br/>))'
        },
        'Huntington Checking/Savings Deposit2': {
            'iterate_results': False,
            'account': r'(?<=CK)(\d{4})',
            'amount': r'(?<=for \$)(([0-9,.]+)*)',
            'vendor': r'(?<= at)(=?\s*)(.*)(?= from)',
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
            body, raw_body = self._get_message_body(message['payload'])
            
            # Get message IDs
            message_id = message.get('message_id')  # Original Message-ID from headers
            gmail_id = message.get('gmail_id')  # Gmail API ID
            
            # Log message details (concise version)
            header_dict = {h['name']: h['value'] for h in headers}
            subject = header_dict.get('Subject', 'N/A')
            from_addr = header_dict.get('From', 'N/A')
            
            # Only log essential info at INFO level
            self.logger.info(f"Processing email: {subject[:50]}... from {from_addr}")
            
            # Verbose logging at DEBUG level
            self.logger.debug(f"Gmail ID: {gmail_id}")
            self.logger.debug(f"Full Subject: {subject}")
            self.logger.debug(f"Date: {header_dict.get('Date', 'N/A')}")
            self.logger.debug(f"Body Preview: {body[:200]}...")
            
            # Find matching template
            template_name, matches = self._find_matching_template(headers, body, raw_body)
            if not template_name or not matches:
                self.logger.debug(f"No matching template found for message {gmail_id}")
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
            
            # Log successful parsing (concise)
            self.logger.info(f"Successfully parsed: {transaction.get('vendor', 'Unknown')} - ${transaction.get('amount', '0')} using {template_name}")
            
            # Verbose details at DEBUG level
            self.logger.debug(f"Transaction Details:")
            self.logger.debug(f"  - Amount: {transaction.get('amount')}")
            self.logger.debug(f"  - Vendor: {transaction.get('vendor')}")
            self.logger.debug(f"  - Account: {transaction.get('account')}")
            self.logger.debug(f"  - Date: {transaction.get('date')}")
            
            return transaction
        except Exception as e:
            self.logger.error(f"Error parsing Gmail message: {str(e)}")
            import traceback
            self.logger.debug(traceback.format_exc())  # Full traceback at DEBUG level
            return None
        
    def _sanitize_body(self, body: str) -> str:
        """
        Remove potentially malicious or unwanted HTML/scripts/styles,
        remove all HTML tags, and decode entities like ’ or /.
        """
        if not body:
            return ""
        
        # Decode quoted-printable first to handle soft breaks
        body = quopri.decodestring(body.encode('utf-8')).decode('utf-8', errors='replace')
            
        # Remove script tags and content
        body = re.sub(r'<script.*?>.*?</script>', '', body, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove style tags and content
        body = re.sub(r'<style.*?>.*?</style>', '', body, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove all HTML comments
        body = re.sub(r'<!--.*?-->', '', body, flags=re.DOTALL)
        
        # Remove all other HTML tags but preserve their content
        body = re.sub(r'<[^>]+>', ' ', body)
        
        # Replace multiple spaces/newlines with single space
        body = re.sub(r'\s+', ' ', body)
        
        # Decode HTML entities (e.g. ’ -> ', / -> /,   -> space)
        body = html.unescape(body)
        
        # Remove any remaining HTML-like artifacts
        body = re.sub(r'&[a-zA-Z0-9#]+;', '', body)
        
        # Clean up any remaining special characters
        body = re.sub(r'[^\x20-\x7E\n]', '', body)
        
        # Trim extra whitespace
        body = body.strip()
        
        return body

    def _get_message_body(self, payload: Dict[str, Any]) -> Tuple[str, str]:
        """Extract message body from Gmail API payload and sanitize it.
        Returns (sanitized_body, raw_body).
        """        
        def find_html_parts(part: Dict[str, Any]) -> Iterator[str]:
            """Recursively yield all *base64-encoded* HTML part-data from a message."""
            if 'parts' in part:  # If this part has sub-parts, recurse
                for sub_part in part['parts']:
                    yield from find_html_parts(sub_part)
            else:
                # If this part is exactly text/html, yield its base64 data
                if part.get('mimeType') == 'text/html':
                    data = part.get('body', {}).get('data', '')
                    if data:
                        # Handle case where data might be a list
                        if isinstance(data, list):
                            # Join all non-empty elements into a single string
                            data = ''.join(str(d) for d in data if d and str(d).strip())
                        yield data
        
        # 1) Initialize a fallback raw_body (in case there's no HTML at all)
        raw_body = ''
        
        # 2) If top-level has 'body' data (single-part), decode it
        body_data = payload.get('body', {}).get('data')
        if body_data:
            try:
                # Handle case where data might be a list
                if isinstance(body_data, list):
                    # Join all non-empty elements into a single string
                    body_data = ''.join(str(d) for d in body_data if d and str(d).strip())
                raw_body = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='replace')
            except Exception as e:
                self.logger.error(f"Failed to decode top-level body: {str(e)}")
                self.logger.error(f"Body data type: {type(body_data)}")
                if isinstance(body_data, (str, bytes)):
                    self.logger.error(f"Body data length: {len(body_data)}")
                    self.logger.error(f"Body data sample: {str(body_data[:100])}")
        
        # 3) If it's multipart, we can also look for text/plain as a fallback
        elif 'parts' in payload:
            for part in payload['parts']:
                if part.get('mimeType') == 'text/plain' and part.get('body', {}).get('data'):
                    try:
                        part_data = part['body']['data']
                        # Handle case where data might be a list
                        if isinstance(part_data, list):
                            # Join all non-empty elements into a single string
                            part_data = ''.join(str(d) for d in part_data if d and str(d).strip())
                        raw_body = base64.urlsafe_b64decode(part_data).decode('utf-8', errors='replace')
                        break
                    except Exception as e:
                        self.logger.error(f"Failed to decode text/plain part: {str(e)}")
                        self.logger.error(f"Part data type: {type(part_data)}")
                        if isinstance(part_data, (str, bytes)):
                            self.logger.error(f"Part data length: {len(part_data)}")
                            self.logger.error(f"Part data sample: {str(part_data[:100])}")
                        continue
        
        # 4) Now gather all text/html parts, recursively
        html_parts = list(find_html_parts(payload))

        if html_parts:
            # Decode each HTML part and concatenate them
            decoded_all_html = []
            for encoded_html in html_parts:
                try:
                    # Handle case where data might be a list
                    if isinstance(encoded_html, list):
                        # Join all non-empty elements into a single string
                        encoded_html = ''.join(str(d) for d in encoded_html if d and str(d).strip())
                    decoded_html = base64.urlsafe_b64decode(encoded_html).decode('utf-8', errors='replace')
                    decoded_all_html.append(decoded_html)
                except Exception as e:
                    self.logger.error(f"Failed to decode HTML part: {str(e)}")
                    self.logger.error(f"HTML part type: {type(encoded_html)}")
                    if isinstance(encoded_html, (str, bytes)):
                        self.logger.error(f"HTML part length: {len(encoded_html)}")
                        self.logger.error(f"HTML part sample: {str(encoded_html[:100])}")
                    continue
            
            # Combine them with a separator (e.g. two line breaks)
            if decoded_all_html:
                raw_body = "\n\n".join(decoded_all_html)

        # 5) Sanitize the combined raw_body however you like
        sanitized_body = self._sanitize_body(raw_body)

        return (sanitized_body, raw_body)

    
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
    
    def _find_matching_template(self, headers: List[Dict[str, str]], body: str, raw_body: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Find a matching template for the message by checking both raw and sanitized body"""
        # Convert headers to dict for easier access
        header_dict = {h['name']: h['value'] for h in headers}
        subject = header_dict.get('Subject', '')
        from_addr = header_dict.get('From', '')
        
        self.logger.debug("Starting template matching...")
        
        # Try all templates until one succeeds
        for template_name, template in self.TEMPLATES.items():
            try:
                self.logger.debug(f"Trying template: {template_name}")
                
                # Check if email_from matches if specified
                if template.get('email_from') and template['email_from'] != from_addr:
                    self.logger.debug(f"❌  Skipping - email_from doesn't match")
                    continue
                
                # Check if subject matches if specified
                if template.get('subject_pattern'):
                    subject_match = re.search(template['subject_pattern'], subject, re.IGNORECASE | re.DOTALL)
                    if not subject_match:
                        self.logger.debug(f"❌  Skipping - subject_pattern doesn't match")
                        continue
                    else:
                        self.logger.debug(f"✓  Subject pattern matches")
                
                # Try matching against both raw and sanitized body
                for body_type, current_body in [('sanitized', body),('raw', raw_body)]:
                    self.logger.debug(f"  Trying {body_type} body")
                    
                    # Create matches dictionary with all necessary data
                    matches = {
                        'subject': subject,
                        'from': from_addr,
                        'headers': headers,
                        'body': current_body,
                        'body_type': body_type,
                        'raw_body': raw_body,
                        'sanitized_body': body
                    }
                    
                    # For templates with iterate_results=True, handle differently
                    if template.get('iterate_results', False):
                        cells = re.findall(template['account'], current_body, re.IGNORECASE | re.DOTALL)
                        if cells:
                            matches['cells'] = cells
                            self.logger.debug(f"✓  Found matching cells in {body_type} body")
                            return template_name, matches
                    
                    # For non-iterate templates, check if we have matches
                    has_matches = False
                    matches_found = {}
                    
                    # Try amount pattern
                    if template.get('amount'):
                        amount_matches = list(re.finditer(template['amount'], current_body, re.IGNORECASE | re.DOTALL))
                        if amount_matches:
                            has_matches = True
                            matches_found['amount'] = amount_matches[0].group(1) if amount_matches[0].groups() else amount_matches[0].group(0)
                            self.logger.debug(f"✓  Amount found in {body_type} body: {matches_found['amount']}")
                        else:
                            self.logger.debug(f"❌  Amount not found in {body_type} body - Pattern: {template['amount']}")
                    
                    # Try vendor pattern
                    if template.get('vendor'):
                        if isinstance(template['vendor'], str):
                            if template['vendor'].startswith('(?') or template['vendor'].startswith('(.*?)'):
                                # It's a regex pattern
                                vendor_matches = list(re.finditer(template['vendor'], current_body, re.IGNORECASE | re.DOTALL))
                                if vendor_matches:
                                    has_matches = True
                                    # Try each group until we find a non-empty one
                                    groups = vendor_matches[0].groups()
                                    vendor = next((g.strip() for g in groups if g), None)
                                    if vendor:
                                        matches_found['vendor'] = vendor
                                        self.logger.debug(f"✓  Vendor found in {body_type} body: {matches_found['vendor']}")
                                else:
                                    self.logger.debug(f"❌  Vendor not found in {body_type} body - Pattern: {template['vendor']}")
                            elif template['vendor'].startswith('Merchant'):
                                # Special handling for Merchant pattern
                                vendor_matches = list(re.finditer(template['vendor'], current_body, re.IGNORECASE | re.DOTALL))
                                if vendor_matches:
                                    has_matches = True
                                    # Get the first group if it exists, otherwise get the full match
                                    vendor = vendor_matches[0].group(1) if vendor_matches[0].groups() else vendor_matches[0].group(0)
                                    if vendor:
                                        matches_found['vendor'] = vendor.strip()
                                        self.logger.debug(f"✓  Vendor found in {body_type} body: {matches_found['vendor']}")
                                        self.logger.debug(f"Full vendor match: {vendor_matches[0].group(0)}")
                                else:
                                    self.logger.debug(f"❌  Vendor not found in {body_type} body - Pattern: {template['vendor']}")
                            else:
                                # It's a fixed string
                                has_matches = True
                                matches_found['vendor'] = template['vendor']
                                self.logger.debug(f"✓  Vendor (fixed) in {body_type} body: {matches_found['vendor']}")
                    
                    # Try account pattern
                    if template.get('account'):
                        account_matches = list(re.finditer(template['account'], current_body, re.IGNORECASE | re.DOTALL))
                        if account_matches:
                            has_matches = True
                            matches_found['account'] = account_matches[0].group(1) if account_matches[0].groups() else account_matches[0].group(0)
                            self.logger.debug(f"✓  Account found in {body_type} body: {matches_found['account']}")
                        else:
                            self.logger.debug(f"❌  Account not found in {body_type} body - Pattern: {template['account']}")
                    
                    # Try date pattern
                    if template.get('date'):
                        date_matches = list(re.finditer(template['date'], current_body, re.IGNORECASE | re.DOTALL))
                        if date_matches:
                            matches_found['date'] = date_matches[0].group(1) if date_matches[0].groups() else date_matches[0].group(0)
                            self.logger.debug(f"✓  Date found in {body_type} body: {matches_found['date']}")
                        else:
                            self.logger.debug(f"❌  Date not found in {body_type} body - Pattern: {template['date']}")
                    
                    # Check if the template has a date pattern defined
                    date_required = 'date' in template and template['date'] != ''
                    
                    if 'amount' in matches_found and 'account' in matches_found and 'vendor' in matches_found and (not date_required or 'date' in matches_found):
                        self.logger.debug(f"\n✓  Found matching template: {template_name} in {body_type} body")
                        matches['found'] = matches_found  # Add the found matches to the matches dictionary
                        return template_name, matches
                    else:
                        missing = []
                        if 'amount' not in matches_found:
                            missing.append('amount')
                        if 'account' not in matches_found:
                            missing.append('account')
                        if 'vendor' not in matches_found:
                            missing.append('vendor')
                        if 'date' not in matches_found:
                            missing.append('date')
                        self.logger.debug(f"❌  Missing required fields in {body_type} body: {', '.join(missing)}")
            
            except Exception as e:
                self.logger.error(f"\n❌ Error processing template {template_name}: {str(e)}")
                import traceback
                self.logger.error(traceback.format_exc())
                continue
        
        self.logger.debug("\n❌  No matching template found in either raw or sanitized body")
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