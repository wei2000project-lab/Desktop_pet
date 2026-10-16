"""Synchronous event source for deterministic emotion lifecycle tests."""


class EmotionTestBus:
    def __init__(self):
        self.listeners = {}
        self.events = []

    def subscribe(self, name, callback):
        self.listeners.setdefault(name, []).append(callback)

    def unsubscribe(self, name, callback):
        self.listeners[name].remove(callback)

    def publish(self, name, *args):
        self.events.append((name, args))
        for callback in list(self.listeners.get(name, [])):
            callback(*args)

    def values(self, name):
        return [args[0] for event, args in self.events if event == name]
