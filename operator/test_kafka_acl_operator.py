import unittest
from unittest.mock import patch, MagicMock
# Assuming the functions are in a module named kafka_acl_operator
from kafka_acl_operator import apply_kafka_acl, delete_kafka_acl, get_kafka_acl, ns_kafka_acl


class TestKafkaAclOperator(unittest.TestCase):

    @patch('kafka_acl_operator.kafka_admin_client')
    def test_apply_kafka_acl(self, mock_kafka_admin_client):
        mock_kafka_admin_client.create_acls = MagicMock()
        test_cases = [
            ('User:wow', 'TOPIC', ['test-v1'], 'READ', 'ALLOW', 'PREFIXED', 'Namespace'),
            ('User:foo', 'TOPIC', ['test-v2'], 'WRITE', 'ALLOW', 'LITERAL', 'Cluster level'),
            ('User:bar', 'TOPIC', ['test-v3'], 'READ', 'DENY', 'PREFIXED', 'Namespace'),
            # Add more test cases here...
        ]

        for case in test_cases:
            # Act
            apply_kafka_acl(*case)

            # Assert
            mock_kafka_admin_client.create_acls.assert_called_once()

            # Reset mock for the next test case
            mock_kafka_admin_client.reset_mock()

    @patch('kafka_acl_operator.kafka_admin_client')
    def test_delete_kafka_acl(self, mock_kafka_admin_client):
        mock_kafka_admin_client.delete_acls = MagicMock()
        delete_kafka_acl('User:test', 'TOPIC', ['test-topic'], 'READ', 'ALLOW', 'LITERAL', 'test-scope')
        mock_kafka_admin_client.delete_acls.assert_called_once()

    @patch('kafka_acl_operator.api')
    def test_get_kafka_acl(self, mock_api):
        mock_api.get_namespaced_custom_object = MagicMock(return_value={'spec': {'resourceName': ['test-resource']}})
        result = get_kafka_acl('test-namespace', 'test-acl-name')
        self.assertEqual(result, ['test-resource'])

    @patch('kafka_acl_operator.rq.get')
    def test_ns_kafka_acl(self, mock_rq_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {'data': [{'principal': 'User:test', 'operation': 'READ', 'resource_name': 'test-resource'}]}
        mock_rq_get.return_value = mock_response
        result = ns_kafka_acl('User:test', 'READ')
        self.assertEqual(result, ['test-resource'])

if __name__ == '__main__':
    unittest.main()