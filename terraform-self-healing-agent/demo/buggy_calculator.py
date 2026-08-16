"""
Buggy Calculator Module for Agent Demonstration.
Contains basic arithmetic operations with an intentional bug in add().
"""


def add(a: float, b: float) -> float:
    """Adds two numbers."""
    # Fixed: use addition.
    return a + b


def subtract(a: float, b: float) -> float:
    """Subtracts b from a."""
    return a - b


def multiply(a: float, b: float) -> float:
    """Multiplies two numbers."""
    return a * b


def divide(a: float, b: float) -> float:
    """Divides a by b."""
    if b == 0:
        raise ValueError("Cannot divide by zero.")
    return a / b