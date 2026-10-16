"""Bounded, request-local parsing of an optional leading emotion marker.

    [[emotion:happy]]\nReply text

Only the first prefix is control data. Once body mode begins, text is verbatim.
Malformed headers end at ]], a newline, or MAX_HEADER_CHARS, whichever comes first.
After that boundary the rest is body, even for malformed model output. This bounds
both retained memory and discarded text rather than waiting for an unlimited line.
"""
from dataclasses import dataclass

from app.contracts.emotion import Emotion


EMOTION_PREFIX = "[[emotion:"
MAX_HEADER_CHARS = 64


@dataclass(frozen=True)
class ParsedEmotionResponse:
    emotion: Emotion
    text: str


class EmotionResponseParser:
    def __init__(self):
        self.emotion = None  # None until the prefix decision is final.
        self._header = ""
        self._state = "prefix"
        self._closed = False

    @property
    def buffered_chars(self):
        return len(self._header) + (1 if self._state == "separator_cr" else 0)

    def _resolve(self, emotion=Emotion.NONE, *, separator=False):
        self.emotion = emotion
        self._header = ""
        self._state = "separator" if separator else "body"

    def feed(self, chunk: str) -> str:
        if self._closed:
            return ""
        output = []
        for index, char in enumerate(chunk):
            if self._state == "body":
                output.append(chunk[index:])
                break
            if self._state == "separator":
                if char == "\r":
                    self._state = "separator_cr"
                else:
                    self._state = "body"
                    if char != "\n":
                        output.append(char)
                continue
            if self._state == "separator_cr":
                self._state = "body"
                if char != "\n":
                    output.append("\r" + char)
                continue

            self._header += char
            if self._state == "prefix":
                if self._header == EMOTION_PREFIX:
                    self._state = "header"
                elif not EMOTION_PREFIX.startswith(self._header):
                    output.append(self._header)
                    self._resolve()
                continue

            if self._header.endswith("]]"):
                value = self._header[len(EMOTION_PREFIX):-2]
                try:
                    emotion = Emotion(value)
                except ValueError:
                    emotion = Emotion.NONE
                self._resolve(emotion, separator=True)
            elif char in "\r\n":
                self._resolve()
                if char == "\r":
                    self._state = "separator_cr"
            elif len(self._header) >= MAX_HEADER_CHARS:
                self._resolve()
        return "".join(output)

    def finish(self) -> str:
        """Flush once; callers accumulate feed/finish output for UI and history."""
        if self._closed:
            return ""
        self._closed = True
        tail = self._header if self._state == "prefix" else ""
        if self._state == "separator_cr":
            tail = "\r"
        if self.emotion is None:
            self.emotion = Emotion.NONE
        self._header = ""
        self._state = "body"
        return tail


def parse_emotion_response(text: str) -> ParsedEmotionResponse:
    """Non-streaming callers use exactly the same parser."""
    parser = EmotionResponseParser()
    body = parser.feed(text) + parser.finish()
    return ParsedEmotionResponse(parser.emotion, body)
