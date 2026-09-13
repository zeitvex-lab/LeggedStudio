"""Lightweight IO utilities for GenesisLab.

Currently this module re-exports a subset of Isaac Lab's IO helpers so that
code can depend on :mod:`genesislab.utils.io` instead of :mod:`isaaclab.utils.io`.
"""

from __future__ import annotations
import re

__all__ = ["dump_yaml"]
import inspect
import os, yaml

import torch

from typing import Any, Callable

def callable_to_string(value: Callable) -> str:
    """Converts a callable object to a string.

    Args:
        value: A callable object.

    Raises:
        ValueError: When the input argument is not a callable object.

    Returns:
        A string representation of the callable object.
    """
    # check if callable
    if not callable(value):
        raise ValueError(f"The input argument is not callable: {value}.")
    # check if lambda function
    if value.__name__ == "<lambda>":
        # we resolve the lambda expression by checking the source code and extracting the line with lambda expression
        # we also remove any comments from the line
        lambda_line = inspect.getsourcelines(value)[0][0].strip().split("lambda")[1].strip().split(",")[0]
        lambda_line = re.sub(r"#.*$", "", lambda_line).rstrip()
        return f"lambda {lambda_line}"
    else:
        # get the module and function name
        module_name = value.__module__
        function_name = value.__name__
        # return the string
        return f"{module_name}:{function_name}"

def class_to_dict(obj: object) -> dict[str, Any]:
    """Convert an object into dictionary recursively.

    Note:
        Ignores all names starting with "__" (i.e. built-in methods).

    Args:
        obj: An instance of a class to convert.

    Raises:
        ValueError: When input argument is not an object.

    Returns:
        Converted dictionary mapping.
    """
    # check that input data is class instance
    if not hasattr(obj, "__class__"):
        raise ValueError(f"Expected a class instance. Received: {type(obj)}.")
    # convert object to dictionary
    if isinstance(obj, dict):
        obj_dict = obj
    elif isinstance(obj, torch.Tensor):
        # We have to treat torch tensors specially because `torch.tensor.__dict__` returns an empty
        # dict, which would mean that a torch.tensor would be stored as an empty dict. Instead we
        # want to store it directly as the tensor.
        return obj
    elif hasattr(obj, "__dict__"):
        obj_dict = obj.__dict__
    else:
        return obj

    # convert to dictionary
    data = dict()
    for key, value in obj_dict.items():
        # disregard builtin attributes
        if key.startswith("__"):
            continue
        # check if attribute is callable -- function
        if callable(value):
            data[key] = callable_to_string(value)
        # check if attribute is a dictionary
        elif hasattr(value, "__dict__") or isinstance(value, dict):
            data[key] = class_to_dict(value)
        # check if attribute is a list or tuple
        elif isinstance(value, (list, tuple)):
            data[key] = type(value)([class_to_dict(v) for v in value])
        else:
            data[key] = value
    return data

def load_yaml(filename: str) -> dict:
    """Loads an input PKL file safely.

    Args:
        filename: The path to pickled file.

    Raises:
        FileNotFoundError: When the specified file does not exist.

    Returns:
        The data read from the input file.
    """
    if not os.path.exists(filename):
        raise FileNotFoundError(f"File not found: {filename}")
    with open(filename) as f:
        data = yaml.full_load(f)
    return data


def dump_yaml(filename: str, data: dict | object, sort_keys: bool = False):
    """Saves data into a YAML file safely.

    Note:
        The function creates any missing directory along the file's path.

    Args:
        filename: The path to save the file at.
        data: The data to save either a dictionary or class object.
        sort_keys: Whether to sort the keys in the output file. Defaults to False.
    """
    # check ending
    if not filename.endswith("yaml"):
        filename += ".yaml"
    # create directory
    if not os.path.exists(os.path.dirname(filename)):
        os.makedirs(os.path.dirname(filename), exist_ok=True)
    # convert data into dictionary
    if not isinstance(data, dict):
        data = class_to_dict(data)
    # save data
    with open(filename, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=sort_keys)
