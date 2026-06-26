import unittest
from tests.client import ChainlitTestClient

class TestSanity(unittest.TestCase):
    def setUp(self):
        self.client = ChainlitTestClient("http://localhost:8000")

    def tearDown(self):
        self.client.disconnect()

    def test_login_and_websocket_connection(self):
        # Use passwordless credentials where username == password
        username = "testuser"
        password = "testuser"
        
        # 1. Login
        logged_in = self.client.login(username, password)
        self.assertTrue(logged_in, "Failed to login with passwordless user")
        
        # 2. Connect WebSocket
        self.client.connect_ws(chat_profile="Omni Mode")
        self.assertTrue(self.client.sio.connected, "Socket.IO client failed to connect to /ws/socket.io")
        
        # 3. Disconnect
        self.client.disconnect()
        self.assertFalse(self.client.sio.connected, "Socket.IO client failed to disconnect cleanly")
