from flask_socketio import SocketIO

socketio = SocketIO(message_queue="amqp://colossus07/socketio")

room = "TrackingAdvisorLogin-4CKD9Y"
namespace = "/auth"
socketio.emit("authclientrequest", {"msg": "hello world"}, namespace=namespace, room=room)

print("done")
