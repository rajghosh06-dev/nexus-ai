import socketio
import requests
import uuid
import datetime

class ChainlitTestClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.sio = socketio.Client()
        self.session_id = str(uuid.uuid4())
        self.messages = []

        @self.sio.on("connect")
        def on_connect():
            print("[Client] Connected to WebSocket")

        @self.sio.on("disconnect")
        def on_disconnect():
            print("[Client] Disconnected from WebSocket")

        @self.sio.on("client_message")
        def on_client_message(data):
            self.messages.append(data)

        @self.sio.on("new_message")
        def on_new_message(data):
            self.messages.append(data)

    def login(self, username, password):
        url = f"{self.base_url}/login"
        resp = self.session.post(
            url,
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        return resp.status_code == 200

    def connect_ws(self, chat_profile="Omni Mode"):
        cookie_header = "; ".join([f"{k}={v}" for k, v in self.session.cookies.get_dict().items()])
        headers = {}
        if cookie_header:
            headers["Cookie"] = cookie_header

        auth = {
            "sessionId": self.session_id,
            "clientType": "webapp",
            "chatProfile": chat_profile,
            "userEnv": "{}"
        }
        
        # Connect to Socket.IO
        self.sio.connect(
            self.base_url,
            headers=headers,
            auth=auth,
            socketio_path="/ws/socket.io"
        )

    def send_message(self, text, file_references=None):
        message_id = str(uuid.uuid4())
        payload = {
            "message": {
                "id": message_id,
                "name": "You",
                "type": "user_message",
                "output": text,
                "createdAt": datetime.datetime.utcnow().isoformat() + "Z"
            },
            "fileReferences": file_references or []
        }
        self.sio.emit("client_message", payload)

    def update_settings(self, settings):
        self.sio.emit("chat_settings_change", settings)

    def trigger_action(self, action_name, action_id, for_msg_id, payload=None):
        url = f"{self.base_url}/project/action"
        data = {
            "sessionId": self.session_id,
            "action": {
                "id": action_id,
                "name": action_name,
                "payload": payload or {},
                "label": action_name,
                "forId": for_msg_id
            }
        }
        resp = self.session.post(url, json=data)
        return resp

    def upload_file(self, filename, content, mime_type):
        url = f"{self.base_url}/project/file"
        params = {"session_id": self.session_id}
        files = {"file": (filename, content, mime_type)}
        resp = self.session.post(url, params=params, files=files)
        return resp

    def disconnect(self):
        if self.sio.connected:
            self.sio.disconnect()
        self.session.close()
