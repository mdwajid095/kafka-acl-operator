import unittest
from unittest.mock import patch, MagicMock
from kafka_acl_operator import apply_kafka_acl, delete_kafka_acl

class TestKafkaACL(unittest.TestCase):
    @patch('kafka_acl_operator.kafka_admin_client')
    def test_apply_kafka_acl(self, mock_admin_client):
        # Arrange
        mock_acl_binding = MagicMock()
        mock_admin_client.create_acls.return_value = [mock_acl_binding]

        test_cases = [
            ('User:wow', 'TOPIC', 'test-v1', 'READ', 'ALLOW', 'LITERAL', 'Cluster level'),
            ('User:foo', 'TOPIC', 'test-v2', 'WRITE', 'ALLOW', 'LITERAL', 'Cluster level'),
            ('User:bar', 'TOPIC', 'test-v3', 'READ', 'DENY', 'PREFIXED', 'Cluster level'),
            # Add more test cases here...
        ]

        for case in test_cases:
            # Act
            apply_kafka_acl(*case)

            # Assert
            mock_admin_client.create_acls.assert_called_once()

            # Reset mock for the next test case
            mock_admin_client.reset_mock()

    @patch('kafka_acl_operator.kafka_admin_client')
    def test_delete_kafka_acl(self, mock_admin_client):
        mock_acl_binding_filter = MagicMock()
        mock_admin_client.delete_acls.return_value = [mock_acl_binding_filter]

        delete_kafka_acl('User:wow', 'TOPIC', 'test-v1', 'WRITE', 'ALLOW', 'LITERAL', 'Cluster level')

        mock_admin_client.delete_acls.assert_called_once()

if __name__ == '__main__':
    unittest.main()
