"""Start TensorBoard with compatibility shims for the bundled protobuf.

The Isaac Gym environment currently contains TensorBoard 2.14 and protobuf
5.29.  TensorBoard's HParams plugin still passes the protobuf-4 keyword
``including_default_value_fields``; protobuf 5 renamed it.  The resulting
request-time exception makes the TensorBoard page appear to hang or fail even
though port 6006 is listening.  Translate that one keyword before TensorBoard
loads its plugins.
"""

from __future__ import annotations

from google.protobuf import json_format


_message_to_json = json_format.MessageToJson


def _message_to_json_compat(message, *args, **kwargs):
    if "including_default_value_fields" in kwargs:
        value = kwargs.pop("including_default_value_fields")
        kwargs.setdefault("always_print_fields_with_no_presence", value)
    return _message_to_json(message, *args, **kwargs)


json_format.MessageToJson = _message_to_json_compat

from tensorboard.main import run_main  # noqa: E402  (patch must run first)


if __name__ == "__main__":
    run_main()
