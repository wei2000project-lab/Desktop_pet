import threading
from typing import Callable, Any, Dict, List
from PySide6.QtCore import QObject, Signal, Slot
from app.utils.logger import logger

class EventBus(QObject):
    # Signal used to safely dispatch events on the main thread
    event_emitted = Signal(str, tuple, dict)
    
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(EventBus, cls).__new__(cls)
            return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            super().__init__()
            self._initialized = True
            self._listeners: Dict[str, List[Callable[..., None]]] = {}
            self._listener_lock = threading.Lock()
            # Connect the signal to our dispatcher (automatically queued across threads if needed)
            self.event_emitted.connect(self._dispatch_event)

    def subscribe(self, event_type: str, callback: Callable[..., None]):
        with self._listener_lock:
            if event_type not in self._listeners:
                self._listeners[event_type] = []
            if callback not in self._listeners[event_type]:
                self._listeners[event_type].append(callback)
                logger.debug(f"Subscribed callback to event: {event_type}")

    def unsubscribe(self, event_type: str, callback: Callable[..., None]):
        with self._listener_lock:
            if event_type in self._listeners:
                try:
                    self._listeners[event_type].remove(callback)
                    logger.debug(f"Unsubscribed callback from event: {event_type}")
                except ValueError:
                    pass

    def publish(self, event_type: str, *args, **kwargs):
        """Publishes an event. Safe to call from any thread."""
        self.event_emitted.emit(event_type, args, kwargs)

    @Slot(str, tuple, dict)
    def _dispatch_event(self, event_type: str, args: tuple, kwargs: dict):
        callbacks = []
        with self._listener_lock:
            if event_type in self._listeners:
                callbacks = list(self._listeners[event_type])
        
        for callback in callbacks:
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in listener for event {event_type}: {e}", exc_info=True)

event_bus = EventBus()
