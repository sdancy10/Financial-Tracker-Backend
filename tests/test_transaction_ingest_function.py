"""Tests for src.services.transaction_ingest_function."""

import json
import types
import sys
import unittest
from unittest.mock import patch, MagicMock


def _mock_module(name, parent=None):
    """Create a mock module that behaves like a real package."""
    mod = types.ModuleType(name)
    mod.__path__ = []  # marks it as a package
    mod.__package__ = name
    # Make attribute access return MagicMock for any name
    mod.__class__ = type(name, (types.ModuleType,), {
        '__getattr__': lambda self, attr: MagicMock()
    })
    sys.modules[name] = mod
    if parent and hasattr(parent, name.split('.')[-1]):
        pass
    if parent is not None:
        setattr(parent, name.split('.')[-1], mod)
    return mod


# Build the mock module tree
_google = _mock_module('google')
_google_cloud = _mock_module('google.cloud', _google)
_mock_module('google.cloud.storage', _google_cloud)
_mock_module('google.cloud.firestore', _google_cloud)
_fv1 = _mock_module('google.cloud.firestore_v1', _google_cloud)
_mock_module('google.cloud.firestore_v1.base_query', _fv1)
_mock_module('google.cloud.secret_manager', _google_cloud)
_mock_module('google.cloud.bigquery', _google_cloud)
_mock_module('google.cloud.aiplatform', _google_cloud)

_sklearn = _mock_module('sklearn')
_mock_module('sklearn.compose', _sklearn)
_mock_module('sklearn.pipeline', _sklearn)
_sk_fe = _mock_module('sklearn.feature_extraction', _sklearn)
_mock_module('sklearn.feature_extraction.text', _sk_fe)
_mock_module('sklearn.multioutput', _sklearn)
_mock_module('sklearn.ensemble', _sklearn)
_mock_module('sklearn.preprocessing', _sklearn)
_sk_ms = _mock_module('sklearn.model_selection', _sklearn)
_mock_module('sklearn.metrics', _sklearn)

_nltk = _mock_module('nltk')
_mock_module('nltk.corpus', _nltk)
_mock_module('nltk.tokenize', _nltk)
_mock_module('nltk.stem', _nltk)
_mock_module('nltk.data', _nltk)

_mock_module('joblib')
_mock_module('metaphone')
_mock_module('pandas')
_mock_module('numpy')
_mock_module('pyarrow')
_mock_module('yaml')

from src.services.transaction_ingest_function import ingest_transactions_http


def _make_request(data=None, method='POST'):
    req = MagicMock()
    req.method = method
    req.get_json.return_value = data
    return req


def _sample_txn(**overrides):
    txn = {
        'id': 'cl_001',
        'vendor': 'WHOLE FOODS',
        'amount': 47.23,
        'date': '2026-02-04T15:30:00+00:00',
        'account': 'CB_1234',
        'template_used': 'Coinbase One Credit Card',
    }
    txn.update(overrides)
    return txn


class TestIngestValidation(unittest.TestCase):

    def test_missing_body(self):
        body, status, _ = ingest_transactions_http(_make_request(None))
        self.assertEqual(status, 400)
        self.assertIn('user_id', json.loads(body)['error'])

    def test_missing_user_id(self):
        body, status, _ = ingest_transactions_http(
            _make_request({'transactions': [_sample_txn()]})
        )
        self.assertEqual(status, 400)
        self.assertIn('user_id', json.loads(body)['error'])

    def test_missing_transactions(self):
        body, status, _ = ingest_transactions_http(
            _make_request({'user_id': 'u1'})
        )
        self.assertEqual(status, 400)
        self.assertIn('transactions', json.loads(body)['error'])

    def test_empty_transactions(self):
        body, status, _ = ingest_transactions_http(
            _make_request({'user_id': 'u1', 'transactions': []})
        )
        self.assertEqual(status, 400)

    def test_missing_required_field(self):
        txn = _sample_txn()
        del txn['vendor']
        body, status, _ = ingest_transactions_http(
            _make_request({'user_id': 'u1', 'transactions': [txn]})
        )
        self.assertEqual(status, 400)
        self.assertIn('vendor', json.loads(body)['error'])

    def test_options_cors(self):
        body, status, headers = ingest_transactions_http(_make_request(method='OPTIONS'))
        self.assertEqual(status, 204)
        self.assertIn('Access-Control-Allow-Origin', headers)


class TestIngestHappyPath(unittest.TestCase):

    @patch('src.services.transaction_ingest_function._get_transaction_dao')
    @patch('src.services.transaction_ingest_function._MODEL')
    @patch('src.services.transaction_ingest_function._FEATURE_ENGINEER')
    @patch('src.services.transaction_ingest_function._load_model_if_needed')
    def test_predict_and_store(self, mock_load, mock_fe, mock_model, mock_dao_fn):
        mock_fe.prepare_for_prediction.return_value = MagicMock()
        mock_model.predict.return_value = [['Groceries', 'Supermarket']]

        mock_dao = MagicMock()
        mock_dao.store_transactions_batch.return_value = True
        mock_dao_fn.return_value = mock_dao

        txns = [_sample_txn()]
        body, status, _ = ingest_transactions_http(
            _make_request({'user_id': 'u1', 'transactions': txns})
        )

        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['total'], 1)
        self.assertTrue(result['stored'])
        self.assertEqual(result['predictions_applied'], 1)

        mock_dao.store_transactions_batch.assert_called_once()
        stored_txns = mock_dao.store_transactions_batch.call_args.args[0]
        self.assertEqual(stored_txns[0]['predicted_category'], 'Groceries')
        self.assertEqual(stored_txns[0]['predicted_subcategory'], 'Supermarket')

    @patch('src.services.transaction_ingest_function._get_transaction_dao')
    @patch('src.services.transaction_ingest_function._MODEL')
    @patch('src.services.transaction_ingest_function._FEATURE_ENGINEER')
    @patch('src.services.transaction_ingest_function._load_model_if_needed')
    def test_multiple_transactions(self, mock_load, mock_fe, mock_model, mock_dao_fn):
        mock_fe.prepare_for_prediction.return_value = MagicMock()
        mock_model.predict.return_value = [
            ['Groceries', 'Supermarket'],
            ['Dining', 'Restaurant'],
        ]

        mock_dao = MagicMock()
        mock_dao.store_transactions_batch.return_value = True
        mock_dao_fn.return_value = mock_dao

        txns = [_sample_txn(id='cl_001'), _sample_txn(id='cl_002', vendor='CHIPOTLE')]
        body, status, _ = ingest_transactions_http(
            _make_request({'user_id': 'u1', 'transactions': txns})
        )

        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['predictions_applied'], 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
