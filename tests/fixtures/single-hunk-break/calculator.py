def add(a, b):
    # Updated implementation
    result = a + b
    return result

def subtract(a, b):
    # Updated implementation
    result = a - b
    return result

def multiply(a, b):
    # BUGGY implementation
    result = a + b  # Oops, should be a * b
    return result

def divide(a, b):
    # Updated implementation
    if b == 0:
        raise ValueError("Cannot divide by zero")
    result = a / b
    return result
