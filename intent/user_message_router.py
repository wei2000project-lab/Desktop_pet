from intent.intent_router import IntentType, route_intent


class UserMessageRouter:
    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.event_bus.subscribe("user_message_sent", self.handle_user_message)

    def handle_user_message(self, user_text: str):
        intent = route_intent(user_text)
        if intent.type == IntentType.APP_PREFERENCE_CHANGE:
            self.event_bus.publish("app_preference_change_requested", intent.text)
            return
        if intent.type == IntentType.OPEN_APP:
            self.event_bus.publish("app_open_requested", intent.text)
            return

        self.event_bus.publish("chat_message_requested", intent.text)
