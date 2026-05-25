def test_package_imports():
    import orchestrator
    assert hasattr(orchestrator, "__version__")
