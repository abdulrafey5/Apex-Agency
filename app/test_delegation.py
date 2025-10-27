#!/usr/bin/env python3
from services.autogen_coordinator import run_autogen_task

def test_delegation():
    user_message = "Plan an ad campaign for coffee, delegate copy to worker."
    result = run_autogen_task(user_message)
    print("CEA Analysis:", result[:200])
    print("Full Result:", result)
    assert "worker" in result.lower() or "delegation" in result.lower(), "Delegation not detected"
    print("Test passed!")

if __name__ == "__main__":
    test_delegation()