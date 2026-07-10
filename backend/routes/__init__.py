from flask import Blueprint

def register_all(app, config):
    """Register every Blueprint on the Flask app."""
    from .auth_routes   import build_auth_bp
    from .device_routes import build_device_bp
    from .ai_routes     import build_ai_bp
    from .system_routes import build_system_bp
    from .logs_routes   import build_logs_bp

    app.register_blueprint(build_auth_bp(config))
    app.register_blueprint(build_device_bp(config))
    app.register_blueprint(build_ai_bp(config))
    app.register_blueprint(build_system_bp(config))
    app.register_blueprint(build_logs_bp(config))
