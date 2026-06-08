"""
Test parsing of Croghan Colonial Bank account-activity alert emails.

Croghan sends HTML "Any Account Activity" alerts (from alerts@croghan.com) that
contain account/transaction details but no merchant and no in-body date. The
transaction "Type" is used as the vendor, and the date falls back to the email
header. Body below mirrors a real message (decoded from quoted-printable).
"""

import os
import sys
import unittest

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from src.utils.transaction_parser import TransactionParser
from src.mock.api.mock_gmail_synthetic_api import create_mock_message

# Representative Croghan body (HTML decoded from the real quoted-printable email).
CROGHAN_BODY = (
    '<div class="bodytext">A transaction has posted:<br/><br/><br/>'
    '<u>Account details:</u><br/><p style="margin-left: 40px"><br/>'
    '    <i>Type</i>: Checking<br/><br/>    <i>Number</i>: x0574<br/></p><br/>'
    '<u>Transaction details:</u><br/><p style="margin-left: 40px"><br/>'
    '    <i>Type</i>: External Deposit<br/><br/>    <i>Amount</i>: $1,500.00<br/></p><br/>'
    'Please click <a href="https://secure.myvirtualbranch.com/croghan/SignIn.px">here</a> '
    'to log in to online banking or contact us with any questions.</div>'
)


class TestCroghanTemplate(unittest.TestCase):
    """Validate the 'Croghan Colonial Bank - Account Activity' template."""

    def setUp(self):
        self.parser = TransactionParser()

    def test_account_activity_alert(self):
        message = create_mock_message(
            subject="Croghan Colonial Bank: Any Account Activity",
            body=CROGHAN_BODY,
            from_addr='"Croghan Colonial Bank" <alerts@croghan.com>',
            date="4 Jun 2026 05:18:09 -0400",
        )

        result = self.parser.parse_gmail_message(message)

        self.assertIsNotNone(result, "Croghan email should match a template")
        self.assertEqual(result['template_used'], 'Croghan Colonial Bank - Account Activity')
        self.assertEqual(result['account'], '0574')
        self.assertEqual(result['amount'], 1500.00)
        self.assertEqual(result['vendor'], 'External Deposit')  # transaction "Type" used as vendor
        # No date in body -> derived from the weekday-less header (-0400 -> UTC).
        self.assertEqual(result['date'], '2026-06-04T09:18:09+00:00')

    def test_vendor_is_transaction_type_not_account_type(self):
        """The vendor must be the transaction Type, not the account Type ('Checking')."""
        message = create_mock_message(
            subject="Croghan Colonial Bank: Any Account Activity",
            body=CROGHAN_BODY,
            from_addr='"Croghan Colonial Bank" <alerts@croghan.com>',
            date="4 Jun 2026 05:18:09 -0400",
        )
        result = self.parser.parse_gmail_message(message)
        self.assertIsNotNone(result)
        self.assertNotEqual(result['vendor'], 'Checking')


if __name__ == '__main__':
    unittest.main(verbosity=2)
