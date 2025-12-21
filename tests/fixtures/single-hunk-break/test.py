#!/usr/bin/env python3
from calculator import add, subtract, multiply, divide

assert add(2, 3) == 5, "add failed"
assert subtract(5, 3) == 2, "subtract failed"
assert multiply(4, 3) == 12, "multiply failed"
assert divide(10, 2) == 5, "divide failed"

print("All tests passed!")
